"""API + worker integration tests (real ffmpeg, real DSP, real SQLite)."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from app.analysis.types import Note
from app.devtools.synth import onset_f1
from app.main import app
from app.worker.runner import Worker


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def run_worker():
    Worker().run(once=True)


def upload(client, path, engine=None, title=None):
    data = {}
    if engine:
        data["engine"] = engine
    if title:
        data["title"] = title
    with open(path, "rb") as fh:
        return client.post("/api/recordings", files={"file": (path.name, fh)}, data=data)


def test_health_and_system(client):
    assert client.get("/api/health").json() == {"ok": True}
    sysinfo = client.get("/api/system").json()
    assert sysinfo["ffmpeg"]["available"]
    assert {e["id"] for e in sysinfo["engines"]} >= {"bytedance", "basic_pitch", "external_cli"}


def test_rejects_unsupported_and_corrupt(client, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    assert upload(client, bad).status_code == 415
    fake = tmp_path / "fake.mp3"
    fake.write_bytes(b"not really audio" * 100)
    assert upload(client, fake).status_code == 422


@pytest.mark.parametrize("fmt", ["mp3", "wav", "m4a", "flac", "mp4", "mov"])
def test_every_format_without_transcription_engine(client, media_files, fmt):
    """With no transcription engine available, audio-only analyses still complete
    and the response says plainly that notes/MIDI/sheet music are unavailable."""
    res = upload(client, media_files[fmt], engine="external_cli", title=f"Format {fmt}")
    assert res.status_code == 201, res.text
    rec = res.json()
    assert rec["file_ext"] == fmt
    assert rec["has_video"] == (fmt in ("mp4", "mov"))
    assert rec["latest_analysis"]["status"] == "queued"

    run_worker()

    a = client.get(f"/api/analyses/{rec['latest_analysis']['id']}").json()
    assert a["status"] == "completed", a
    assert a["transcription_status"] == "unavailable"
    assert a["files"] == {"result": True, "midi": False, "musicxml": False, "pdf": False}
    assert 70 <= a["bpm"] <= 82
    result = client.get(f"/api/analyses/{a['id']}/result").json()
    assert result["notes"] == []
    assert result["chords"]["source"] == "audio"
    assert any(w.startswith("AI transcription skipped") for w in result["warnings"])
    assert client.get(f"/api/analyses/{a['id']}/files/midi").status_code == 404

    audio = client.get(f"/api/recordings/{rec['id']}/audio", headers={"Range": "bytes=0-99"})
    assert audio.status_code == 206 and len(audio.content) == 100
    assert client.delete(f"/api/recordings/{rec['id']}").status_code == 204
    assert client.get(f"/api/recordings/{rec['id']}").status_code == 404


ml_ready = (
    importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("piano_transcription_inference") is not None
)


@pytest.mark.skipif(not ml_ready, reason="ML extras not installed (pip install -r requirements-ml.txt)")
def test_full_pipeline_with_real_model(client, media_files, reference_notes):
    from app.config import get_settings
    from app.transcription.bytedance import checkpoint_ready

    if not checkpoint_ready(get_settings()):
        pytest.skip("Model checkpoint not downloaded (python -m app.cli download-models)")

    rec = upload(client, media_files["mov"], engine="bytedance", title="Gospel ii-V-I").json()
    run_worker()
    a = client.get(f"/api/analyses/{rec['latest_analysis']['id']}").json()
    assert a["status"] == "completed", a
    assert a["transcription_status"] == "completed"
    assert a["files"]["midi"] and a["files"]["musicxml"]
    assert a["key"] == "A♭ major"
    assert a["time_signature"] == "4/4"

    result = client.get(f"/api/analyses/{a['id']}/result").json()
    est = [Note.from_dict(n) for n in result["notes"]]
    assert onset_f1(reference_notes, est)["f1"] > 0.85
    labels = [c["label"] for c in result["chords"]["segments"]]
    assert {"Abmaj9", "Fm9", "Eb13"} & set(labels)

    midi = client.get(f"/api/analyses/{a['id']}/files/midi")
    assert midi.status_code == 200 and midi.content[:4] == b"MThd"
    assert "Gospel%20ii-V-I.mid" in midi.headers["content-disposition"]
    xml = client.get(f"/api/analyses/{a['id']}/files/musicxml?download=false")
    assert b"<score-partwise" in xml.content

    # Re-engrave in 3/4 with a different hand split, reusing the notes.
    r = client.post(f"/api/analyses/{a['id']}/renotate", json={"time_signature": "3/4", "hand_split": 55})
    assert r.status_code == 201, r.text
    run_worker()
    b = client.get(f"/api/analyses/{r.json()['id']}").json()
    assert b["status"] == "completed" and b["mode"] == "renotate"
    assert b["time_signature"] == "3/4" and b["note_count"] == a["note_count"]
    detail = client.get(f"/api/recordings/{rec['id']}").json()
    assert detail["latest_analysis"]["id"] == b["id"] and len(detail["analyses"]) == 2
