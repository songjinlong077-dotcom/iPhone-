from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event

PROJECT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT))

from video_downloader.models.download_task import DownloadMode, DownloadTask
from video_downloader.core import DownloadCancelled
from video_downloader.proxy import ProxyConfig
from video_downloader.services.download_service import YtDlpDownloadService
from video_downloader.services.process_manager import ProcessManager
from video_downloader.services.tool_manager import ToolManager


class QuietHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/slow.mp4":
            total = 64 * 1024 * 1024
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(total))
            self.end_headers()
            chunk = b"0" * (256 * 1024)
            try:
                for _ in range(total // len(chunk)):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        super().do_GET()

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def ffprobe(tools: ToolManager, path: Path) -> dict:
    completed = subprocess.run(
        [
            str(tools.paths.ffprobe),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=True,
    )
    return json.loads(completed.stdout)


def main() -> int:
    tools = ToolManager()
    tools.require_tools()
    logger = logging.getLogger("v2-acceptance")
    with tempfile.TemporaryDirectory(dir=PROJECT / "03_工作过程" / "临时") as temp_name:
        root = Path(temp_name)
        source = root / "source"
        output = root / "中文输出目录"
        source.mkdir()
        output.mkdir()
        manifest = source / "manifest.mpd"
        subprocess.run(
            [
                str(tools.paths.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=24:duration=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=3",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-f",
                "dash",
                "-adaptation_sets",
                "id=0,streams=v id=1,streams=a",
                manifest.name,
            ],
            cwd=str(source),
            shell=False,
            check=True,
        )
        webm_manifest = source / "webm_manifest.mpd"
        subprocess.run(
            [
                str(tools.paths.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=320x180:rate=12:duration=2",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=550:duration=2",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "libvpx-vp9",
                "-deadline",
                "realtime",
                "-cpu-used",
                "8",
                "-c:a",
                "libvorbis",
                "-f",
                "dash",
                "-dash_segment_type",
                "webm",
                "-init_seg_name",
                "webm_init_$RepresentationID$.webm",
                "-media_seg_name",
                "webm_chunk_$RepresentationID$_$Number%05d$.webm",
                "-adaptation_sets",
                "id=0,streams=v id=1,streams=a",
                webm_manifest.name,
            ],
            cwd=str(source),
            shell=False,
            check=True,
        )
        handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(source), **kwargs)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/manifest.mpd"
            service = YtDlpDownloadService(tools, ProcessManager(), logger)
            progress = []
            states = []
            result = service.download(
                DownloadTask(url, output, "中文标题_音视频合并", DownloadMode.BEST, proxy=ProxyConfig()),
                progress.append,
                states.append,
                Event(),
            )
            final_file = result.files[-1]
            media = ffprobe(tools, final_file)
            streams = {(item["codec_type"], item["codec_name"]) for item in media.get("streams", [])}
            if not any(kind == "video" for kind, _codec in streams):
                raise AssertionError("合并结果缺少视频流")
            if not any(kind == "audio" for kind, _codec in streams):
                raise AssertionError("合并结果缺少音频流")
            if not progress:
                raise AssertionError("未收到结构化进度")
            print(f"MERGE_FILE={final_file.name}")
            print(f"STREAMS={sorted(streams)}")
            print(f"PROGRESS_EVENTS={len(progress)}")
            print("DASH_SEPARATE_AV_MERGE=PASS")
            print("CHINESE_PATH=PASS")

            mkv_result = service.download(
                DownloadTask(
                    f"http://127.0.0.1:{server.server_port}/{webm_manifest.name}",
                    output,
                    "MKV回退测试",
                    DownloadMode.BEST,
                ),
                lambda _item: None,
                lambda _state: None,
                Event(),
            )
            mkv_file = mkv_result.files[-1]
            mkv_media = ffprobe(tools, mkv_file)
            mkv_streams = {(item["codec_type"], item["codec_name"]) for item in mkv_media.get("streams", [])}
            if mkv_file.suffix.lower() != ".mkv":
                raise AssertionError(f"不兼容 MP4 的 VP9/Vorbis 未回退为 MKV：{mkv_file.name}")
            if ("video", "vp9") not in mkv_streams or ("audio", "vorbis") not in mkv_streams:
                raise AssertionError(f"MKV 编码未保持：{sorted(mkv_streams)}")
            print(f"MKV_FILE={mkv_file.name}")
            print(f"MKV_STREAMS={sorted(mkv_streams)}")
            print("MKV_FALLBACK_NO_REENCODE=PASS")

            cancel_manager = ProcessManager()
            cancel_service = YtDlpDownloadService(tools, cancel_manager, logger)
            cancel_event = Event()
            progress_started = Event()
            cancel_errors: list[BaseException] = []

            def cancel_worker() -> None:
                try:
                    cancel_service.download(
                        DownloadTask(
                            f"http://127.0.0.1:{server.server_port}/slow.mp4",
                            output,
                            "取消测试",
                            DownloadMode.BEST,
                        ),
                        lambda _item: progress_started.set(),
                        lambda _state: None,
                        cancel_event,
                    )
                except BaseException as exc:
                    cancel_errors.append(exc)

            cancel_thread = threading.Thread(target=cancel_worker, daemon=True)
            cancel_thread.start()
            if not progress_started.wait(8):
                raise AssertionError("取消测试未开始下载")
            cancel_event.set()
            cancel_manager.cancel()
            cancel_thread.join(timeout=10)
            if cancel_thread.is_alive() or cancel_manager.running:
                raise AssertionError("取消后下载进程仍在运行")
            if not cancel_errors or not isinstance(cancel_errors[0], DownloadCancelled):
                raise AssertionError(f"取消结果不正确：{cancel_errors}")
            cancel_service.remove_partial_files(output)
            if list(output.glob("*.part")):
                raise AssertionError("取消后仍有未清理的 .part 文件")
            print("CANCEL_PROCESS_TREE=PASS")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
