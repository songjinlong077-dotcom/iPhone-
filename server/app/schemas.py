from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class MediaFormatResponse(BaseModel):
    height: int
    label: str


class MediaResponse(BaseModel):
    url: str
    title: str
    uploader: str
    platform: str
    duration: float | None
    thumbnail_url: str
    formats: list[MediaFormatResponse]


class TaskCreateRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    resolution: int | None = Field(default=None, ge=144, le=8640)
    mode: Literal["best", "compatible_mp4"] = "best"


class TaskResponse(BaseModel):
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
    has_file: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    attempt: int


class HealthResponse(BaseModel):
    status: str
    version: str
