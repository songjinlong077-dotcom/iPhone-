from __future__ import annotations

from dataclasses import dataclass

from ..models.download_task import TaskState


@dataclass(frozen=True)
class StructuredProgress:
    state: TaskState
    downloaded: int = 0
    total: int | None = None
    speed: float | None = None
    eta: int | None = None
    percent: float | None = None
    format_id: str = ""


def _number(value: str, caster):
    try:
        return caster(value) if value not in {"", "NA", "None", "null"} else None
    except (ValueError, TypeError):
        return None


def parse_progress_line(line: str) -> tuple[str, object] | None:
    clean = line.strip()
    if clean.startswith("PROGRESS|"):
        parts = clean.split("|")
        if len(parts) < 9:
            return None
        kind, status = parts[1], parts[2]
        downloaded = _number(parts[3], int) or 0
        total = _number(parts[4], int) or _number(parts[5], int)
        speed = _number(parts[6], float)
        eta = _number(parts[7], int)
        format_id = parts[8]
        percent = (downloaded / total * 100) if total else None
        state = TaskState.MERGING if kind == "postprocess" else TaskState.DOWNLOADING_VIDEO
        if status == "finished" and kind == "download":
            state = TaskState.MERGING
        return "progress", StructuredProgress(state, downloaded, total, speed, eta, percent, format_id)
    if clean.startswith("STAGE|"):
        parts = clean.split("|")
        stage = parts[1] if len(parts) > 1 else ""
        if stage == "MERGING":
            return "state", TaskState.MERGING
        if stage == "BEFORE_DL" and len(parts) >= 5:
            vcodec, acodec = parts[3], parts[4]
            state = TaskState.DOWNLOADING_AUDIO if vcodec == "none" and acodec != "none" else TaskState.DOWNLOADING_VIDEO
            return "state", state
    if clean.startswith("RESULT|"):
        return "result", clean.partition("|")[2]
    return None
