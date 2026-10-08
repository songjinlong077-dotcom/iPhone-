from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class ToolchainError(RuntimeError):
    pass


@dataclass(frozen=True)
class Toolchain:
    ytdlp: Path
    ffmpeg: Path

    @classmethod
    def discover(cls, ytdlp_bin: str | None = None, ffmpeg_bin: str | None = None) -> "Toolchain":
        project_root = Path(__file__).resolve().parents[2]
        windows_tools = project_root / "tools" / "windows-x64"

        def locate(explicit: str | None, name: str) -> Path | None:
            if explicit:
                candidate = Path(explicit).expanduser().resolve()
                return candidate if candidate.is_file() else None
            found = shutil.which(name)
            if found:
                return Path(found).resolve()
            bundled = windows_tools / f"{name}.exe"
            return bundled if bundled.is_file() else None

        ytdlp = locate(ytdlp_bin, "yt-dlp")
        ffmpeg = locate(ffmpeg_bin, "ffmpeg")
        if not ytdlp or not ffmpeg:
            missing = [name for name, value in (("yt-dlp", ytdlp), ("ffmpeg", ffmpeg)) if not value]
            raise ToolchainError("缺少服务端工具：" + "、".join(missing))
        return cls(ytdlp=ytdlp, ffmpeg=ffmpeg)
