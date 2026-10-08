from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class TaskRecord:
    id: str
    url: str
    title: str
    platform: str
    status: str
    progress: float
    downloaded_bytes: int
    total_bytes: int | None
    speed_bytes: float | None
    eta_seconds: int | None
    resolution: int | None
    mode: str
    error: str | None
    file_path: str | None
    created_at: str
    updated_at: str
    expires_at: str | None
    attempt: int

    @property
    def has_file(self) -> bool:
        return bool(self.file_path and Path(self.file_path).is_file())


class TaskRepository:
    FIELDS = tuple(TaskRecord.__dataclass_fields__)

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0, downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER, speed_bytes REAL, eta_seconds INTEGER, resolution INTEGER,
                    mode TEXT NOT NULL, error TEXT, file_path TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, expires_at TEXT, attempt INTEGER NOT NULL DEFAULT 1
                )"""
            )
            connection.commit()

    @staticmethod
    def _record(row: sqlite3.Row | None) -> TaskRecord | None:
        return TaskRecord(**dict(row)) if row else None

    def create(self, *, task_id: str, url: str, resolution: int | None, mode: str) -> TaskRecord:
        now = utc_now()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO tasks (id,url,status,resolution,mode,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (task_id, url, "queued", resolution, mode, now, now),
            )
            connection.commit()
        record = self.get(task_id)
        assert record is not None
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._record(row)

    def list(self, limit: int = 100) -> list[TaskRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [TaskRecord(**dict(row)) for row in rows]

    def update(self, task_id: str, **values: Any) -> TaskRecord | None:
        allowed = set(self.FIELDS) - {"id", "created_at"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            return self.get(task_id)
        clean["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in clean)
        with closing(self._connect()) as connection:
            connection.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*clean.values(), task_id))
            connection.commit()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            connection.commit()
        return cursor.rowcount > 0

    def recover_interrupted(self) -> int:
        now = utc_now()
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """UPDATE tasks
                   SET status='failed', error='服务重启，原下载进程已中断。', updated_at=?
                   WHERE status IN ('queued','analyzing','downloading','merging')""",
                (now,),
            )
            connection.commit()
        return cursor.rowcount
