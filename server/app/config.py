from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    data_dir: Path
    max_workers: int = 2
    retention_hours: int = 24
    max_file_bytes: int = 2 * 1024 * 1024 * 1024
    analyze_timeout_seconds: int = 60
    ytdlp_bin: str | None = None
    ffmpeg_bin: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("VIDEO_API_KEY", "").strip()
        if len(api_key) < 16:
            raise RuntimeError("VIDEO_API_KEY 必须至少包含 16 个字符。")
        server_root = Path(__file__).resolve().parents[1]
        data_dir = Path(os.environ.get("VIDEO_DATA_DIR", server_root / "data")).expanduser().resolve()
        return cls(
            api_key=api_key,
            data_dir=data_dir,
            max_workers=max(1, int(os.environ.get("VIDEO_MAX_WORKERS", "2"))),
            retention_hours=max(1, int(os.environ.get("VIDEO_RETENTION_HOURS", "24"))),
            max_file_bytes=max(1024 * 1024, int(os.environ.get("VIDEO_MAX_FILE_BYTES", str(2 * 1024**3)))),
            analyze_timeout_seconds=max(10, int(os.environ.get("VIDEO_ANALYZE_TIMEOUT_SECONDS", "60"))),
            ytdlp_bin=os.environ.get("YTDLP_BIN") or None,
            ffmpeg_bin=os.environ.get("FFMPEG_BIN") or None,
        )
