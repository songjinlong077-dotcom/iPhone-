from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..proxy import ProxyConfig
from .auth_config import AuthConfig


class TaskState(str, Enum):
    IDLE = "就绪"
    ANALYZING = "解析中"
    READY = "准备就绪"
    DOWNLOADING_VIDEO = "下载视频"
    DOWNLOADING_AUDIO = "下载音频"
    MERGING = "合并中"
    COMPLETED = "完成"
    FAILED = "失败"
    CANCELLED = "已取消"


class DownloadMode(str, Enum):
    BEST = "最高画质"
    COMPATIBLE_MP4 = "兼容 MP4"
    AUDIO_ONLY = "仅音频"


@dataclass
class DownloadTask:
    url: str
    output_folder: Path
    filename_stem: str
    mode: DownloadMode = DownloadMode.BEST
    resolution: int | None = None
    audio_format: str = "m4a"
    playlist: bool = False
    overwrite: bool = False
    proxy: ProxyConfig = ProxyConfig()
    auth: AuthConfig = AuthConfig()
