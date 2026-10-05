"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StageOut(BaseModel):
    name: str
    label: str
    status: str
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class AnalysisFiles(BaseModel):
    result: bool = False
    midi: bool = False
    musicxml: bool = False
    pdf: bool = False


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recording_id: str
    status: str
    mode: str
    stage: str | None
    stage_message: str | None
    progress: float
    stages: list[StageOut]
    engine: str
    engine_label: str | None = None
    options: dict[str, Any]
    transcription_status: str | None
    transcription_message: str | None
    warnings: list[str]
    error: str | None
    bpm: float | None
    key: str | None
    time_signature: str | None
    note_count: int | None
    chord_count: int | None
    section_count: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    files: AnalysisFiles = Field(default_factory=AnalysisFiles)


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_filename: str
    file_ext: str
    content_type: str | None
    size_bytes: int
    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    has_video: bool
    audio_codec: str | None
    created_at: datetime
    updated_at: datetime
    playback_ready: bool = False
    latest_analysis: AnalysisOut | None = None


class RecordingDetail(RecordingOut):
    analyses: list[AnalysisOut] = Field(default_factory=list)


class RecordingUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class AnalyzeRequest(BaseModel):
    engine: str | None = None


class RenotateRequest(BaseModel):
    """Overrides for re-engraving without re-running the transcription model."""

    bpm: float | None = Field(default=None, gt=20, lt=320)
    time_signature: str | None = Field(default=None, pattern=r"^(4/4|3/4|2/4|12/8|6/8)$")
    key: str | None = Field(default=None, max_length=20)
    hand_split: int | None = Field(default=None, ge=36, le=84)
    subdivisions: int | None = Field(default=None, ge=1, le=8)
    chord_symbols: bool | None = None
    downbeat_shift: int | None = Field(default=None, ge=-11, le=11)


class EngineOut(BaseModel):
    id: str
    label: str
    description: str
    piano_specific: bool
    available: bool
    reason: str | None
    install_hint: str | None
    details: dict[str, Any]
    is_default: bool


class ToolStatus(BaseModel):
    available: bool
    path: str | None = None
    version: str | None = None


class WorkerOut(BaseModel):
    worker_id: str
    pid: int
    hostname: str
    started_at: datetime
    last_seen: datetime
    current_analysis_id: str | None


class SystemStatus(BaseModel):
    app: str = "PianoScribe AI"
    version: str
    ffmpeg: ToolStatus
    musescore: ToolStatus
    engines: list[EngineOut]
    default_engine: str
    workers: list[WorkerOut]
    worker_online: bool
    queue: dict[str, int]
    data_dir: str
    torch_device: str
    allowed_extensions: list[str]
    max_upload_mb: int
