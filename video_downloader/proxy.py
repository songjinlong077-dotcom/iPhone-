from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote, urlsplit, urlunsplit


class ProxyMode(str, Enum):
    NONE = "不使用代理"
    HTTP = "HTTP 代理"
    HTTPS = "HTTPS 代理"
    SOCKS5 = "SOCKS5 代理"


@dataclass(frozen=True)
class ProxyConfig:
    mode: ProxyMode = ProxyMode.NONE
    address: str = ""
    username: str = ""
    password: str = ""

    @property
    def enabled(self) -> bool:
        return self.mode is not ProxyMode.NONE

    def requests_proxies(self) -> dict[str, str] | None:
        if not self.enabled:
            return None

        address = self.address.strip()
        if not address:
            raise ValueError("请填写代理地址。")

        default_scheme = {
            ProxyMode.HTTP: "http",
            ProxyMode.HTTPS: "https",
            ProxyMode.SOCKS5: "socks5h",
        }[self.mode]
        if "://" not in address:
            address = f"{default_scheme}://{address}"

        parsed = urlsplit(address)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("代理账号和密码请分别填写，不要写在代理地址中。")
        allowed_schemes = {
            ProxyMode.HTTP: {"http"},
            ProxyMode.HTTPS: {"http", "https"},
            ProxyMode.SOCKS5: {"socks5", "socks5h"},
        }[self.mode]
        if parsed.scheme.lower() not in allowed_schemes:
            expected = "/".join(sorted(allowed_schemes))
            raise ValueError(f"代理协议与所选类型不匹配，应使用 {expected}。")
        try:
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("代理端口无效，应填写 1 到 65535 之间的数字。") from exc
        if not host or port is None:
            raise ValueError("代理地址格式不正确，应包含主机和端口，例如 127.0.0.1:7890。")

        rendered_host = f"[{host}]" if ":" in host else host

        if self.username:
            userinfo = quote(self.username, safe="")
            if self.password:
                userinfo += ":" + quote(self.password, safe="")
            netloc = f"{userinfo}@{rendered_host}:{port}"
        else:
            netloc = f"{rendered_host}:{port}"

        normalized = urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))
        return {"http": normalized, "https": normalized}

    def yt_dlp_proxy(self) -> str | None:
        proxies = self.requests_proxies()
        return proxies["https"] if proxies else None

    def safe_description(self) -> str:
        if not self.enabled:
            return ProxyMode.NONE.value
        parsed = urlsplit(self.address if "://" in self.address else f"x://{self.address}")
        host = parsed.hostname or "地址无效"
        try:
            port_value = parsed.port
        except ValueError:
            port_value = None
        port = f":{port_value}" if port_value else ""
        return f"{self.mode.value}（{host}{port}）"
