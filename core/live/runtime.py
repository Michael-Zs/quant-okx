"""实盘 job / state / 日志的读写，以及 start_job / stop_job / list_jobs。

UI 与 REST API 共用这套接口；daemon 是独立进程，由 start_job 用 subprocess 拉起
（start_new_session=True 脱离父进程组，关闭浏览器/重启控制台不影响）。
"""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from core.utils.config import settings


# ---- 路径 ----
def job_path(job_id: str) -> Path:
    return settings.JOBS_DIR / f"{job_id}.json"


def state_path(job_id: str) -> Path:
    return settings.STATE_DIR / f"{job_id}.json"


def log_path(job_id: str) -> Path:
    return settings.LOGS_DIR / f"{job_id}.jsonl"


def out_path(job_id: str) -> Path:
    return settings.LOGS_DIR / f"{job_id}.out"


def _lock_path(job_id: str) -> Path:
    return settings.STATE_DIR / f"{job_id}.lock"


def _acquire_lock(job_id: str, stale_sec: int = 30) -> int | None:
    """用 O_CREAT|O_EXCL 原子创建锁文件。失败时检查是否过期（进程崩溃遗留）。"""
    lp = _lock_path(job_id)
    lp.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        # 锁文件已存在，检查是否过期
        try:
            if time.time() - os.path.getmtime(lp) > stale_sec:
                lp.unlink()
                return os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except (OSError, FileNotFoundError):
            pass
        return None


def _release_lock(job_id: str, fd: int):
    """释放锁文件。"""
    lp = _lock_path(job_id)
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        lp.unlink()
    except FileNotFoundError:
        pass


# ---- 读写 ----
def write_json_atomic(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_log(job_id: str, event: dict):
    event = {**event, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(log_path(job_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def read_logs(job_id: str, n: int = 50) -> list[dict]:
    p = log_path(job_id)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-n:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            out.append({"raw": ln})
    return out


# ---- 进程 ----
def is_process_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def gen_job_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


# ---- job 管理 ----
def list_jobs() -> list[dict]:
    jobs = []
    for p in sorted(settings.JOBS_DIR.glob("*.json"), reverse=True):
        j = read_json(p, {}) or {}
        j.setdefault("job_id", p.stem)
        # 检测孤儿 job（标 running 但进程已死）
        j["alive"] = is_process_alive(j.get("pid")) if j.get("status") == "running" else False
        jobs.append(j)
    return jobs


def get_job(job_id: str) -> dict:
    return read_json(job_path(job_id), {})


def get_state(job_id: str) -> dict:
    return read_json(state_path(job_id), {})


def start_job(config: dict) -> str:
    job_id = config.get("job_id") or gen_job_id()
    lock = _acquire_lock(job_id)
    if not lock:
        # 没拿到锁：另一个请求正在启动，等它完成
        time.sleep(0.5)
        return job_id
    try:
        # 锁内双重检查
        existing = read_json(job_path(job_id), {})
        if existing.get("status") == "running" and is_process_alive(existing.get("pid")):
            return job_id
        config["job_id"] = job_id
        config["status"] = "running"
        config["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json_atomic(job_path(job_id), config)

        daemon = settings.ROOT / "scripts" / "trader_daemon.py"
        proc = subprocess.Popen(
            [sys.executable, str(daemon), "--job", str(job_path(job_id))],
            stdout=open(out_path(job_id), "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(settings.ROOT),
        )
        config["pid"] = proc.pid
        write_json_atomic(job_path(job_id), config)
        return job_id
    finally:
        _release_lock(job_id, lock)


def stop_job(job_id: str) -> bool:
    j = read_json(job_path(job_id), {})
    if not j:
        return False
    pid = j.get("pid")
    if pid and is_process_alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
        # 等待优雅退出（最多 5 秒），超时强杀（daemon 在网络 IO 中可能延迟响应信号）
        for _ in range(50):
            if not is_process_alive(pid):
                break
            time.sleep(0.1)
        if is_process_alive(pid):
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass
    j["status"] = "stopped"
    j["stopped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_atomic(job_path(job_id), j)
    return True


def delete_job(job_id: str) -> bool:
    stop_job(job_id)
    for p in (job_path(job_id), state_path(job_id), log_path(job_id), out_path(job_id)):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    return True


# ---- 策略组部署（多组占比；daemon 读 DB，用 --deployment <id>）----

def start_deployment(deployment_id: str) -> str:
    """启动部署 daemon。幂等：文件锁 + 双重检查，不会重复拉起进程。"""
    job_id = deployment_id
    lock = _acquire_lock(job_id)
    if not lock:
        time.sleep(0.5)
        return job_id
    try:
        # 锁内双重检查：已在运行则直接返回
        existing = read_json(job_path(job_id), {})
        if existing.get("status") == "running" and is_process_alive(existing.get("pid")):
            return job_id
        config = {"deployment_id": deployment_id, "job_id": job_id,
                  "status": "running", "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        write_json_atomic(job_path(job_id), config)
        daemon = settings.ROOT / "scripts" / "trader_daemon.py"
        proc = subprocess.Popen(
            [sys.executable, str(daemon), "--deployment", deployment_id],
            stdout=open(out_path(job_id), "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True, cwd=str(settings.ROOT))
        config["pid"] = proc.pid
        write_json_atomic(job_path(job_id), config)
        return job_id
    finally:
        _release_lock(job_id, lock)


def stop_deployment(deployment_id: str) -> bool:
    """停止部署 daemon（按 deployment_id 作 key，复用 stop_job）。"""
    return stop_job(deployment_id)
