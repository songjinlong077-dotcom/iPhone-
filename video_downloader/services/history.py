from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, config_dir: Path) -> None:
        config_dir.mkdir(parents=True, exist_ok=True)
        self.path = config_dir / "history.json"

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def add(self, *, title: str, url: str, platform: str, path: str, status: str) -> None:
        records = self.load()
        records.append(
            {
                "title": title,
                "url": url,
                "platform": platform,
                "path": path,
                "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": status,
            }
        )
        records = records[-500:]
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
