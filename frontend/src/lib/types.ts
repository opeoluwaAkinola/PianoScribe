// Mirrors backend/app/schemas.py and the result.json written by the pipeline.

export type AnalysisStatus = "queued" | "running" | "completed" | "failed" | "cancelled"
export type StageStatus = "pending" | "running" | "done" | "skipped" | "unavailable" | "failed" | "cancelled"

export interface Stage {
  name: string
  label: string
  status: StageStatus
  message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface AnalysisFiles {
  result: boolean
  midi: boolean
  musicxml: boolean
  pdf: boolean
}

export interface NotationOverrides {
  bpm?: number | null
  time_signature?: string | null
  key?: string | null
  hand_split?: number | null
  subdivisions?: number | null
  chord_symbols?: boolean | null
  downbeat_shift?: number | null
}

export interface Analysis {
  id: string
  recording_id: string
  status: AnalysisStatus
  mode: "full" | "renotate"
  stage: string | null
  stage_message: string | null
  progress: number
  stages: Stage[]
  engine: string
  engine_label: string | null
  options: NotationOverrides & { source_analysis_id?: string }
  transcription_status: "completed" | "unavailable" | "failed" | null
  transcription_message: string | null
  warnings: string[]
  error: string | null
  bpm: number | null
  key: string | null
  time_signature: string | null
  note_count: number | null
  chord_count: number | null
  section_count: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  files: AnalysisFiles
}

export interface Recording {
  id: string
  title: string
  original_filename: string
  file_ext: string
  content_type: string | null
  size_bytes: number
  duration_sec: number | null
  sample_rate: number | null
  channels: number | null
  has_video: boolean
  audio_codec: string | null
  created_at: string
  updated_at: string
  playback_ready: boolean
  latest_analysis: Analysis | null
}

export interface RecordingDetail extends Recording {
  analyses: Analysis[]
}

export interface Engine {
  id: string
  label: string
  description: string
  piano_specific: boolean
  available: boolean
  reason: string | null
  install_hint: string | null
  details: Record<string, unknown>
  is_default: boolean
}

export interface SystemStatus {
  app: string
  version: string
  ffmpeg: { available: boolean; path: string | null; version: string | null }
  musescore: { available: boolean; path: string | null; version: string | null }
  engines: Engine[]
  default_engine: string
  workers: {
    worker_id: string
    pid: number
    hostname: string
    started_at: string
    last_seen: string
    current_analysis_id: string | null
  }[]
  worker_online: boolean
  queue: { queued: number; running: number }
  data_dir: string
  torch_device: string
  allowed_extensions: string[]
  max_upload_mb: number
}

// ---- result.json --------------------------------------------------------------

export interface NoteEvent {
  pitch: number
  start: number
  end: number
  velocity: number
}

export interface PedalEvent {
  start: number
  end: number
}

export interface BeatGridData {
  beat_times: number[]
  beats_per_bar: number
  compound: boolean
  lead_in: number
  duration: number
}

export interface TempoResult {
  bpm: number
  time_signature: string
  beats_per_bar: number
  compound: boolean
  meter_confidence: number
  triplet_ratio: number
  stability: number
  beat_count: number
  fallback: boolean
  tempo_curve: { time: number; bpm: number }[]
  grid?: BeatGridData
  beats?: number[]
  downbeats?: number[]
  start_position?: number
  bar_count?: number
}

export interface KeyResult {
  tonic: string
  mode: "major" | "minor"
  label: string
  short: string
  fifths: number
  confidence: number
  source: "notes" | "audio" | "override" | "fallback"
  alternatives: { label: string; short: string; score: number }[]
  histogram: number[]
  refined_by_chords?: boolean
}

export interface ChordSegment {
  start: number
  end: number
  label: string
  root: string | null
  quality: string | null
  bass: string | null
  roman: string | null
  nashville: string | null
  confidence: number
  start_beat: number
  end_beat: number
}

export interface SectionResult {
  start: number
  end: number
  letter: string
  label: string
  start_bar: number
  end_bar: number
}

export interface TranscriptionInfo {
  status?: "completed" | "unavailable" | "failed"
  engine?: string
  engine_label?: string
  model?: string | null
  message?: string | null
  install_hint?: string | null
  note_count?: number
  pedal_count?: number
  elapsed_sec?: number
  details?: Record<string, unknown>
}

export interface AnalysisResult {
  schema_version: number
  analysis_id: string
  recording_id: string
  generated_at: string
  mode: string
  duration: number
  transcription: TranscriptionInfo
  notes: NoteEvent[]
  pedals: PedalEvent[]
  tempo: TempoResult
  key: KeyResult | null
  chords: { source: "notes" | "audio" | null; segments: ChordSegment[] }
  sections: SectionResult[]
  notation: {
    measures?: number
    subdivisions?: number
    hand_split?: number
    chord_symbols?: boolean
    files: { midi: boolean; musicxml: boolean; pdf: boolean }
  }
  options: NotationOverrides
  warnings: string[]
}
