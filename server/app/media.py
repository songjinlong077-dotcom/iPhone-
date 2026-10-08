from __future__ import annotations

import json
import subprocess

from .security import validate_public_url
from .tools import Toolchain


class MediaAnalyzeError(RuntimeError):
    pass


def analyze_media(url: str, tools: Toolchain, timeout: int = 60) -> dict:
    clean = validate_public_url(url)
    command = [str(tools.ytdlp), "--dump-single-json", "--no-playlist", "--no-warnings", "--encoding", "utf-8", "--ffmpeg-location", str(tools.ffmpeg.parent), clean]
    completed = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, shell=False, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout.strip().splitlines()[-1:] or ["未知解析错误"]
        raise MediaAnalyzeError("视频解析失败：" + detail[0][:300])
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaAnalyzeError("yt-dlp 未返回有效的视频信息。") from exc
    formats: dict[int, dict] = {}
    for item in data.get("formats") or []:
        height = item.get("height")
        if isinstance(height, (int, float)) and int(height) > 0:
            value = int(height)
            formats[value] = {"height": value, "label": str(item.get("format_note") or f"{value}p")}
    return {
        "url": clean,
        "title": str(data.get("title") or "未命名视频"),
        "uploader": str(data.get("uploader") or data.get("channel") or "未知"),
        "platform": str(data.get("extractor_key") or data.get("extractor") or "未知"),
        "duration": float(data["duration"]) if isinstance(data.get("duration"), (int, float)) else None,
        "thumbnail_url": str(data.get("thumbnail") or ""),
        "formats": [formats[key] for key in sorted(formats, reverse=True)],
    }
