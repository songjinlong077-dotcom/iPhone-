from __future__ import annotations

import os
import json
import shutil
import signal
import subprocess
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Settings
from .db import TaskRecord, TaskRepository
from .security import validate_public_url
from .tools import Toolchain


class TaskConflictError(RuntimeError):
    pass


class DownloadTaskManager:
    PROGRESS_PREFIX = "V4PROGRESS|"
    RESULT_PREFIX = "V4RESULT|"

    def __init__(self, settings: Settings, repository: TaskRepository, tools: Toolchain) -> None:
        self.settings = settings
        self.repository = repository
        self.tools = tools
        self.tasks_dir = settings.data_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="download")
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
        self._futures: dict[str, Future[None]] = {}
        self.repository.recover_interrupted()

    def close(self) -> None:
        with self._lock:
            ids = list(self._processes)
        for task_id in ids:
            self.cancel(task_id)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def create(self, url: str, resolution: int | None, mode: str) -> TaskRecord:
        clean = validate_public_url(url)
        self.cleanup_expired()
        task_id = uuid.uuid4().hex
        record = self.repository.create(task_id=task_id, url=clean, resolution=resolution, mode=mode)
        with self._lock:
            self._futures[task_id] = self._executor.submit(self._run, task_id)
        return record

    def retry(self, task_id: str) -> TaskRecord:
        record = self.repository.get(task_id)
        if not record:
            raise KeyError(task_id)
        if record.status not in {"failed", "cancelled", "expired"}:
            raise TaskConflictError("只有失败、取消或过期的任务可以重试。")
        task_dir = self._task_dir(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir)
        with self._lock:
            self._cancelled.discard(task_id)
        updated = self.repository.update(
            task_id, status="queued", progress=0, downloaded_bytes=0, total_bytes=None,
            speed_bytes=None, eta_seconds=None, error=None, file_path=None, expires_at=None,
            attempt=record.attempt + 1,
        )
        with self._lock:
            self._futures[task_id] = self._executor.submit(self._run, task_id)
        assert updated is not None
        return updated

    def cancel(self, task_id: str) -> TaskRecord:
        record = self.repository.get(task_id)
        if not record:
            raise KeyError(task_id)
        if record.status in {"completed", "failed", "cancelled", "expired"}:
            return record
        with self._lock:
            self._cancelled.add(task_id)
            process = self._processes.get(task_id)
            future = self._futures.get(task_id)
        if future and future.cancel():
            updated = self.repository.update(task_id, status="cancelled", error=None)
            assert updated is not None
            return updated
        if process:
            self._terminate(process)
        updated = self.repository.update(task_id, status="cancelled", error=None)
        assert updated is not None
        return updated

    def delete(self, task_id: str) -> bool:
        record = self.repository.get(task_id)
        if not record:
            return False
        if record.status in {"queued", "downloading", "merging"}:
            raise TaskConflictError("运行中的任务必须先取消。")
        task_dir = self._task_dir(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir)
        return self.repository.delete(task_id)

    def file_for(self, record: TaskRecord) -> Path:
        if record.status != "completed" or not record.file_path:
            raise FileNotFoundError("任务还没有可下载文件。")
        path = Path(record.file_path).resolve()
        root = self._task_dir(record.id).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("任务文件不存在或路径无效。")
        return path

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        removed = 0
        for record in self.repository.list(limit=500):
            if record.status != "completed" or not record.expires_at:
                continue
            try:
                expires = datetime.fromisoformat(record.expires_at)
            except ValueError:
                continue
            if expires <= now:
                task_dir = self._task_dir(record.id)
                if task_dir.exists():
                    shutil.rmtree(task_dir)
                self.repository.update(record.id, status="expired", file_path=None)
                removed += 1
        return removed

    def _task_dir(self, task_id: str) -> Path:
        if not task_id.isalnum():
            raise ValueError("无效任务编号。")
        return self.tasks_dir / task_id

    def _build_command(self, record: TaskRecord, task_dir: Path) -> list[str]:
        height = f"[height<={record.resolution}]" if record.resolution else ""
        if record.mode == "compatible_mp4":
            selector = f"bv*[ext=mp4]{height}+ba[ext=m4a]/b[ext=mp4]{height}/b{height}"
            merge_format = "mp4"
        else:
            selector = f"bv*{height}+ba/b{height}"
            merge_format = "mp4/mkv"
        return [
            str(self.tools.ytdlp), "--no-playlist", "--newline", "--no-color", "--progress",
            "--encoding", "utf-8", "--socket-timeout", "30", "--max-filesize",
            str(self.settings.max_file_bytes), "--ffmpeg-location", str(self.tools.ffmpeg.parent),
            "--progress-template",
            "download:V4PROGRESS|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s",
            "--print", "before_dl:V4META|%(title)j|%(extractor_key)j",
            "--print", "post_process:V4STAGE|merging",
            "--print", "after_move:V4RESULT|%(filepath)s",
            "-f", selector, "--merge-output-format", merge_format,
            "-P", str(task_dir), "-o", "%(title).150B [%(id)s].%(ext)s", record.url,
        ]

    @staticmethod
    def _number(value: str, caster):
        try:
            return None if value in {"", "NA", "None", "null"} else caster(value)
        except (TypeError, ValueError):
            return None

    def _run(self, task_id: str) -> None:
        record = self.repository.get(task_id)
        if not record:
            return
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        process: subprocess.Popen[str] | None = None
        try:
            self.repository.update(task_id, status="analyzing", error=None)
            process = subprocess.Popen(
                self._build_command(record, task_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1,
                shell=False, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                start_new_session=os.name != "nt",
            )
            with self._lock:
                self._processes[task_id] = process
            result_path: Path | None = None
            output: list[str] = []
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.rstrip()
                with self._lock:
                    cancelled = task_id in self._cancelled
                if cancelled:
                    self._terminate(process)
                    break
                if line.startswith(self.PROGRESS_PREFIX):
                    parts = line.split("|")
                    if len(parts) >= 7:
                        downloaded = self._number(parts[2], int) or 0
                        total = self._number(parts[3], int) or self._number(parts[4], int)
                        progress = min(100.0, downloaded / total * 100) if total else 0.0
                        self.repository.update(
                            task_id, status="downloading", progress=progress, downloaded_bytes=downloaded, total_bytes=total,
                            speed_bytes=self._number(parts[5], float), eta_seconds=self._number(parts[6], int),
                        )
                elif line.startswith("V4META|"):
                    parts = line.split("|", 2)
                    if len(parts) == 3:
                        try:
                            title = str(json.loads(parts[1]) or "")
                            platform = str(json.loads(parts[2]) or "")
                        except (json.JSONDecodeError, TypeError):
                            title, platform = "", ""
                        self.repository.update(task_id, status="downloading", title=title[:500], platform=platform[:100])
                elif line == "V4STAGE|merging":
                    self.repository.update(task_id, status="merging")
                elif line.startswith(self.RESULT_PREFIX):
                    result_path = Path(line[len(self.RESULT_PREFIX):])
                else:
                    output.append(line)
            return_code = process.wait()
            with self._lock:
                cancelled = task_id in self._cancelled
            if cancelled:
                self.repository.update(task_id, status="cancelled", error=None)
                return
            if return_code != 0:
                detail = next((line for line in reversed(output) if line.strip()), "yt-dlp 下载失败")
                raise RuntimeError(detail[:500])
            if result_path and not result_path.is_absolute():
                result_path = task_dir / result_path
            if not result_path or not result_path.is_file():
                candidates = [p for p in task_dir.iterdir() if p.is_file() and p.suffix not in {".part", ".ytdl"}]
                result_path = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
            if not result_path:
                raise RuntimeError("下载完成但没有找到输出文件。")
            expires = datetime.now(UTC) + timedelta(hours=self.settings.retention_hours)
            self.repository.update(
                task_id, status="completed", progress=100.0, file_path=str(result_path.resolve()),
                expires_at=expires.isoformat(timespec="seconds"), error=None,
            )
        except Exception as exc:
            with self._lock:
                cancelled = task_id in self._cancelled
            safe_error = str(exc).replace(record.url, "<url>")[:500]
            self.repository.update(task_id, status="cancelled" if cancelled else "failed", error=None if cancelled else safe_error)
        finally:
            with self._lock:
                self._processes.pop(task_id, None)
                self._futures.pop(task_id, None)
                self._cancelled.discard(task_id)
            if process and process.stdout:
                process.stdout.close()

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False, shell=False)
            else:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            process.kill()
