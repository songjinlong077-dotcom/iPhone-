from __future__ import annotations

import os
import select
import shutil
import socket
import socketserver
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from video_downloader.core import (
    DownloadError,
    download_file,
    suggested_filename,
    test_proxy as check_proxy,
    validate_destination,
)
from video_downloader.proxy import ProxyConfig, ProxyMode

PAYLOAD = (b"0123456789abcdef" * 65536) + b"video-end"


class MediaHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)
        elif self.path == "/unknown.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(PAYLOAD)
            self.close_connection = True
        elif self.path == "/page":
            body = b"<html>not a video</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/denied":
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/cutoff.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(PAYLOAD) * 2))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(PAYLOAD[:1000])
            self.close_connection = True
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class RecordingProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits: list[str] = []

    def do_GET(self) -> None:
        type(self).hits.append(self.path)
        if self.path.endswith("/proxy-check"):
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class Socks5Handler(socketserver.BaseRequestHandler):
    hits = 0

    @staticmethod
    def _receive_exact(sock: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("SOCKS client closed early")
            data.extend(chunk)
        return bytes(data)

    def handle(self) -> None:
        client = self.request
        version, method_count = self._receive_exact(client, 2)
        if version != 5:
            return
        self._receive_exact(client, method_count)
        client.sendall(b"\x05\x00")

        version, command, _reserved, address_type = self._receive_exact(client, 4)
        if version != 5 or command != 1:
            return
        if address_type == 1:
            host = socket.inet_ntoa(self._receive_exact(client, 4))
        elif address_type == 3:
            length = self._receive_exact(client, 1)[0]
            host = self._receive_exact(client, length).decode("idna")
        else:
            client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        port = struct.unpack("!H", self._receive_exact(client, 2))[0]

        upstream = socket.create_connection((host, port), timeout=5)
        type(self).hits += 1
        try:
            client.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            sockets = [client, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 5)
                if not readable:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is client else client
                    target.sendall(data)
        finally:
            upstream.close()


class SocksServerContext:
    def __init__(self) -> None:
        class SocksServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = SocksServer(("127.0.0.1", 0), Socks5Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "SocksServerContext":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def address(self) -> str:
        host, port = self.server.server_address
        return f"socks5://{host}:{port}"


class ServerContext:
    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        class QuietThreadingHTTPServer(ThreadingHTTPServer):
            def handle_error(self, _request: object, _client_address: object) -> None:
                pass

        self.server = QuietThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "ServerContext":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / "03_工作过程" / "临时")
        self.folder = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_direct_download_with_progress_and_chinese_path(self) -> None:
        progress = []
        chinese = self.folder / "中文目录"
        chinese.mkdir()
        destination = chinese / "测试视频.mp4"
        with ServerContext(MediaHandler) as server:
            result = download_file(
                server.base_url + "/video.mp4",
                destination,
                ProxyConfig(),
                progress.append,
            )
        self.assertEqual(result.read_bytes(), PAYLOAD)
        self.assertTrue(progress)
        self.assertEqual(progress[-1].downloaded, len(PAYLOAD))
        self.assertEqual(progress[-1].total, len(PAYLOAD))

    def test_download_without_content_length(self) -> None:
        progress = []
        destination = self.folder / "unknown.mp4"
        with ServerContext(MediaHandler) as server:
            download_file(server.base_url + "/unknown.mp4", destination, ProxyConfig(), progress.append)
        self.assertEqual(destination.read_bytes(), PAYLOAD)
        self.assertIsNone(progress[-1].total)

    def test_no_proxy_mode_ignores_environment_proxy(self) -> None:
        destination = self.folder / "direct.mp4"
        bad_proxy = "http://127.0.0.1:1"
        with ServerContext(MediaHandler) as server, patch.dict(
            os.environ, {"HTTP_PROXY": bad_proxy, "HTTPS_PROXY": bad_proxy}, clear=False
        ):
            download_file(server.base_url + "/video.mp4", destination, ProxyConfig())
        self.assertEqual(destination.read_bytes(), PAYLOAD)

    def test_http_proxy_is_actually_used(self) -> None:
        RecordingProxyHandler.hits.clear()
        destination = self.folder / "through-proxy.mp4"
        with ServerContext(RecordingProxyHandler) as proxy_server:
            config = ProxyConfig(ProxyMode.HTTP, proxy_server.base_url)
            download_file("http://media.example/video.mp4", destination, config)
        self.assertEqual(destination.read_bytes(), PAYLOAD)
        self.assertEqual(RecordingProxyHandler.hits, ["http://media.example/video.mp4"])

    def test_proxy_test_uses_configured_proxy(self) -> None:
        RecordingProxyHandler.hits.clear()
        with ServerContext(RecordingProxyHandler) as proxy_server:
            config = ProxyConfig(ProxyMode.HTTP, proxy_server.base_url)
            result = check_proxy(config, "http://connectivity.example/proxy-check")
        self.assertEqual(result.status_code, 204)
        self.assertEqual(RecordingProxyHandler.hits, ["http://connectivity.example/proxy-check"])

    def test_socks5_proxy_download_is_actually_forwarded(self) -> None:
        Socks5Handler.hits = 0
        destination = self.folder / "through-socks5.mp4"
        with ServerContext(MediaHandler) as media_server, SocksServerContext() as socks_server:
            config = ProxyConfig(ProxyMode.SOCKS5, socks_server.address)
            download_file(media_server.base_url + "/video.mp4", destination, config)
        self.assertEqual(destination.read_bytes(), PAYLOAD)
        self.assertGreaterEqual(Socks5Handler.hits, 1)

    def test_html_and_forbidden_are_clear_errors_and_part_is_removed(self) -> None:
        with ServerContext(MediaHandler) as server:
            for route, expected in (("/page", "网页"), ("/denied", "拒绝访问")):
                destination = self.folder / (route[1:] + ".mp4")
                with self.assertRaisesRegex(DownloadError, expected):
                    download_file(server.base_url + route, destination, ProxyConfig())
                self.assertFalse(destination.exists())
                self.assertFalse(destination.with_name(destination.name + ".part").exists())

    def test_invalid_proxy_and_windows_filename_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "主机和端口"):
            ProxyConfig(ProxyMode.SOCKS5, "socks5://127.0.0.1").requests_proxies()
        with self.assertRaisesRegex(DownloadError, "不允许"):
            validate_destination(self.folder, "bad:name.mp4")
        self.assertEqual(suggested_filename("https://x.example/%E8%A7%86%E9%A2%91.mp4"), "视频.mp4")

    def test_proxy_credentials_are_encoded_and_safe_description_hides_them(self) -> None:
        config = ProxyConfig(
            ProxyMode.HTTP,
            "http://127.0.0.1:7890",
            username="user@example.com",
            password="p@ss:/word",
        )
        proxy_url = config.requests_proxies()["http"]  # type: ignore[index]
        self.assertIn("user%40example.com:p%40ss%3A%2Fword@", proxy_url)
        self.assertNotIn("p@ss:/word", config.safe_description())
        with self.assertRaisesRegex(ValueError, "分别填写"):
            ProxyConfig(ProxyMode.HTTP, "http://inline:secret@127.0.0.1:7890").requests_proxies()

    def test_unreachable_http_and_socks_proxies_return_chinese_error(self) -> None:
        for index, mode in enumerate((ProxyMode.HTTP, ProxyMode.SOCKS5)):
            destination = self.folder / f"proxy-failure-{index}.mp4"
            config = ProxyConfig(mode, "127.0.0.1:1")
            with self.subTest(mode=mode), self.assertRaisesRegex(DownloadError, "代理连接失败"):
                download_file("http://media.example/video.mp4", destination, config)

    def test_disk_space_check_and_interrupted_transfer_cleanup(self) -> None:
        with ServerContext(MediaHandler) as server:
            disk_target = self.folder / "too-large.mp4"
            fake_usage = shutil._ntuple_diskusage(total=100, used=99, free=1)
            with patch("video_downloader.core.shutil.disk_usage", return_value=fake_usage):
                with self.assertRaisesRegex(DownloadError, "磁盘可用空间不足"):
                    download_file(server.base_url + "/video.mp4", disk_target, ProxyConfig())

            cutoff_target = self.folder / "cutoff.mp4"
            with self.assertRaises(DownloadError):
                download_file(server.base_url + "/cutoff.mp4", cutoff_target, ProxyConfig())
            self.assertFalse(cutoff_target.exists())
            self.assertFalse(cutoff_target.with_name(cutoff_target.name + ".part").exists())

    def test_existing_file_is_not_overwritten(self) -> None:
        destination = self.folder / "existing.mp4"
        destination.write_bytes(b"keep")
        with self.assertRaisesRegex(DownloadError, "已存在"):
            download_file("http://example.invalid/video.mp4", destination, ProxyConfig())
        self.assertEqual(destination.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
