import type { BeatGridData } from "@/lib/types"

const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
const NEUTRAL = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

export function pitchClassName(pc: number, fifths = 0): string {
  const table = fifths < 0 ? FLATS : fifths > 0 ? SHARPS : NEUTRAL
  return table[((pc % 12) + 12) % 12]
}

export function midiToName(midi: number, fifths = 0): string {
  return `${pitchClassName(midi, fifths)}${Math.floor(midi / 12) - 1}`
}

export function isBlackKey(midi: number): boolean {
  return [1, 3, 6, 8, 10].includes(((midi % 12) + 12) % 12)
}

export const KEY_OPTIONS: string[] = [
  ...["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"].map((t) => `${t} major`),
  ...["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"].map((t) => `${t} minor`),
]

/**
 * Client-side copy of the backend BeatGrid (seconds <-> beat position), so the
 * piano roll, chord chart and sections agree with the engraved bar numbers.
 */
export class BeatClock {
  private t: number[]
  private b: number[]
  readonly beatsPerBar: number
  readonly compound: boolean

  constructor(grid: BeatGridData) {
    const bt = grid.beat_times
    this.beatsPerBar = grid.beats_per_bar
    this.compound = grid.compound
    const med = (xs: number[]) => {
      const s = [...xs].sort((a, b) => a - b)
      return s[Math.floor(s.length / 2)] ?? 0.5
    }
    const diffs = (xs: number[]) => xs.slice(1).map((x, i) => x - xs[i])
    const ibiFirst = med(diffs(bt.slice(0, 5))) || 0.5
    const ibiLast = med(diffs(bt.slice(-5))) || 0.5
    const pos = bt.map((_, i) => grid.lead_in + i)
    const t = [...bt]
    const b = [...pos]
    if (bt[0] > 0) {
      t.unshift(0)
      b.unshift(pos[0] - bt[0] / ibiFirst)
    }
    const end = Math.max(grid.duration, bt[bt.length - 1]) + 4 * ibiLast
    t.push(end)
    b.push(pos[pos.length - 1] + (end - bt[bt.length - 1]) / ibiLast)
    this.t = t
    this.b = b
  }

  private static interp(x: number, xs: number[], ys: number[]): number {
    if (x <= xs[0]) return ys[0] + ((x - xs[0]) * (ys[1] - ys[0])) / (xs[1] - xs[0] || 1)
    let lo = 0
    let hi = xs.length - 1
    if (x >= xs[hi]) return ys[hi] + ((x - xs[hi]) * (ys[hi] - ys[hi - 1])) / (xs[hi] - xs[hi - 1] || 1)
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (xs[mid] <= x) lo = mid
      else hi = mid
    }
    return ys[lo] + ((x - xs[lo]) * (ys[hi] - ys[lo])) / (xs[hi] - xs[lo] || 1)
  }

  timeToBeat(t: number): number {
    return BeatClock.interp(t, this.t, this.b)
  }

  beatToTime(b: number): number {
    return BeatClock.interp(b, this.b, this.t)
  }

  /** 1-based bar number containing time t (bars before bar 1 clamp to 1). */
  barAt(t: number): number {
    return Math.max(1, Math.floor(this.timeToBeat(t) / this.beatsPerBar + 1e-9) + 1)
  }

  beatInBar(t: number): number {
    const pos = this.timeToBeat(t)
    return ((pos % this.beatsPerBar) + this.beatsPerBar) % this.beatsPerBar
  }
}
