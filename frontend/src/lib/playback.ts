import { PianoSynth } from "@/lib/synth"
import type { NoteEvent } from "@/lib/types"

export type PlaybackMode = "recording" | "transcription" | "both"

/**
 * One clock for everything: the original recording (an <audio> element) when
 * available, otherwise an internal clock. The transcription synth is scheduled
 * against that clock with a short look-ahead, so recording and transcription
 * can be played together for A/B comparison.
 *
 * Components subscribe instead of re-rendering through React state on every
 * animation frame.
 */
export class PlaybackController {
  private audio: HTMLAudioElement | null = null
  private synth: PianoSynth | null = null
  private notes: NoteEvent[] = []
  private listeners = new Set<() => void>()
  private raf = 0
  private scheduler: ReturnType<typeof setInterval> | null = null
  private scheduledUntil = 0
  private nextIdx = 0
  private internalStartPerf = 0
  private internalOffset = 0

  duration = 0
  playing = false
  mode: PlaybackMode = "recording"
  audioReady = false
  audioError: string | null = null

  attachAudio(src: string | null) {
    if (this.audio) {
      this.audio.pause()
      this.audio.removeAttribute("src")
      this.audio.load()
    }
    this.audioReady = false
    this.audioError = null
    if (!src) {
      this.audio = null
      this.emit()
      return
    }
    const a = new Audio()
    a.preload = "auto"
    a.src = src
    a.muted = this.mode === "transcription"
    a.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(a.duration)) this.duration = Math.max(this.duration, a.duration)
      this.audioReady = true
      this.emit()
    })
    a.addEventListener("ended", () => this.pause())
    a.addEventListener("error", () => {
      this.audioError = "Audio unavailable"
      this.audioReady = false
      this.emit()
    })
    this.audio = a
  }

  setNotes(notes: NoteEvent[], duration: number) {
    this.notes = [...notes].sort((x, y) => x.start - y.start)
    this.duration = Math.max(this.duration, duration)
    this.resetSchedule(this.getTime())
  }

  hasTranscription() {
    return this.notes.length > 0
  }

  private usesAudioClock() {
    return !!this.audio && this.audioReady
  }

  getTime(): number {
    if (this.usesAudioClock()) return this.audio!.currentTime
    if (!this.playing) return this.internalOffset
    return this.internalOffset + (performance.now() - this.internalStartPerf) / 1000
  }

  async play() {
    if (this.playing) return
    if (this.mode !== "recording" && this.notes.length) {
      this.synth ??= new PianoSynth()
      await this.synth.resume()
      this.synth.setVolume(1)
    }
    const t = this.getTime()
    if (t >= this.duration - 0.05) this.seek(0)
    if (this.usesAudioClock()) {
      this.audio!.muted = this.mode === "transcription"
      try {
        await this.audio!.play()
      } catch {
        return
      }
    } else {
      this.internalStartPerf = performance.now()
    }
    this.playing = true
    this.resetSchedule(this.getTime())
    this.startLoops()
    this.emit()
  }

  pause() {
    if (!this.playing) return
    if (!this.usesAudioClock()) this.internalOffset = this.getTime()
    this.audio?.pause()
    this.playing = false
    this.synth?.stopAll()
    this.stopLoops()
    this.emit()
  }

  toggle() {
    if (this.playing) this.pause()
    else void this.play()
  }

  seek(t: number) {
    const clamped = Math.max(0, Math.min(t, this.duration || t))
    if (this.usesAudioClock()) this.audio!.currentTime = clamped
    this.internalOffset = clamped
    this.internalStartPerf = performance.now()
    this.synth?.stopAll()
    this.resetSchedule(clamped)
    this.emit()
  }

  async setMode(mode: PlaybackMode) {
    this.mode = mode
    if (this.audio) this.audio.muted = mode === "transcription"
    if (mode === "recording") this.synth?.stopAll()
    else if (this.playing && this.notes.length) {
      this.synth ??= new PianoSynth()
      await this.synth.resume()
      this.resetSchedule(this.getTime())
    }
    this.emit()
  }

  subscribe(cb: () => void): () => void {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  destroy() {
    this.stopLoops()
    this.audio?.pause()
    this.synth?.close()
    this.listeners.clear()
  }

  // --- internals -------------------------------------------------------------
  private emit() {
    this.listeners.forEach((cb) => cb())
  }

  private resetSchedule(from: number) {
    this.scheduledUntil = from
    let lo = 0
    let hi = this.notes.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (this.notes[mid].start < from) lo = mid + 1
      else hi = mid
    }
    this.nextIdx = lo
  }

  private schedule() {
    if (!this.playing || this.mode === "recording" || !this.synth) return
    const now = this.getTime()
    const ctxNow = this.synth.ctx.currentTime
    const horizon = now + 0.2
    while (this.nextIdx < this.notes.length && this.notes[this.nextIdx].start < horizon) {
      const n = this.notes[this.nextIdx++]
      if (n.start < now - 0.05) continue
      const when = ctxNow + Math.max(0, n.start - now)
      this.synth.note(n.pitch, n.velocity, when, n.end - n.start)
    }
    this.scheduledUntil = horizon
  }

  private startLoops() {
    this.stopLoops()
    const tick = () => {
      if (!this.usesAudioClock() && this.getTime() >= this.duration) {
        this.pause()
        this.internalOffset = this.duration
        this.emit()
        return
      }
      this.emit()
      this.raf = requestAnimationFrame(tick)
    }
    this.raf = requestAnimationFrame(tick)
    this.scheduler = setInterval(() => this.schedule(), 25)
    this.schedule()
  }

  private stopLoops() {
    cancelAnimationFrame(this.raf)
    if (this.scheduler) clearInterval(this.scheduler)
    this.scheduler = null
  }
}
