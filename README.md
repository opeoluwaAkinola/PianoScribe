# PianoScribe AI

A private, local web app that turns recordings of piano performances into:

| Output | How |
| --- | --- |
| **Piano notes** (pitch, onset, length, velocity, sustain pedal) | AI transcription model (pluggable – ByteDance piano model by default) |
| **MIDI** | Exact performance timing *plus* a tempo map that follows the beat, so bars line up in a DAW |
| **MusicXML** | Quantised two-staff piano score with key/time signature, tempo and chord symbols |
| **Printable sheet music** | Rendered in the browser (OpenSheetMusicDisplay) → Print / Save as PDF; direct PDF if MuseScore is installed |
| **Chord progression** | Beat-by-beat chord recognition (from the notes, or from audio) with chord names, Roman numerals and Nashville numbers |
| **Tempo / BPM** | Beat tracking + tempo curve |
| **Key** | Key-profile correlation, re-ranked by functional harmony (ii–V–I etc.) |
| **Time signature** | Accent-periodicity analysis (4/4, 3/4, 12/8) – overridable |
| **Song sections** | Bar-level self-similarity segmentation (A / B / A …, Intro/Outro) |
| **Piano roll** | Interactive canvas with chord/section/pedal lanes, synced to playback |

Upload **MP3, WAV, M4A, FLAC, MP4 or MOV**. Everything runs and stays on your computer.

> This is a personal project: there are deliberately no accounts, payments, billing or other SaaS features.

---

## Quick start

Requirements: **Python 3.11+**, **Node.js 20+**, macOS/Linux. ffmpeg is bundled (via `imageio-ffmpeg`), so you
don't need to install it.

```bash
./setup.sh      # one-time: Python venv, packages, AI model (~1 GB incl. PyTorch), frontend packages
./dev.sh        # starts API + worker + web UI
```

Open **http://localhost:3456**. (The API runs on **:8484**, interactive docs at http://localhost:8484/docs.)
Ports are configurable: `API_PORT=8585 WEB_PORT=3737 ./dev.sh`.

`./setup.sh --no-ml` skips PyTorch. Tempo, key, chords (from audio) and sections still work; notes, MIDI and
sheet music then need a transcription engine.

Check your setup at any time:

```bash
cd backend && .venv/bin/python -m app.cli doctor
```

---

## Using it

1. **Upload** a recording on the Library page (drag & drop). Pick a transcription engine if you have several.
2. Watch the **live progress** – each stage reports what it found (e.g. “76 BPM · 4/4”, “Transcribing segment 7/11”).
3. Explore the result:
   - **Transport** – play the original **recording**, a synthesised rendering of the **transcription**, or **both**
     at once to judge accuracy by ear. Space bar toggles playback.
   - **Piano roll** – zoom (Ctrl/⌘ + scroll), click to seek, colour by hand or velocity, hover for note details.
   - **Sheet music** – zoom, print / save as PDF.
   - **Chords** – lead-sheet style chord chart grouped by section; toggle C·Dm7 / I·ii7 / 1·2m7.
   - **Sections**, **Notes** (the raw transcription), **Downloads** (MIDI, MusicXML, PDF, JSON, original).
4. **Notation settings** – if the detector got the meter, tempo (double/half time), key or bar-line phase wrong,
   correct it and **re-engrave**. This reuses the transcribed notes, so it takes seconds rather than re-running the
   model. Every run is kept in the version history.

---

## How it works

```
                ┌──────────── decode (ffmpeg) ────────────┐
upload ─► queue ┤                                          ├─► tempo / beats / meter ─┐
                └─► AI piano transcription ─► notes ──────┘                           │
                                                 │                                    ▼
                                                 ├─► key ─► chords ─► key refinement ─► sections
                                                 └─► MIDI (tempo-mapped) ─► MusicXML ─► PDF (optional)
```

* **Queue / worker** – analyses are rows in SQLite; a worker process claims them atomically
  (`UPDATE … RETURNING`). No Redis needed. Interrupted jobs are re-queued when the worker restarts.
* **Graceful degradation** – each stage is isolated. If the transcription engine isn't installed or fails, the
  audio-only analyses still complete and the UI says exactly what's missing. **Nothing is ever faked.**
* **The score clock** (`analysis/beatgrid.py`) maps seconds ↔ beats using the detected beats as anchors, so a
  live performance's tempo drift doesn't push bar lines out of sync. MIDI, MusicXML, the chord chart and the piano
  roll all share it.

### Accuracy – what to expect

* The default model (ByteDance, Kong et al. 2021) was trained on **solo concert piano (MAESTRO)**; reported note
  onset F1 ≈ 96.7 % there. On a synthetic gospel ii–V–I test signal it scored **F1 0.95** in this repo's tests.
  Phone recordings, heavy reverb, band/vocals or other instruments will lower accuracy.
* Tempo, meter and sections are signal-processing heuristics and report a confidence. Meter detection covers
  4/4, 3/4 and 12/8 (compound feel); 2/4 and 6/8 can be set manually.
* Sheet music is deliberately *simplified*: one voice per staff, notes split between hands at a pitch (middle C by
  default). The raw performance is always in the MIDI file and the Notes tab.
* Rhythm quantisation (`notation/quantize.py`) is adaptive: chords played slightly unevenly are merged, quick slides
  become grace notes, very quiet blips are dropped, and each beat uses the simplest grid that fits (quarter, 8ths, 16ths
  or triplets). 16ths and triplets are only favoured when the performance as a whole shows them, so loose timing in a
  straight piece doesn't produce stray tuplets. On a real 3-minute gospel recording this cut rests from 134 to 13 and
  16th-or-shorter fragments from 356 to 128 versus plain 16th-note rounding. You can force a fixed grid in Notation
  settings.
* Section labels are letters (A, B, …) because naming “verse/chorus” from audio alone would be guesswork.

---

## Transcription engines (pluggable)

| id | Engine | Notes |
| --- | --- | --- |
| `bytedance` *(default)* | ByteDance High-Resolution Piano Transcription | Piano-specific, with pedal detection. `requirements-ml.txt`. ~0.5× real-time on an M2 CPU. |
| `basic_pitch` | Spotify Basic Pitch | Lightweight, instrument-agnostic; no pedal. `pip install basic-pitch` (check its supported Python versions). |
| `external_cli` | Any command-line model | Set `PIANOSCRIBE_EXTERNAL_CLI_COMMAND="transkun {input} {output}"` – anything that writes a MIDI file works. |

Set the default with `PIANOSCRIBE_TRANSCRIPTION_ENGINE` in `backend/.env` (see `.env.example`).

### Adding a model

```python
# backend/app/transcription/my_model.py
class MyModelEngine(TranscriptionEngine):
    id = "my_model"
    label = "My model"
    description = "What it is and when to use it."
    piano_specific = True

    @classmethod
    def availability(cls, settings):            # cheap: no model loading here
        ok = importlib.util.find_spec("my_model") is not None
        return EngineAvailability(ok, reason=None if ok else "pip install my-model")

    def transcribe(self, audio_path, progress):  # audio_path: 44.1 kHz mono WAV
        events = my_model.run(audio_path, on_progress=lambda f: progress(f, None))
        return TranscriptionOutput(notes=[Note(p, on, off, vel) for p, on, off, vel in events])
```

Register it in `backend/app/transcription/registry.py`. Everything downstream (chords, MIDI, MusicXML, UI) works
unchanged.

---

## Development data

`/dev/sample` (linked from *Engines & system*) renders the full results UI from a **synthetic fixture**: hand-written
notes rendered with a test synthesiser. It is labelled as development data on the page and in its JSON, and exists
only for UI work. Regenerate it with:

```bash
cd backend && .venv/bin/python -m app.devtools.make_dev_fixture
```

---

## Project layout

```
backend/
  app/
    main.py                FastAPI app (CORS, routers, optional embedded worker)
    config.py              settings (env vars prefixed PIANOSCRIBE_)
    models.py db.py        SQLAlchemy models (Recording, Analysis, WorkerHeartbeat) on SQLite
    api/                   REST endpoints: recordings, analyses, system
    services/              storage (local filesystem), media (ffmpeg), jobs (SQLite queue)
    worker/                background worker (python -m app.worker)
    pipeline/              stage orchestration + progress reporting
    transcription/         engine interface, registry, ByteDance / Basic Pitch / external CLI
    analysis/              tempo & meter, beat grid, key, chords, sections, music theory
    notation/              MIDI (tempo-mapped), rhythm quantiser, MusicXML (music21), PDF (MuseScore)
    devtools/              synthetic test signals + dev fixture generator
    cli.py                 doctor · download-models · transcribe FILE · make-test-audio
  tests/                   pytest: theory, chords/key, beat grid, quantiser, notation, API + worker (incl. real model)
  data/                    (git-ignored) database, uploads, results, model checkpoints
frontend/
  src/app/                 Next.js App Router pages: library, recording, print, engines, dev sample
  src/components/          results views (piano roll, sheet music, chords…), playback, shadcn/ui
  src/lib/                 API client, types, beat clock, playback controller, synth
```

### Useful commands

```bash
cd backend
.venv/bin/python -m pytest                       # backend tests (real ffmpeg, DSP and – if installed – the model)
.venv/bin/python -m app.cli transcribe song.m4a  # run the whole pipeline from the terminal
.venv/bin/python -m app.cli make-test-audio      # synthetic WAV with known notes, for testing
.venv/bin/python -m ruff check app tests

cd frontend
npm run lint && npx tsc --noEmit && npm run build
```

### Configuration (`backend/.env`)

| Variable | Default | |
| --- | --- | --- |
| `PIANOSCRIBE_TRANSCRIPTION_ENGINE` | `bytedance` | default engine for new uploads |
| `PIANOSCRIBE_TORCH_DEVICE` | `cpu` | `cpu`, `mps`, `cuda`, `auto` (on an M2, CPU measured faster than MPS for this model) |
| `PIANOSCRIBE_EXTERNAL_CLI_COMMAND` | – | e.g. `transkun {input} {output}` |
| `PIANOSCRIBE_DATA_DIR` | `backend/data` | uploads, results, database, models |
| `PIANOSCRIBE_EMBEDDED_WORKER` | `false` | run the worker inside the API process |
| `PIANOSCRIBE_MUSESCORE_PATH` | auto-detect | enables direct PDF export |
| `PIANOSCRIBE_MAX_UPLOAD_MB` | `2048` | |

The frontend reads `NEXT_PUBLIC_API_URL` (default `http://localhost:8484`).

---

## Troubleshooting

* **“Worker not running”** in the header – start it: `cd backend && .venv/bin/python -m app.worker` (`./dev.sh` does
  this, and restarts the worker automatically when backend code changes).
* **Port in use** – `API_PORT=… WEB_PORT=… ./dev.sh`.
* **Model download fails with a certificate error** – the app uses `certifi`'s CA bundle; make sure
  `pip install certifi` succeeded, or run `/Applications/Python 3.x/Install Certificates.command`.
* **No PDF button** – install MuseScore 4, or use *Print / save as PDF* in the sheet-music view.

## Later: going public

Not built (by design), but the seams are there: storage is behind `services/storage.py` (swap for S3), the queue
behind `services/jobs.py` (swap for Redis/RQ/Celery), engines behind `transcription/registry.py`, and the database URL
is configurable (Postgres). Auth and per-user ownership would be added as a `user_id` on `Recording` plus an API
dependency.
