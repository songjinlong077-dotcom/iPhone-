from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ToolPaths:
    root: Path
    yt_dlp: Path
    ffmpeg: Path
    ffprobe: Path
    deno: Path


class ToolError(RuntimeError):
    pass


class ToolManager:
    REQUIRED = ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe")

    def __init__(self, root: Path | None = None) -> None:
        self.app_root = (root or application_root()).resolve()
        tool_root = self.app_root / "tools" / "windows-x64"
        self.paths = ToolPaths(
            tool_root,
            tool_root / "yt-dlp.exe",
            tool_root / "ffmpeg.exe",
            tool_root / "ffprobe.exe",
            tool_root / "deno.exe",
        )

    def missing_tools(self) -> list[str]:
        return [name for name in self.REQUIRED if not (self.paths.root / name).is_file()]

    def require_tools(self) -> None:
        missing = self.missing_tools()
        if missing:
            raise ToolError("缺少程序随附工具：" + "、".join(missing))

    @staticmethod
    def _version(executable: Path, arguments: list[str]) -> str:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [str(executable), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            shell=False,
            creationflags=creationflags,
            check=False,
        )
        if completed.returncode != 0:
            raise ToolError(f"{executable.name} 无法执行：{completed.stdout.strip()}")
        return completed.stdout.splitlines()[0].strip()

    def versions(self) -> dict[str, str]:
        self.require_tools()
        return {
            "yt-dlp": self._version(self.paths.yt_dlp, ["--version"]),
            "FFmpeg": self._version(self.paths.ffmpeg, ["-version"]),
            "FFprobe": self._version(self.paths.ffprobe, ["-version"]),
            "Deno": self._version(self.paths.deno, ["--version"]),
        }

    def validate_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test.tmp"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError as exc:
            raise ToolError(f"保存目录没有写入权限：{folder}") from exc

    def update_yt_dlp(self, progress: Callable[[str], None] | None = None) -> str:
        self.require_tools()
        updater = self.paths.root / ".update"
        updater.mkdir(exist_ok=True)
        candidate = updater / "yt-dlp.exe.new"
        backup = updater / "yt-dlp.exe.backup"
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        if progress:
            progress("正在下载 yt-dlp 更新…")
        try:
            with requests.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                with candidate.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            new_version = self._version(candidate, ["--version"])
            old_version = self._version(self.paths.yt_dlp, ["--version"])
            shutil.copy2(self.paths.yt_dlp, backup)
            os.replace(candidate, self.paths.yt_dlp)
            verified = self._version(self.paths.yt_dlp, ["--version"])
            if verified != new_version:
                raise ToolError("更新后的 yt-dlp 版本验证失败。")
            if backup.exists():
                backup.unlink()
            return f"{old_version} → {new_version}" if old_version != new_version else f"已是最新版本 {new_version}"
        except Exception as exc:
            if backup.exists():
                os.replace(backup, self.paths.yt_dlp)
            if candidate.exists():
                candidate.unlink()
            if isinstance(exc, ToolError):
                raise
            raise ToolError(f"yt-dlp 更新失败，旧版本已保留：{exc}") from exc
