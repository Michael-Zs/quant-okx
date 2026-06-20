"""策略注册表：内置策略发现 + 用户目录发现 + 动态重载。

- 内置：core/strategy/builtin/ 包内所有 Strategy 子类。
- 用户：strategies/ 目录下每个 .py 文件（UI 编辑器保存到这里）。
- 动态重载：discover_dir 每次重新 exec 用户文件，实现「保存即生效」。
"""
from __future__ import annotations
import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path

from core.strategy.base import Strategy


class StrategyRegistry:
    _strategies: dict[str, type[Strategy]] = {}
    _user_modules: set[str] = set()          # 跟踪已加载的用户模块，便于重载
    _user_registered: set[str] = set()       # 上次由用户目录注册的策略 name

    # ---- 注册 ----
    @classmethod
    def register(cls, strat_cls: type[Strategy]) -> type[Strategy]:
        name = getattr(strat_cls, "name", "")
        if name:
            cls._strategies[name] = strat_cls
        return strat_cls

    @classmethod
    def _register_module(cls, mod):
        from core.strategy.multi_base import MultiStrategy
        for attr in vars(mod).values():
            if not isinstance(attr, type):
                continue
            is_single = issubclass(attr, Strategy) and attr is not Strategy
            is_multi = issubclass(attr, MultiStrategy) and attr is not MultiStrategy
            if (is_single or is_multi) and getattr(attr, "name", ""):
                cls.register(attr)

    # ---- 查询 ----
    @classmethod
    def all(cls) -> dict[str, type[Strategy]]:
        return dict(cls._strategies)

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._strategies.keys())

    @classmethod
    def info(cls) -> list[dict]:
        return [
            {
                "name": s.name,
                "display_name": s.display_name or s.name,
                "description": s.description,
                "kind": getattr(s, "kind", "single"),
                "side_mode": getattr(s, "side_mode", "long_short"),
                "params": [
                    {"name": p.name, "default": p.default, "label": p.label,
                     "kind": p.kind, "min": p.min, "max": p.max, "step": p.step,
                     "options": p.options}
                    for p in s.param_schema()
                ],
            }
            for s in cls._strategies.values()
        ]

    @classmethod
    def get(cls, name: str) -> type[Strategy]:
        if name not in cls._strategies:
            raise KeyError(f"未知策略: {name}（可用: {cls.names()}）")
        return cls._strategies[name]

    # ---- 发现 ----
    @classmethod
    def discover_builtin(cls):
        import core.strategy.builtin as pkg
        for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
            try:
                mod = importlib.import_module(modname)
                cls._register_module(mod)
            except Exception as e:
                print(f"[registry] 加载内置策略 {modname} 失败: {e}")

    @classmethod
    def discover_dir(cls, directory, force_reload: bool = True):
        """扫描目录下 .py，动态加载为模块并注册其中的 Strategy 子类。

        force_reload 时先卸载上次由用户目录注册的策略，确保删除/修改文件后状态正确。
        """
        directory = Path(directory)
        if not directory.exists():
            return
        if force_reload:
            for m in list(cls._user_modules):
                sys.modules.pop(m, None)
            cls._user_modules.clear()
            for nm in list(cls._user_registered):
                cls._strategies.pop(nm, None)
            cls._user_registered = set()

        for py in sorted(directory.glob("*.py")):
            if py.name.startswith("_") or py.stem.endswith("example"):
                continue
            modname = f"user_strategy_{py.stem}"
            try:
                sys.modules.pop(modname, None)
                spec = importlib.util.spec_from_file_location(modname, py)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[modname] = mod
                before = set(cls._strategies.keys())
                spec.loader.exec_module(mod)
                cls._register_module(mod)
                cls._user_modules.add(modname)
                cls._user_registered.update(set(cls._strategies.keys()) - before)
            except Exception as e:
                print(f"[registry] 加载用户策略 {py.name} 失败: {e}")

    @classmethod
    def discover_all(cls, user_dir=None):
        """一次性发现内置 + 用户策略。"""
        from core.utils.config import settings
        cls.discover_builtin()
        cls.discover_dir(user_dir or settings.STRATEGIES_DIR)
