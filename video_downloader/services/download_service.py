from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ..core import DownloadCancelled, DownloadError, validate_http_url
from ..models.auth_config import build_auth_args
from ..models.download_task import DownloadMode, DownloadTask, TaskState
from .app_logging import redact_args, redact_text
from .error_translator import translate_error
from .filename_utils import safe_stem, unique_stem
from .process_manager import ProcessManager
from .progress_parser import StructuredProgress, parse_progress_line
from .tool_manager import ToolManager


@dataclass
class DownloadResult:
    files: list[Path]
    command_summary: list[str]


class YtDlpDownloadService:
    PROGRESS_TEMPLATE = (
        "download:PROGRESS|download|%(progress.status)s|%(progress.downloaded_bytes)s|"
        "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|"
        "%(progress.eta)s|%(info.format_id)s"
    )
    POSTPROCESS_TEMPLATE = (
        "postprocess:PROGRESS|postprocess|%(progress.status)s|0|0|0|0|0|%(info.format_id)s"
    )

    def __init__(self, tools: ToolManager, processes: ProcessManager, logger: logging.Logger) -> None:
        self.tools = tools
        self.processes = processes
        self.logger = logger

    def build_arguments(self, task: DownloadTask) -> tuple[list[str], str]:
        self.tools.require_tools()
        validate_http_url(task.url)
        folder = task.output_folder.resolve()
        self.tools.validate_output_folder(folder)
        stem = safe_stem(task.filename_stem, folder)
        if not task.overwrite:
            stem = unique_stem(folder, stem)

        if task.playlist:
            template = "%(playlist_index)03d - %(title).150B.%(ext)s"
        else:
            template = stem + ".%(ext)s"
        arguments = [
            str(self.tools.paths.yt_dlp),
            "--no-simulate",
            "--newline",
            "--no-color",
            "--quiet",
            "--progress",
            "--encoding",
            "utf-8",
            "--ffmpeg-location",
            str(self.tools.paths.root),
            "--js-runtimes",
            f"deno:{self.tools.paths.deno}",
            "--progress-template",
            self.PROGRESS_TEMPLATE,
            "--progress-template",
            self.POSTPROCESS_TEMPLATE,
            "--print",
            "before_dl:STAGE|BEFORE_DL|%(format_id)s|%(vcodec)s|%(acodec)s",
            "--print",
            "post_process:STAGE|MERGING",
            "--print",
            "after_move:RESULT|%(filepath)s",
            "--yes-playlist" if task.playlist else "--no-playlist",
            "-P",
            str(folder),
            "-o",
            template,
        ]
        if task.overwrite:
            arguments.append("--force-overwrites")
        else:
            arguments.append("--no-overwrites")
        if task.playlist:
            archive = self.tools.app_root / "config" / "download-archive.txt"
            arguments.extend(["--download-archive", str(archive)])

        height = f"[height<={task.resolution}]" if task.resolution else ""
        if task.mode is DownloadMode.BEST:
            arguments.extend(["-f", f"bv*{height}+ba/b{height}", "--merge-output-format", "mp4/mkv"])
        elif task.mode is DownloadMode.COMPATIBLE_MP4:
            arguments.extend(
                [
                    "-f",
                    f"bv*[ext=mp4]{height}+ba[ext=m4a]/b[ext=mp4]{height}/b{height}",
                    "--merge-output-format",
                    "mp4",
                ]
            )
        else:
            audio_format = "mp3" if task.audio_format.lower() == "mp3" else "m4a"
            arguments.extend(["-f", "ba/b", "-x", "--audio-format", audio_format])

        proxy_url = task.proxy.yt_dlp_proxy()
        if proxy_url:
            arguments.extend(["--proxy", proxy_url])
        arguments.extend(build_auth_args(task.auth))
        arguments.append(task.url)
        return arguments, stem

    def download(
        self,
        task: DownloadTask,
        progress_callback: Callable[[StructuredProgress], None],
        state_callback: Callable[[TaskState], None],
        cancel_event: Event,
    ) -> DownloadResult:
        arguments, _stem = self.build_arguments(task)
        started_at = time.time()
        before_files = {path.resolve() for path in task.output_folder.iterdir() if path.is_file()}
        safe_args = redact_args(arguments, (task.proxy.password,))
        self.logger.info("启动 yt-dlp：%s", " ".join(safe_args))
        process = self.processes.start(arguments, self.tools.app_root)
        output: list[str] = []
        results: list[Path] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if cancel_event.is_set():
                    self.processes.cancel()
                    raise DownloadCancelled()
                stripped = line.rstrip()
                parsed = parse_progress_line(stripped)
                if parsed:
                    kind, payload = parsed
                    if kind == "progress":
                        progress_callback(payload)  # type: ignore[arg-type]
                    elif kind == "state":
                        state_callback(payload)  # type: ignore[arg-type]
                    elif kind == "result":
                        path = Path(str(payload))
                        if not path.is_absolute():
                            path = task.output_folder / path
                        results.append(path)
                else:
                    output.append(stripped)
            return_code = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self.processes.clear(process)

        if cancel_event.is_set():
            raise DownloadCancelled()
        if return_code != 0:
            detail = "\n".join(output[-100:])
            safe = redact_text(detail, (task.proxy.password,))
            self.logger.error("yt-dlp 下载失败（%s）：%s", return_code, safe)
            raise DownloadError(translate_error(safe), safe)
        existing = [path.resolve() for path in results if path.exists()]
        if not existing:
            incomplete_suffixes = {".part", ".ytdl", ".temp"}
            existing = [
                path.resolve()
                for path in task.output_folder.iterdir()
                if path.is_file()
                and path.suffix.lower() not in incomplete_suffixes
                and (path.resolve() not in before_files or path.stat().st_mtime >= started_at)
            ]
        if not existing:
            raise DownloadError("下载任务结束，但未找到输出文件，请查看日志。")
        return DownloadResult(existing, safe_args)

    @staticmethod
    def remove_partial_files(folder: Path) -> int:
        removed = 0
        for pattern in ("*.part", "*.ytdl", "*.temp"):
            for path in folder.glob(pattern):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
