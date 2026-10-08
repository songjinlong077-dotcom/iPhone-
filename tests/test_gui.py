from __future__ import annotations

import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from video_downloader.core import DownloadProgress
from video_downloader.gui import VideoDownloaderApp


GUI_PAYLOAD = b"\x00\x00\x00\x18ftypmp42" + (b"gui-download-test" * 4096)


class GuiMediaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(GUI_PAYLOAD)))
        self.end_headers()
        self.wfile.write(GUI_PAYLOAD)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class GuiResponsivenessTests(unittest.TestCase):
    def test_start_button_completes_real_download(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), GuiMediaHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        app = VideoDownloaderApp()
        errors: list[str] = []
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / "03_工作过程" / "临时") as folder:
            destination = Path(folder) / "button-test.mp4"
            app.url_var.set(f"http://127.0.0.1:{server.server_port}/video.mp4")
            app.folder_var.set(folder)
            app.filename_var.set(destination.name)

            def finish_when_ready() -> None:
                if app.last_download or errors:
                    app.root.destroy()
                else:
                    app.root.after(50, finish_when_ready)

            with patch("video_downloader.ui.main_window.messagebox.showinfo"), patch(
                "video_downloader.ui.main_window.messagebox.showerror",
                side_effect=lambda _title, message, **_kwargs: errors.append(str(message)),
            ):
                app.download_button.invoke()
                app.root.after(50, finish_when_ready)
                app.root.after(5000, app.root.destroy)
                app.run()

            self.assertFalse(errors)
            self.assertEqual(destination.read_bytes(), GUI_PAYLOAD)
            self.assertEqual(app.last_download, destination)

        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    def test_background_download_does_not_block_tk_event_loop(self) -> None:
        app = VideoDownloaderApp()
        ticks: list[float] = []
        with tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / "03_工作过程" / "临时") as folder:
            app.url_var.set("http://example.test/video.mp4")
            app.folder_var.set(folder)
            app.filename_var.set("video.mp4")

            def fake_download(url, destination, proxy, progress_callback, cancel_event):
                for index in range(5):
                    time.sleep(0.08)
                    progress_callback(DownloadProgress((index + 1) * 20, 100, 250))
                Path(destination).write_bytes(b"video")
                return Path(destination)

            def tick() -> None:
                ticks.append(time.monotonic())
                if app.worker and app.worker.is_alive():
                    app.root.after(20, tick)
                else:
                    app.root.after(100, app.root.destroy)

            with patch("video_downloader.ui.main_window.download_file", side_effect=fake_download), patch(
                "video_downloader.ui.main_window.messagebox.showinfo"
            ):
                app._start_download()
                app.root.after(20, tick)
                app.run()

        self.assertGreaterEqual(len(ticks), 8, "后台下载期间 Tk 事件循环未持续响应")


if __name__ == "__main__":
    unittest.main(verbosity=2)
