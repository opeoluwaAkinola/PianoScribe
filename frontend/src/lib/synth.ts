/**
 * A small Web Audio "piano-ish" synthesiser used to audition the transcription
 * (so you can A/B it against the original recording). No samples to download.
 */
export class PianoSynth {
  readonly ctx: AudioContext
  private master: GainNode
  private compressor: DynamicsCompressorNode
  private voices = new Set<{ stop: (at: number) => void; end: number }>()

  constructor() {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    this.ctx = new Ctx()
    this.compressor = this.ctx.createDynamicsCompressor()
    this.compressor.threshold.value = -18
    this.compressor.ratio.value = 4
    this.master = this.ctx.createGain()
    this.master.gain.value = 0.5
    this.master.connect(this.compressor).connect(this.ctx.destination)
  }

  async resume() {
    if (this.ctx.state !== "running") await this.ctx.resume()
  }

  setVolume(v: number) {
    this.master.gain.setTargetAtTime(v * 0.5, this.ctx.currentTime, 0.02)
  }

  note(pitch: number, velocity: number, when: number, duration: number) {
    const ctx = this.ctx
    const f0 = 440 * 2 ** ((pitch - 69) / 12)
    const vel = Math.max(0.05, velocity / 127)
    const decay = Math.min(6, Math.max(0.6, 3.2 * Math.sqrt(110 / f0)))

    const out = ctx.createGain()
    out.gain.value = 0
    const filter = ctx.createBiquadFilter()
    filter.type = "lowpass"
    filter.frequency.value = Math.min(16000, f0 * (3 + 9 * vel))
    filter.Q.value = 0.3
    filter.connect(out).connect(this.master)

    const partials: [number, number, OscillatorType][] = [
      [1, 1, "triangle"],
      [2, 0.35 * vel, "sine"],
      [3, 0.12 * vel, "sine"],
    ]
    const oscs = partials.map(([mult, amp, type]) => {
      const o = ctx.createOscillator()
      o.type = type
      o.frequency.value = f0 * mult * (1 + 0.0004 * mult * mult)
      const g = ctx.createGain()
      g.gain.value = amp
      o.connect(g).connect(filter)
      return o
    })

    const peak = 0.25 * vel ** 1.4
    const g = out.gain
    g.setValueAtTime(0, when)
    g.linearRampToValueAtTime(peak, when + 0.005)
    g.setTargetAtTime(peak * 0.25, when + 0.005, decay * 0.35)
    const release = when + Math.max(0.05, duration)
    g.setTargetAtTime(0, release, 0.09)
    const end = release + 0.6
    oscs.forEach((o) => {
      o.start(when)
      o.stop(end)
    })

    const voice = {
      end,
      stop: (at: number) => {
        g.cancelScheduledValues(at)
        g.setTargetAtTime(0, at, 0.02)
        oscs.forEach((o) => {
          try {
            o.stop(at + 0.1)
          } catch {
            /* already stopped */
          }
        })
      },
    }
    this.voices.add(voice)
    oscs[0].onended = () => this.voices.delete(voice)
  }

  stopAll() {
    const now = this.ctx.currentTime
    this.voices.forEach((v) => v.stop(now))
    this.voices.clear()
  }

  close() {
    this.stopAll()
    void this.ctx.close()
  }
}
