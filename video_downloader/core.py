from __future__ import annotations

import errno
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import unquote, urlsplit

import requests

from .proxy import ProxyConfig

CHUNK_SIZE = 256 * 1024
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
USER_AGENT = "WindowsVideoDownloader/1.0"


class DownloadError(Exception):
    """面向用户展示的下载错误。"""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail or message


class DownloadCancelled(Exception):
    pass


@dataclass(frozen=True)
class DownloadProgress:
    downloaded: int
    total: int | None
    speed_bytes: float


@dataclass(frozen=True)
class ProxyTestResult:
    status_code: int
    elapsed_seconds: float
    target: str


def validate_http_url(url: str) -> str:
    clean = url.strip()
    parsed = urlsplit(clean)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise DownloadError("URL 无效，请输入完整的 http:// 或 https:// 视频地址。")
    return clean


def clean_error_detail(detail: str | None) -> str:
    """清洗错误详情：去掉空的 null/None 字符串，以及多行输出中单独成行的 null/None。"""
    if detail is None:
        return ""
    text = str(detail).strip()
    if text.lower() in {"", "none", "null"}:
        return ""
    lines = [line for line in text.splitlines() if line.strip().lower() not in {"null", "none"}]
    return "\n".join(lines).strip()


def suggested_filename(url: str) -> str:
    name = unquote(Path(urlsplit(url).path).name).strip() or "video.mp4"
    invalid = '<>:"/\\|?*'
    name = "".join("_" if char in invalid or ord(char) < 32 else char for char in name)
    name = name.rstrip(" .") or "video.mp4"
    if not Path(name).suffix:
        name += ".mp4"
    return name


def validate_destination(folder: str | Path, filename: str) -> Path:
    directory = Path(folder).expanduser()
    if not directory.is_dir():
        raise DownloadError("保存文件夹不存在，请重新选择。")

    filename = filename.strip()
    if not filename or filename in {".", ".."}:
        raise DownloadError("请输入有效的文件名。")
    if Path(filename).name != filename or any(c in filename for c in '<>:"/\\|?*'):
        raise DownloadError("文件名包含 Windows 不允许的字符。")
    if filename.endswith((" ", ".")):
        raise DownloadError("文件名不能以空格或句点结尾。")
    return directory / filename


def _new_session(proxy: ProxyConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.trust_env = False
    proxies = proxy.requests_proxies()
    if proxies:
        session.proxies.update(proxies)
    return session


def _friendly_network_error(exc: BaseException, proxy_enabled: bool) -> DownloadError:
    detail = str(exc).replace("\n", " ").strip()
    prefix = "代理连接失败" if proxy_enabled else "网络连接失败"
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return DownloadError(f"{prefix}：连接超时，请检查网络、地址或代理设置。")
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return DownloadError(f"{prefix}：读取超时，服务器长时间未返回数据。")
    if isinstance(exc, requests.exceptions.ProxyError):
        return DownloadError("代理连接失败：请检查代理地址、端口、协议和账号信息。")
    if isinstance(exc, requests.exceptions.SSLError):
        return DownloadError(f"{prefix}：SSL/TLS 证书或加密连接异常。")
    if isinstance(exc, requests.exceptions.ConnectionError):
        suffix = f"（{detail[:180]}）" if detail else ""
        return DownloadError(f"{prefix}：连接被拒绝、中断或目标不可达。{suffix}")
    if isinstance(exc, requests.exceptions.InvalidURL):
        return DownloadError("URL 格式无效，请检查地址。")
    return DownloadError(f"{prefix}：{detail or '未知网络错误'}")


def _raise_for_status(response: requests.Response) -> None:
    code = response.status_code
    if 200 <= code < 300:
        return
    messages = {
        401: "服务器要求身份验证（401），当前版本不支持网站登录下载。",
        403: "服务器拒绝访问（403），请确认该链接允许直接下载。",
        404: "未找到视频文件（404），请检查 URL 是否已失效。",
        407: "代理要求身份验证（407），请检查代理用户名和密码。",
        429: "请求过于频繁（429），请稍后再试。",
    }
    if code in messages:
        raise DownloadError(messages[code])
    if 500 <= code:
        raise DownloadError(f"服务器暂时不可用（HTTP {code}），请稍后再试。")
    raise DownloadError(f"服务器拒绝请求（HTTP {code}）。")


def download_file(
    url: str,
    destination: Path,
    proxy: ProxyConfig,
    progress_callback: Callable[[DownloadProgress], None] | None = None,
    cancel_event: Event | None = None,
) -> Path:
    url = validate_http_url(url)
    destination = Path(destination)
    if destination.exists():
        raise DownloadError("目标文件已存在，请更换文件名或保存位置。")

    partial = destination.with_name(destination.name + ".part")
    if partial.exists():
        raise DownloadError(f"发现同名未完成文件：{partial.name}。请移走或删除后再试。")

    session = _new_session(proxy)
    response: requests.Response | None = None
    downloaded = 0
    try:
        response = session.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        _raise_for_status(response)

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            raise DownloadError("该 URL 返回的是网页而不是视频文件，请使用直接的 MP4 文件地址。")

        raw_total = response.headers.get("Content-Length")
        total = int(raw_total) if raw_total and raw_total.isdigit() else None
        if total is not None:
            free = shutil.disk_usage(destination.parent).free
            if total > free:
                raise DownloadError("磁盘可用空间不足，无法保存该视频。")

        started = time.monotonic()
        last_report = started
        with partial.open("xb") as output:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled()
                if not chunk:
                    continue
                output.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if progress_callback and (now - last_report >= 0.15 or total == downloaded):
                    elapsed = max(now - started, 0.001)
                    progress_callback(DownloadProgress(downloaded, total, downloaded / elapsed))
                    last_report = now
            output.flush()
            os.fsync(output.fileno())

        if total is not None and downloaded != total:
            raise DownloadError(
                f"下载中断：服务器声明文件大小为 {total} 字节，实际只收到 {downloaded} 字节。"
            )
        if downloaded == 0:
            raise DownloadError("服务器未返回任何文件数据。")
        partial.replace(destination)
        if progress_callback:
            elapsed = max(time.monotonic() - started, 0.001)
            progress_callback(DownloadProgress(downloaded, total, downloaded / elapsed))
        return destination
    except DownloadCancelled:
        raise
    except DownloadError:
        raise
    except requests.RequestException as exc:
        raise _friendly_network_error(exc, proxy.enabled) from exc
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise DownloadError("磁盘空间不足，下载无法继续。") from exc
        raise DownloadError(f"无法写入文件：{exc}") from exc
    finally:
        if response is not None:
            response.close()
        session.close()
        if partial.exists() and not destination.exists():
            try:
                partial.unlink()
            except OSError:
                pass


def test_proxy(
    proxy: ProxyConfig,
    target: str = "https://example.com/",
) -> ProxyTestResult:
    if not proxy.enabled:
        raise DownloadError("请先选择并填写要测试的代理。")
    session = _new_session(proxy)
    started = time.monotonic()
    try:
        response = session.get(target, timeout=(CONNECT_TIMEOUT, 15), allow_redirects=True)
        _raise_for_status(response)
        return ProxyTestResult(response.status_code, time.monotonic() - started, target)
    except DownloadError:
        raise
    except requests.RequestException as exc:
        raise _friendly_network_error(exc, True) from exc
    finally:
        session.close()
