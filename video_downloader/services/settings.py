from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class SettingsStore:
    ALLOWED = {
        "output_folder",
        "proxy_mode",
        "proxy_address",
        "proxy_username",
        "cookie_mode",
        "cookie_browser",
        "remember_cookie_file",
        "cookie_file",
    }

    def __init__(self, config_dir: Path) -> None:
        config_dir.mkdir(parents=True, exist_ok=True)
        self.path = config_dir / "settings.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {key: value for key, value in data.items() if key in self.ALLOWED}
        except (OSError, json.JSONDecodeError, AttributeError):
            return {}

    def save(self, values: dict[str, Any]) -> None:
        safe = {key: values[key] for key in self.ALLOWED if key in values}
        if "@" in str(safe.get("proxy_address", "")):
            safe["proxy_address"] = ""
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
