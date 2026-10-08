from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MediaFormat:
    format_id: str
    label: str
    height: int | None = None
    extension: str = ""


@dataclass
class MediaInfo:
    url: str
    title: str
    uploader: str = "未知"
    duration: float | None = None
    platform: str = "未知"
    thumbnail_url: str = ""
    is_playlist: bool = False
    playlist_count: int | None = None
    formats: list[MediaFormat] = field(default_factory=list)
    extractor_key: str = ""

    @property
    def duration_text(self) -> str:
        if self.duration is None:
            return "未知"
        seconds = max(0, int(self.duration))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
