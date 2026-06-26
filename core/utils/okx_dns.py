"""国内 DNS 污染绕行：强制 www.okx.com → 真实 IP。

GFW 对 www.okx.com 做 DNS 劫持（返回 169.254.x.x 等假地址），导致 ccxt/requests
直连超时。通过 monkey-patch socket.getaddrinfo 把 www.okx.com 解析到真实 IP。

import 本模块即生效（模块级副作用，幂等：多次 import 只 patch 一次）。
任何访问 OKX 的进程入口（api_server / trader_daemon / executor_daemon）以及
core.data.fetcher 都应 import 本模块，确保在首次 OKX 请求前完成 patch。
"""
from __future__ import annotations
import socket

# Cloudflare 后端真实 IP（轮询）。失效时换 IP 即可。
_OKX_REAL_IPS = [
    ("104.18.43.174", 443),
    ("172.64.144.82", 443),
]

_orig_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "www.okx.com":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, p)) for ip, p in _OKX_REAL_IPS]
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


# 幂等：多次 import 只 patch 一次
if socket.getaddrinfo is not _patched_getaddrinfo:
    socket.getaddrinfo = _patched_getaddrinfo
