from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse

from . import __version__
from .auth import ApiKeyAuth
from .config import Settings
from .db import TaskRecord, TaskRepository
from .media import MediaAnalyzeError, analyze_media
from .schemas import AnalyzeRequest, HealthResponse, MediaResponse, TaskCreateRequest, TaskResponse
from .security import UnsafeUrlError
from .tasks import DownloadTaskManager, TaskConflictError
from .tools import Toolchain


def _task_response(record: TaskRecord) -> TaskResponse:
    return TaskResponse(
        id=record.id, url=record.url, title=record.title, platform=record.platform,
        status=record.status, progress=record.progress, downloaded_bytes=record.downloaded_bytes,
        total_bytes=record.total_bytes, speed_bytes=record.speed_bytes, eta_seconds=record.eta_seconds,
        resolution=record.resolution, mode=record.mode, error=record.error, has_file=record.has_file,
        created_at=record.created_at, updated_at=record.updated_at, expires_at=record.expires_at,
        attempt=record.attempt,
    )


def create_app(settings: Settings | None = None, tools: Toolchain | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    repository = TaskRepository(config.data_dir / "tasks.sqlite3")
    toolchain = tools or Toolchain.discover(config.ytdlp_bin, config.ffmpeg_bin)
    manager = DownloadTaskManager(config, repository, toolchain)
    auth = ApiKeyAuth(config.api_key)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        manager.cleanup_expired()
        yield
        manager.close()

    app = FastAPI(title="Video Downloader V4 API", version=__version__, lifespan=lifespan)
    app.state.settings = config
    app.state.repository = repository
    app.state.manager = manager

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.post("/v1/media/analyze", response_model=MediaResponse, dependencies=[Depends(auth)])
    async def analyze(request: AnalyzeRequest) -> MediaResponse:
        try:
            result = await asyncio.to_thread(analyze_media, request.url, toolchain, config.analyze_timeout_seconds)
            return MediaResponse(**result)
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MediaAnalyzeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/tasks", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(auth)])
    def create_task(request: TaskCreateRequest) -> TaskResponse:
        try:
            return _task_response(manager.create(request.url, request.resolution, request.mode))
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/tasks", response_model=list[TaskResponse], dependencies=[Depends(auth)])
    def list_tasks(limit: int = Query(default=100, ge=1, le=500)) -> list[TaskResponse]:
        manager.cleanup_expired()
        return [_task_response(item) for item in repository.list(limit)]

    @app.get("/v1/tasks/{task_id}", response_model=TaskResponse, dependencies=[Depends(auth)])
    def get_task(task_id: str) -> TaskResponse:
        manager.cleanup_expired()
        record = repository.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="任务不存在。")
        return _task_response(record)

    @app.post("/v1/tasks/{task_id}/cancel", response_model=TaskResponse, dependencies=[Depends(auth)])
    def cancel_task(task_id: str) -> TaskResponse:
        try:
            return _task_response(manager.cancel(task_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在。") from exc

    @app.post("/v1/tasks/{task_id}/retry", response_model=TaskResponse, dependencies=[Depends(auth)])
    def retry_task(task_id: str) -> TaskResponse:
        try:
            return _task_response(manager.retry(task_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在。") from exc
        except TaskConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/tasks/{task_id}/file", dependencies=[Depends(auth)])
    def download_file(task_id: str) -> FileResponse:
        manager.cleanup_expired()
        record = repository.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="任务不存在。")
        try:
            path = manager.file_for(record)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    @app.delete("/v1/tasks/{task_id}", status_code=204, dependencies=[Depends(auth)])
    def delete_task(task_id: str) -> None:
        try:
            if not manager.delete(task_id):
                raise HTTPException(status_code=404, detail="任务不存在。")
        except TaskConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


__all__ = ["create_app", "Settings", "Toolchain"]
