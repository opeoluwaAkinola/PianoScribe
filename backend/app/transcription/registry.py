"""Registry of available transcription engines."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.transcription.base import EngineAvailability, TranscriptionEngine
from app.transcription.basic_pitch import BasicPitchEngine
from app.transcription.bytedance import ByteDancePianoEngine
from app.transcription.external_cli import ExternalCliEngine

ENGINES: dict[str, type[TranscriptionEngine]] = {
    e.id: e for e in (ByteDancePianoEngine, BasicPitchEngine, ExternalCliEngine)
}


class UnknownEngine(ValueError):
    pass


def get_engine_class(engine_id: str) -> type[TranscriptionEngine]:
    try:
        return ENGINES[engine_id]
    except KeyError as exc:
        raise UnknownEngine(f"Unknown transcription engine: {engine_id!r}") from exc


def create_engine(engine_id: str, settings: Settings | None = None) -> TranscriptionEngine:
    return get_engine_class(engine_id)(settings or get_settings())


def default_engine_id(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.transcription_engine if settings.transcription_engine in ENGINES else "bytedance"


def describe_engines(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    default = default_engine_id(settings)
    out = []
    for engine_id, cls in ENGINES.items():
        avail: EngineAvailability = cls.availability(settings)
        out.append(
            {
                "id": engine_id,
                "label": cls.label,
                "description": cls.description,
                "piano_specific": cls.piano_specific,
                "available": avail.available,
                "reason": avail.reason,
                "install_hint": avail.install_hint,
                "details": avail.details,
                "is_default": engine_id == default,
            }
        )
    return out
