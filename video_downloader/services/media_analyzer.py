from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..core import DownloadCancelled, DownloadError, validate_http_url
from ..models.auth_config import BROWSER_LABELS, AuthConfig, build_auth_args
from ..models.media_info import MediaFormat, MediaInfo
from ..proxy import ProxyConfig
from .app_logging import redact_command, redact_text
from .error_translator import translate_error
from .process_manager import ProcessManager
from .tool_manager import ToolManager


@dataclass(frozen=True)
class CookieTestResult:
    browser_label: str
    title: str
    uploader: str


class MediaAnalyzer:
    def __init__(self, tools: ToolManager, processes: ProcessManager, logger: logging.Logger) -> None:
        self.tools = tools
        self.processes = processes
        self.logger = logger

    def _parse_arguments(self, url: str, proxy: ProxyConfig, auth: AuthConfig) -> list[str]:
        arguments = [
            str(self.tools.paths.yt_dlp),
            "--dump-single-json",
            "--no-playlist",
            "--no-warnings",
            "--encoding",
            "utf-8",
            "--ffmpeg-location",
            str(self.tools.paths.root),
            "--js-runtimes",
            f"deno:{self.tools.paths.deno}",
        ]
        arguments.extend(build_auth_args(auth))
        proxy_url = proxy.yt_dlp_proxy()
        if proxy_url:
            arguments.extend(["--proxy", proxy_url])
        arguments.append(url)
        return arguments

    def analyze(self, url: str, proxy: ProxyConfig, auth: AuthConfig = AuthConfig()) -> MediaInfo:
        clean_url = validate_http_url(url)
        self.tools.require_tools()
        arguments = self._parse_arguments(clean_url, proxy, auth)
        self.logger.info("解析视频：%s", redact_command(arguments, (proxy.password,)))

        process = self.processes.start(arguments, self.tools.app_root)
        lines: list[str] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                lines.append(line.rstrip())
            return_code = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self.processes.clear(process)

        output = "\n".join(lines)
        safe_output = redact_text(output, (proxy.password,))
        if return_code != 0:
            self.logger.error("解析失败：%s", safe_output)
            raise DownloadError(translate_error(safe_output), safe_output)

        data = None
        for line in reversed(lines):
            if line.lstrip().startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not isinstance(data, dict):
            self.logger.error("解析输出中没有有效 JSON：%s", safe_output)
            raise DownloadError("无法读取视频信息，请更新 yt-dlp 后重试。", safe_output)
        return self._to_media_info(clean_url, data)

    def test_cookie(
        self,
        url: str,
        proxy: ProxyConfig,
        auth: AuthConfig,
        cancel_event: threading.Event,
        timeout: float = 45.0,
    ) -> CookieTestResult:
        clean_url = validate_http_url(url)
        self.tools.require_tools()
        if not build_auth_args(auth):
            raise DownloadError("请先在设置中选择一种 Cookie 方式。")
        arguments = self._parse_arguments(clean_url, proxy, auth)
        self.logger.info("测试 Cookie：%s", redact_command(arguments, (proxy.password,)))

        process = self.processes.start(arguments, self.tools.app_root)
        pending: queue.Queue[str | None] = queue.Queue()

        def _read() -> None:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    pending.put(line.rstrip())
            finally:
                pending.put(None)

        reader = threading.Thread(target=_read, name="cookie-test-reader", daemon=True)
        reader.start()
        lines: list[str] = []
        deadline = time.monotonic() + timeout
        timed_out = False
        try:
            while True:
                if cancel_event.is_set():
                    self.processes.cancel()
                    raise DownloadCancelled()
                try:
                    item = pending.get(timeout=0.2)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        timed_out = True
                        self.processes.cancel()
                        break
                    continue
                if item is None:
                    break
                lines.append(item)
            return_code = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self.processes.clear(process)

        if timed_out:
            self.logger.error("Cookie 测试超时")
            raise DownloadError("Cookie 测试超时，请检查网络或代理。", "测试超过 45 秒未完成。")

        output = "\n".join(lines)
        safe_output = redact_text(output, (proxy.password,))
        if return_code != 0:
            self.logger.error("Cookie 测试失败：%s", safe_output)
            raise DownloadError(translate_error(safe_output), safe_output)

        data = None
        for line in reversed(lines):
            if line.lstrip().startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not isinstance(data, dict):
            raise DownloadError("Cookie 测试无法读取视频信息。", safe_output)

        browser_label = BROWSER_LABELS.get(auth.browser, "浏览器") if auth.browser else "浏览器"
        return CookieTestResult(
            browser_label=browser_label,
            title=str(data.get("title") or data.get("fulltitle") or "未命名视频"),
            uploader=str(data.get("uploader") or data.get("channel") or data.get("creator") or "未知"),
        )

    @staticmethod
    def _to_media_info(url: str, data: dict) -> MediaInfo:
        available: dict[int, MediaFormat] = {}
        for item in data.get("formats") or []:
            height = item.get("height")
            if not isinstance(height, (int, float)) or int(height) <= 0:
                continue
            height = int(height)
            label = item.get("format_note") or f"{height}p"
            available[height] = MediaFormat(
                str(item.get("format_id") or ""),
                f"{height}p · {label}",
                height,
                str(item.get("ext") or ""),
            )
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        is_playlist = data.get("_type") == "playlist" or bool(data.get("playlist_count")) or "list" in query
        return MediaInfo(
            url=url,
            title=str(data.get("title") or data.get("fulltitle") or "未命名视频"),
            uploader=str(data.get("uploader") or data.get("channel") or data.get("creator") or "未知"),
            duration=float(data["duration"]) if isinstance(data.get("duration"), (int, float)) else None,
            platform=str(data.get("extractor_key") or data.get("extractor") or "未知"),
            thumbnail_url=str(data.get("thumbnail") or ""),
            is_playlist=is_playlist,
            playlist_count=data.get("playlist_count") if isinstance(data.get("playlist_count"), int) else None,
            formats=[available[key] for key in sorted(available, reverse=True)],
            extractor_key=str(data.get("extractor_key") or ""),
        )
