from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

MAX_COOKIE_FILE_BYTES = 20 * 1024 * 1024
NETSCAPE_HEADERS = {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}


class CookieMode(str, Enum):
    NONE = "none"
    BROWSER = "browser"
    FILE = "file"


class SupportedBrowser(str, Enum):
    EDGE = "edge"
    CHROME = "chrome"
    FIREFOX = "firefox"


BROWSER_LABELS: dict[SupportedBrowser, str] = {
    SupportedBrowser.EDGE: "Microsoft Edge",
    SupportedBrowser.CHROME: "Google Chrome",
    SupportedBrowser.FIREFOX: "Mozilla Firefox",
}
LABEL_TO_BROWSER: dict[str, SupportedBrowser] = {label: browser for browser, label in BROWSER_LABELS.items()}


@dataclass(frozen=True)
class AuthConfig:
    cookie_mode: CookieMode = CookieMode.NONE
    browser: SupportedBrowser | None = None
    browser_profile: str | None = None
    cookie_file: Path | None = None


def validate_browser_profile(profile: str | None) -> str:
    """校验浏览器配置文件；返回清理后的值，非法输入抛出 ValueError。"""
    if profile is None:
        return ""
    value = str(profile).strip()
    if not value:
        return ""
    if any(ord(char) < 32 for char in value):
        raise ValueError("浏览器配置文件无效，不能包含换行或控制字符。")
    if value.startswith("--"):
        raise ValueError("浏览器配置文件无效，不能以 -- 开头。")
    lowered = value.lower()
    if lowered.startswith(("http://", "https://", "file://")):
        raise ValueError("浏览器配置文件无效，不能是 URL。")
    return value


def validate_cookie_file(path: Path | None) -> Path:
    """校验 cookies.txt 必须是存在、非空、大小合理且为 Netscape 格式的普通文件。"""
    if path is None:
        raise ValueError("请选择 Cookie 文件。")
    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise ValueError("Cookie 文件不存在，请重新选择。")
    size = resolved.stat().st_size
    if size == 0:
        raise ValueError("Cookie 文件为空。")
    if size > MAX_COOKIE_FILE_BYTES:
        raise ValueError("Cookie 文件异常过大。")
    with resolved.open("r", encoding="utf-8-sig", errors="replace") as file:
        first_line = file.readline().strip()
    if first_line not in NETSCAPE_HEADERS:
        raise ValueError("Cookie 文件不是 Netscape 格式，需要 cookies.txt。")
    return resolved


def build_auth_args(auth: AuthConfig) -> list[str]:
    """把经过校验的认证配置转换为 yt-dlp 参数列表。"""
    if auth is None or auth.cookie_mode == CookieMode.NONE:
        return []

    if auth.cookie_mode == CookieMode.BROWSER:
        if auth.browser not in {
            SupportedBrowser.EDGE,
            SupportedBrowser.CHROME,
            SupportedBrowser.FIREFOX,
        }:
            raise ValueError("不支持的浏览器。")
        value = auth.browser.value
        if auth.browser_profile:
            profile = validate_browser_profile(auth.browser_profile)
            if profile:
                value = f"{value}:{profile}"
        return ["--cookies-from-browser", value]

    if auth.cookie_mode == CookieMode.FILE:
        cookie_file = validate_cookie_file(auth.cookie_file)
        return ["--cookies", str(cookie_file)]

    raise ValueError("无效的 Cookie 模式。")
