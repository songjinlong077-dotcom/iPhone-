from __future__ import annotations

import logging
import ctypes
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event
from unittest.mock import patch

import requests

from video_downloader.models.download_task import DownloadMode, DownloadTask
from video_downloader.proxy import ProxyConfig
from video_downloader.services.download_service import YtDlpDownloadService
from video_downloader.services.error_translator import translate_error
from video_downloader.services.filename_utils import safe_stem
from video_downloader.services.history import HistoryStore
from video_downloader.services.media_analyzer import MediaAnalyzer
from video_downloader.services.process_manager import ProcessManager
from video_downloader.services.progress_parser import parse_progress_line
from video_downloader.services.settings import SettingsStore
from video_downloader.services.tool_manager import ToolError, ToolManager

PAYLOAD = b"\x00\x00\x00\x18ftypmp42" + b"service-test" * 32768


class FileHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = Path(__file__).parents[1]
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FileHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/video.mp4"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=self.project / "03_工作过程" / "临时")
        self.folder = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_tool_paths_and_versions_are_project_local(self) -> None:
        manager = ToolManager()
        manager.require_tools()
        self.assertEqual(manager.paths.root, self.project / "tools" / "windows-x64")
        versions = manager.versions()
        self.assertTrue(versions["yt-dlp"])
        self.assertIn("ffmpeg version", versions["FFmpeg"].lower())
        self.assertIn("deno", versions["Deno"].lower())

    def test_progress_parser_and_error_translation(self) -> None:
        parsed = parse_progress_line("PROGRESS|download|downloading|50|100|NA|25|2|137")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[1].percent, 50)  # type: ignore[union-attr]
        self.assertIn("暂不支持", translate_error("ERROR: Unsupported URL"))
        self.assertIn("需要登录", translate_error("Sign in to confirm"))
        self.assertIn("DRM", translate_error("This format is DRM protected"))
        self.assertIn("私密", translate_error("Private video"))
        self.assertIn("拒绝访问", translate_error("HTTP Error 403"))
        self.assertIn("频繁", translate_error("HTTP Error 429"))

    def test_missing_ffmpeg_is_reported_before_download(self) -> None:
        manager = ToolManager(self.folder)
        self.assertIn("ffmpeg.exe", manager.missing_tools())
        with self.assertRaisesRegex(ToolError, "ffmpeg.exe"):
            manager.require_tools()

    def test_safe_filename_reserved_chars_and_length(self) -> None:
        self.assertEqual(safe_stem("CON", self.folder), "_CON")
        cleaned = safe_stem('中文<>:"/\\|?*标题' * 30, self.folder)
        self.assertNotRegex(cleaned, r'[<>:"/\\|?*]')
        self.assertLessEqual(len(str(self.folder / (cleaned + ".mp4"))), 220)

    def test_settings_never_save_proxy_password_and_history_persists(self) -> None:
        settings = SettingsStore(self.folder)
        settings.save({"proxy_mode": "HTTP 代理", "proxy_address": "http://user:secret@host:1", "proxy_password": "secret", "output_folder": "D:/x"})
        text = settings.path.read_text(encoding="utf-8")
        self.assertNotIn("secret", text)
        self.assertNotIn("password", text)
        history = HistoryStore(self.folder)
        history.add(title="中文", url=self.url, platform="test", path="D:/中文.mp4", status="成功")
        self.assertEqual(HistoryStore(self.folder).load()[0]["title"], "中文")

    def test_analyzer_and_ytdlp_download_local_mp4(self) -> None:
        tools = ToolManager()
        logger = logging.getLogger("service-test")
        analyzer = MediaAnalyzer(tools, ProcessManager(), logger)
        info = analyzer.analyze(self.url, ProxyConfig())
        self.assertTrue(info.title)

        manager = ProcessManager()
        service = YtDlpDownloadService(tools, manager, logger)
        progress = []
        states = []
        result = service.download(
            DownloadTask(self.url, self.folder, "中文:测试", DownloadMode.BEST),
            progress.append,
            states.append,
            Event(),
        )
        self.assertTrue(result.files)
        self.assertEqual(result.files[0].read_bytes(), PAYLOAD)
        self.assertTrue(progress)
        self.assertFalse(manager.running)

    def test_command_arguments_keep_url_as_one_item_and_use_local_tools(self) -> None:
        tools = ToolManager()
        service = YtDlpDownloadService(tools, ProcessManager(), logging.getLogger("args-test"))
        url = self.url + "?name=a&danger=calc.exe"
        arguments, _ = service.build_arguments(DownloadTask(url, self.folder, "video"))
        self.assertEqual(arguments[-1], url)
        self.assertEqual(arguments[0], str(tools.paths.yt_dlp))
        self.assertIn(str(tools.paths.root), arguments)
        self.assertNotIn("shell", " ".join(arguments).lower())

    def test_mode_playlist_and_resolution_arguments(self) -> None:
        service = YtDlpDownloadService(ToolManager(), ProcessManager(), logging.getLogger("mode-test"))
        best, _ = service.build_arguments(
            DownloadTask(self.url, self.folder, "best", DownloadMode.BEST, resolution=720, playlist=True)
        )
        self.assertIn("--yes-playlist", best)
        self.assertIn("bv*[height<=720]+ba/b[height<=720]", best)
        compatible, _ = service.build_arguments(
            DownloadTask(self.url, self.folder, "mp4", DownloadMode.COMPATIBLE_MP4)
        )
        self.assertIn("bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", compatible)
        audio, _ = service.build_arguments(
            DownloadTask(self.url, self.folder, "audio", DownloadMode.AUDIO_ONLY, audio_format="mp3")
        )
        self.assertIn("--audio-format", audio)
        self.assertIn("mp3", audio)

    def test_process_manager_cancels_windows_process_tree(self) -> None:
        manager = ProcessManager()
        child_code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid, flush=True); time.sleep(60)"
        process = manager.start([sys.executable, "-u", "-c", child_code], self.folder)
        assert process.stdout is not None
        child_pid = int(process.stdout.readline().strip())
        manager.cancel()
        process.stdout.close()
        manager.clear(process)
        self.assertIsNotNone(process.poll())
        time.sleep(0.3)
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, child_pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            self.assertNotEqual(exit_code.value, 259, "取消后仍有子进程存活")

    def test_failed_update_keeps_existing_ytdlp(self) -> None:
        root = self.folder / "app"
        tools_dir = root / "tools" / "windows-x64"
        tools_dir.mkdir(parents=True)
        for name in ToolManager.REQUIRED:
            (tools_dir / name).write_bytes(b"old-tool")
        manager = ToolManager(root)
        original = manager.paths.yt_dlp.read_bytes()
        with patch("video_downloader.services.tool_manager.requests.get", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(ToolError):
                manager.update_yt_dlp()
        self.assertEqual(manager.paths.yt_dlp.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
