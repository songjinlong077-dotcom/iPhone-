from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    pass


def _is_blocked(address: str) -> bool:
    return not ipaddress.ip_address(address).is_global


def validate_public_url(url: str, *, resolver=socket.getaddrinfo) -> str:
    clean = str(url).strip()
    parsed = urlsplit(clean)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("只允许完整的 HTTP 或 HTTPS 视频地址。")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL 不允许包含用户名或密码。")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise UnsafeUrlError("不允许访问本机或内网地址。")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked(str(literal)):
            raise UnsafeUrlError("不允许访问本机或内网地址。")
        return clean
    try:
        results = resolver(host, parsed.port or (443 if parsed.scheme.lower() == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrlError("无法解析视频地址的域名。") from exc
    addresses = {item[4][0] for item in results}
    if not addresses or any(_is_blocked(address) for address in addresses):
        raise UnsafeUrlError("域名解析到了本机、内网或保留地址。")
    return clean
