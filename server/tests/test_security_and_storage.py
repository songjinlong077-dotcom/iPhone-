from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import TaskRepository
from app.security import UnsafeUrlError, validate_public_url


def public_resolver(*_args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def private_resolver(*_args, **_kwargs):
    return [(2, 1, 6, "", ("127.0.0.1", 80))]


class SecurityAndStorageTests(unittest.TestCase):
    def test_public_url_validation_blocks_credentials_and_private_networks(self) -> None:
        self.assertEqual(validate_public_url("https://example.com/video", resolver=public_resolver), "https://example.com/video")
        for url in ("file:///etc/passwd", "http://localhost/x", "http://127.0.0.1/x", "http://a:b@example.com"):
            with self.subTest(url=url), self.assertRaises(UnsafeUrlError):
                validate_public_url(url, resolver=public_resolver)
        with self.assertRaises(UnsafeUrlError):
            validate_public_url("http://example.invalid/x", resolver=private_resolver)

    def test_repository_persists_task_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TaskRepository(Path(directory) / "tasks.sqlite3")
            created = repository.create(task_id="abc123", url="https://example.com/video", resolution=1080, mode="best")
            self.assertEqual(created.status, "queued")
            updated = repository.update("abc123", status="completed", progress=100.0)
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "completed")  # type: ignore[union-attr]
            self.assertEqual(repository.list()[0].id, "abc123")

    def test_repository_marks_interrupted_tasks_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TaskRepository(Path(directory) / "tasks.sqlite3")
            repository.create(task_id="queued1", url="https://example.com/1", resolution=None, mode="best")
            self.assertEqual(repository.recover_interrupted(), 1)
            recovered = repository.get("queued1")
            self.assertEqual(recovered.status, "failed")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
