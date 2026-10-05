"""Model -> schema conversion (adds file availability from storage)."""

from __future__ import annotations

from app.models import Analysis, Recording
from app.schemas import AnalysisFiles, AnalysisOut, RecordingDetail, RecordingOut
from app.services.storage import LocalStorage
from app.transcription.registry import ENGINES


def analysis_out(a: Analysis, storage: LocalStorage) -> AnalysisOut:
    def has(name: str) -> bool:
        return storage.analysis_file(a.recording_id, a.id, name).exists()

    out = AnalysisOut.model_validate(a)
    out.engine_label = ENGINES[a.engine].label if a.engine in ENGINES else a.engine
    out.files = AnalysisFiles(
        result=has(LocalStorage.RESULT_FILE),
        midi=has(LocalStorage.MIDI_FILE),
        musicxml=has(LocalStorage.MUSICXML_FILE),
        pdf=has(LocalStorage.PDF_FILE),
    )
    return out


def recording_out(r: Recording, storage: LocalStorage) -> RecordingOut:
    out = RecordingOut.model_validate(r, from_attributes=True)
    out.playback_ready = storage.playback_path(r.id).exists()
    out.latest_analysis = analysis_out(r.latest_analysis, storage) if r.latest_analysis else None
    return out


def recording_detail(r: Recording, storage: LocalStorage) -> RecordingDetail:
    base = recording_out(r, storage)
    return RecordingDetail(
        **base.model_dump(exclude={"latest_analysis"}),
        latest_analysis=base.latest_analysis,
        analyses=[analysis_out(a, storage) for a in r.analyses],
    )
