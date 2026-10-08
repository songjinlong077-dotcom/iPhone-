from __future__ import annotations

import hashlib
import http.client
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).parents[1]
TEMP_ROOT = PROJECT_ROOT / "03_工作过程" / "临时"
sys.path.insert(0, str(PROJECT_ROOT))

from video_downloader.core import download_file
from video_downloader.proxy import ProxyConfig, ProxyMode


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, _request: object, _client_address: object) -> None:
        pass


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass


class ForwardProxy(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.scheme != "http" or not parsed.hostname:
            self.send_error(400)
            return
        type(self).hits += 1
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={"User-Agent": "IntegrationProxy/1.0"})
            response = connection.getresponse()
            body = response.read()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in {"connection", "transfer-encoding"}:
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
        finally:
            connection.close()

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法生成集成测试 MP4。")

    with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp_name:
        folder = Path(temp_name)
        source = folder / "源视频.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x180:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                "-y",
                str(source),
            ],
            check=True,
        )

        media_handler = partial(QuietStaticHandler, directory=str(folder))
        media = QuietServer(("127.0.0.1", 0), media_handler)
        proxy = QuietServer(("127.0.0.1", 0), ForwardProxy)
        threads = [
            threading.Thread(target=media.serve_forever, daemon=True),
            threading.Thread(target=proxy.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            media_url = f"http://127.0.0.1:{media.server_port}/{source.name}"
            direct = folder / "直连下载.mp4"
            proxied = folder / "代理下载.mp4"
            direct_progress = []
            proxy_progress = []

            download_file(media_url, direct, ProxyConfig(), direct_progress.append)
            proxy_config = ProxyConfig(ProxyMode.HTTP, f"http://127.0.0.1:{proxy.server_port}")
            download_file(media_url, proxied, proxy_config, proxy_progress.append)

            expected = sha256(source)
            if sha256(direct) != expected or sha256(proxied) != expected:
                raise AssertionError("下载文件哈希与源 MP4 不一致。")
            if ForwardProxy.hits < 1:
                raise AssertionError("代理服务器未收到下载请求。")
            if not direct_progress or not proxy_progress:
                raise AssertionError("未收到下载进度回调。")

            print(f"Valid MP4 size: {source.stat().st_size} bytes")
            print(f"SHA-256: {expected}")
            print(f"Direct download: PASS ({len(direct_progress)} progress callbacks)")
            print(f"HTTP proxy download: PASS ({ForwardProxy.hits} proxy request)")
        finally:
            media.shutdown()
            proxy.shutdown()
            media.server_close()
            proxy.server_close()
            for thread in threads:
                thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
