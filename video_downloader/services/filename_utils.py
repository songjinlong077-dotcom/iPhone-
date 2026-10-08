from __future__ import annotations

import re
from pathlib import Path

RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_stem(value: str, folder: Path, limit: int = 220) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned) or "video"
    if cleaned.upper() in RESERVED:
        cleaned = "_" + cleaned
    max_stem = max(20, limit - len(str(folder.resolve())) - 12)
    return cleaned[:max_stem].rstrip(" .") or "video"


def unique_stem(folder: Path, stem: str) -> str:
    candidate = stem
    index = 1
    while any(folder.glob(f"{candidate}.*")):
        candidate = f"{stem} ({index})"
        index += 1
    return candidate
