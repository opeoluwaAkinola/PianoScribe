"""ORM models.

Large analysis outputs (notes, chords, beats…) live in ``result.json`` on disk;
the database only keeps metadata, job state and a few summary fields.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC datetimes and always returns timezone-aware ones.

    SQLite has no timezone support, so without this values read back naive.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class AnalysisStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ACTIVE = (QUEUED, RUNNING)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(500))
    file_ext: Mapped[str] = mapped_column(String(10))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
        order_by="Analysis.created_at.desc()",
    )

    @property
    def latest_analysis(self) -> Analysis | None:
        return self.analyses[0] if self.analyses else None


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=AnalysisStatus.QUEUED, index=True)
    # "full" runs every stage; "renotate" reuses notes/beats and redoes notation.
    mode: Mapped[str] = mapped_column(String(20), default="full")
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stage_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    engine: Mapped[str] = mapped_column(String(50))
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    transcription_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transcription_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Summary fields (denormalised from result.json for list views)
    bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    time_signature: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chord_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    recording: Mapped[Recording] = relationship(back_populates="analyses")


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    pid: Mapped[int] = mapped_column(Integer)
    hostname: Mapped[str] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    current_analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
