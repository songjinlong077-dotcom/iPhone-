from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tools import Toolchain


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        fake = root / "tool"
        fake.write_bytes(b"")
        settings = Settings(api_key="test-api-key-123456", data_dir=root / "data", max_workers=1)
        self.app = create_app(settings, Toolchain(fake, fake))
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer test-api-key-123456"}

    def tearDown(self) -> None:
        self.client.close()
        self.app.state.manager.close()
        self.temporary.cleanup()

    def test_health_is_public_and_tasks_require_auth(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/v1/tasks")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_analyze_returns_normalized_media(self) -> None:
        value = {
            "url": "https://example.com/video", "title": "Example", "uploader": "Owner",
            "platform": "Example", "duration": 12.5, "thumbnail_url": "https://example.com/image.jpg",
            "formats": [{"height": 1080, "label": "1080p"}],
        }
        with patch("app.main.analyze_media", return_value=value):
            response = self.client.post("/v1/media/analyze", headers=self.headers, json={"url": "https://example.com/video"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["formats"][0]["height"], 1080)

    def test_create_list_cancel_retry_and_delete(self) -> None:
        with patch("app.tasks.validate_public_url", return_value="https://example.com/video"), patch.object(
            self.app.state.manager._executor, "submit"
        ) as submit:
            response = self.client.post(
                "/v1/tasks", headers=self.headers,
                json={"url": "https://example.com/video", "resolution": 720, "mode": "best"},
            )
            self.assertEqual(response.status_code, 202)
            task_id = response.json()["id"]
            submit.assert_called_once()
        listed = self.client.get("/v1/tasks", headers=self.headers)
        self.assertEqual(listed.json()[0]["id"], task_id)
        cancelled = self.client.post(f"/v1/tasks/{task_id}/cancel", headers=self.headers)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        with patch.object(self.app.state.manager._executor, "submit"):
            retried = self.client.post(f"/v1/tasks/{task_id}/retry", headers=self.headers)
        self.assertEqual(retried.json()["attempt"], 2)
        self.client.post(f"/v1/tasks/{task_id}/cancel", headers=self.headers)
        deleted = self.client.delete(f"/v1/tasks/{task_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 204)


if __name__ == "__main__":
    unittest.main()
