"use client"

import { Crosshair, ZoomIn, ZoomOut } from "lucide-react"
import { useTheme } from "next-themes"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { usePlayback } from "@/components/playback/playback-provider"
import { Button } from "@/components/ui/button"
import { Toggle } from "@/components/ui/toggle"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { formatTime, prettyAccidentals } from "@/lib/format"
import { type BeatClock, isBlackKey, midiToName } from "@/lib/music"
import type { ChordSegment, NoteEvent, PedalEvent, SectionResult } from "@/lib/types"

export type ChordDisplay = "label" | "roman" | "nashville"

const KEYBOARD_W = 56
const RULER_H = 18
const SECTION_H = 18
const CHORD_H = 22
const PEDAL_H = 10
const TOP = RULER_H + SECTION_H + CHORD_H

interface Palette {
  bg: string
  rowAlt: string
  grid: string
  gridStrong: string
  text: string
  muted: string
  rh: string
  lh: string
  playhead: string
  laneBg: string
  sections: string[]
  keyWhite: string
  keyBlack: string
  keyActive: string
}

function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  return {
    bg: v("--roll-bg"),
    rowAlt: v("--roll-row-alt"),
    grid: v("--roll-grid"),
    gridStrong: v("--roll-grid-strong"),
    text: v("--roll-text"),
    muted: v("--roll-muted"),
    rh: v("--note-rh"),
    lh: v("--note-lh"),
    playhead: v("--playhead"),
    laneBg: v("--roll-lane"),
    sections: [1, 2, 3, 4, 5, 6].map((i) => v(`--section-${i}`)),
    keyWhite: v("--key-white"),
    keyBlack: v("--key-black"),
    keyActive: v("--key-active"),
  }
}

export function sectionColorIndex(letter: string): number {
  return (letter.charCodeAt(0) - 65) % 6
}

interface Props {
  notes: NoteEvent[]
  pedals?: PedalEvent[]
  duration: number
  clock: BeatClock | null
  chords: ChordSegment[]
  sections: SectionResult[]
  handSplit?: number
  fifths: number
  chordDisplay: ChordDisplay
  height?: number
}

export function PianoRoll({
  notes,
  pedals = [],
  duration,
  clock,
  chords,
  sections,
  handSplit = 60,
  fifths,
  chordDisplay,
  height = 480,
}: Props) {
  const playback = usePlayback()
  const { resolvedTheme } = useTheme()
  const scrollerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const keysRef = useRef<HTMLCanvasElement>(null)
  const paletteRef = useRef<Palette | null>(null)
  const frame = useRef(0)
  const [width, setWidth] = useState(800)
  const [pps, setPps] = useState(90) // pixels per second
  const [follow, setFollow] = useState(true)
  const [colorBy, setColorBy] = useState<"hand" | "velocity">("hand")
  const [hover, setHover] = useState<{ x: number; y: number; note: NoteEvent } | null>(null)

  const sorted = useMemo(() => [...notes].sort((a, b) => a.start - b.start), [notes])
  const maxDur = useMemo(() => sorted.reduce((m, n) => Math.max(m, n.end - n.start), 0), [sorted])
  const [lo, hi] = useMemo(() => {
    if (!sorted.length) return [48, 84]
    let mn = 127
    let mx = 0
    for (const n of sorted) {
      mn = Math.min(mn, n.pitch)
      mx = Math.max(mx, n.pitch)
    }
    let a = Math.max(21, mn - 2)
    let b = Math.min(108, mx + 2)
    while (b - a < 30) {
      if (a > 21) a--
      if (b < 108 && b - a < 30) b++
      if (a === 21 && b === 108) break
    }
    return [a, b]
  }, [sorted])

  const rollH = height - TOP - (pedals.length ? PEDAL_H : 0)
  const rowH = rollH / (hi - lo + 1)
  const contentW = Math.max(width, duration * pps + 40)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const keys = keysRef.current
    const scroller = scrollerRef.current
    if (!canvas || !keys || !scroller) return
    const pal = (paletteRef.current ??= readPalette())
    const dpr = window.devicePixelRatio || 1
    const W = width
    const H = height
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
      canvas.width = Math.round(W * dpr)
      canvas.height = Math.round(H * dpr)
    }
    if (keys.width !== Math.round(KEYBOARD_W * dpr) || keys.height !== Math.round(H * dpr)) {
      keys.width = Math.round(KEYBOARD_W * dpr)
      keys.height = Math.round(H * dpr)
    }
    const ctx = canvas.getContext("2d")!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const now = playback.getTime()

    // Follow the playhead while playing.
    if (follow && playback.playing) {
      const px = now * pps - scroller.scrollLeft
      if (px > W * 0.85 || px < 0) scroller.scrollLeft = Math.max(0, now * pps - W * 0.15)
    }
    const t0 = scroller.scrollLeft / pps
    const t1 = t0 + W / pps
    const X = (t: number) => (t - t0) * pps
    const Y = (p: number) => TOP + (hi - p) * rowH

    ctx.fillStyle = pal.bg
    ctx.fillRect(0, 0, W, H)

    // Pitch rows
    for (let p = lo; p <= hi; p++) {
      if (isBlackKey(p)) {
        ctx.fillStyle = pal.rowAlt
        ctx.fillRect(0, Y(p), W, rowH)
      }
      if (p % 12 === 0) {
        ctx.fillStyle = pal.gridStrong
        ctx.fillRect(0, Y(p) + rowH - 0.5, W, 1)
      }
    }

    // Lanes background
    ctx.fillStyle = pal.laneBg
    ctx.fillRect(0, 0, W, TOP)

    // Beat / bar grid + ruler
    ctx.font = "10px var(--font-sans), system-ui, sans-serif"
    ctx.textBaseline = "middle"
    if (clock) {
      const bpb = clock.beatsPerBar
      const b0 = Math.floor(clock.timeToBeat(Math.max(0, t0)))
      const b1 = Math.ceil(clock.timeToBeat(Math.min(duration, t1)))
      const beatPx = pps * Math.max(0.05, clock.beatToTime(b0 + 1) - clock.beatToTime(b0))
      const barEvery = Math.max(1, Math.ceil(36 / (beatPx * bpb)))
      for (let b = b0; b <= b1; b++) {
        const t = clock.beatToTime(b)
        if (t < 0 || t > duration) continue
        const x = X(t)
        const isBar = ((b % bpb) + bpb) % bpb === 0
        if (isBar) {
          ctx.fillStyle = pal.gridStrong
          ctx.fillRect(x, RULER_H, 1, H - RULER_H)
          const bar = Math.floor(b / bpb) + 1
          if (bar >= 1 && (bar - 1) % barEvery === 0) {
            ctx.fillStyle = pal.muted
            ctx.fillText(String(bar), x + 3, RULER_H / 2)
          }
        } else if (beatPx > 7) {
          ctx.fillStyle = pal.grid
          ctx.fillRect(x, TOP, 1, H - TOP)
        }
      }
    } else {
      const step = pps > 60 ? 1 : pps > 20 ? 5 : 15
      for (let s = Math.floor(t0 / step) * step; s <= t1; s += step) {
        const x = X(s)
        ctx.fillStyle = pal.grid
        ctx.fillRect(x, RULER_H, 1, H - RULER_H)
        ctx.fillStyle = pal.muted
        ctx.fillText(formatTime(s), x + 3, RULER_H / 2)
      }
    }

    // Sections lane
    for (const s of sections) {
      if (s.end < t0 || s.start > t1) continue
      const x = X(s.start)
      const w = (s.end - s.start) * pps
      ctx.fillStyle = pal.sections[sectionColorIndex(s.letter)]
      ctx.globalAlpha = 0.85
      ctx.fillRect(x + 1, RULER_H + 2, w - 2, SECTION_H - 4)
      ctx.globalAlpha = 1
      ctx.fillStyle = "#fff"
      ctx.save()
      ctx.beginPath()
      ctx.rect(x + 1, RULER_H, w - 2, SECTION_H)
      ctx.clip()
      ctx.font = "600 10px var(--font-sans), system-ui, sans-serif"
      ctx.fillText(s.label, Math.max(x, 0) + 6, RULER_H + SECTION_H / 2)
      ctx.restore()
    }

    // Chord lane
    ctx.font = "600 11px var(--font-sans), system-ui, sans-serif"
    let alt = false
    for (const c of chords) {
      if (c.end < t0 || c.start > t1) {
        alt = !alt
        continue
      }
      const x = X(c.start)
      const w = (c.end - c.start) * pps
      const active = now >= c.start && now < c.end
      ctx.fillStyle = active ? pal.playhead : alt ? pal.rowAlt : pal.bg
      ctx.globalAlpha = active ? 0.25 : 1
      ctx.fillRect(x, RULER_H + SECTION_H + 1, w, CHORD_H - 2)
      ctx.globalAlpha = 1
      alt = !alt
      const text = c.root == null ? "N.C." : (chordDisplay === "roman" ? c.roman : chordDisplay === "nashville" ? c.nashville : prettyAccidentals(c.label)) ?? c.label
      ctx.save()
      ctx.beginPath()
      ctx.rect(x, RULER_H + SECTION_H, w, CHORD_H)
      ctx.clip()
      ctx.fillStyle = c.root == null ? pal.muted : pal.text
      ctx.fillText(text, Math.max(x, 0) + 4, RULER_H + SECTION_H + CHORD_H / 2)
      ctx.restore()
    }
    ctx.fillStyle = pal.gridStrong
    ctx.fillRect(0, TOP - 1, W, 1)

    // Pedal lane
    if (pedals.length) {
      const py = H - PEDAL_H
      ctx.fillStyle = pal.laneBg
      ctx.fillRect(0, py, W, PEDAL_H)
      ctx.fillStyle = pal.muted
      for (const p of pedals) {
        if (p.end < t0 || p.start > t1) continue
        ctx.fillRect(X(p.start), py + 3, Math.max(1, (p.end - p.start) * pps), PEDAL_H - 5)
      }
    }

    // Notes
    const active = new Set<number>()
    let i = 0
    let hiIdx = sorted.length
    const from = t0 - maxDur
    while (i < hiIdx) {
      const mid = (i + hiIdx) >> 1
      if (sorted[mid].start < from) i = mid + 1
      else hiIdx = mid
    }
    for (; i < sorted.length; i++) {
      const n = sorted[i]
      if (n.start > t1) break
      if (n.end < t0) continue
      const x = X(n.start)
      const w = Math.max(2, (n.end - n.start) * pps - 1)
      const y = Y(n.pitch) + 0.5
      const h = Math.max(2, rowH - 1)
      const isActive = now >= n.start && now < n.end
      if (isActive) active.add(n.pitch)
      const vel = n.velocity / 127
      ctx.fillStyle = colorBy === "hand" ? (n.pitch >= handSplit ? pal.rh : pal.lh) : `hsl(${260 - vel * 220} 80% 55%)`
      ctx.globalAlpha = isActive ? 1 : colorBy === "hand" ? 0.45 + 0.55 * vel : 0.9
      const r = Math.min(3, h / 2, w / 2)
      ctx.beginPath()
      ctx.roundRect(x, y, w, h, r)
      ctx.fill()
      if (isActive) {
        ctx.globalAlpha = 1
        ctx.strokeStyle = pal.text
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }
    ctx.globalAlpha = 1

    // Playhead
    const px = X(now)
    if (px >= 0 && px <= W) {
      ctx.fillStyle = pal.playhead
      ctx.fillRect(px - 0.75, 0, 1.5, H)
    }

    // Keyboard
    const k = keys.getContext("2d")!
    k.setTransform(dpr, 0, 0, dpr, 0, 0)
    k.fillStyle = pal.laneBg
    k.fillRect(0, 0, KEYBOARD_W, H)
    k.font = "9px var(--font-sans), system-ui, sans-serif"
    k.textBaseline = "middle"
    for (let p = lo; p <= hi; p++) {
      const y = Y(p)
      const black = isBlackKey(p)
      k.fillStyle = active.has(p) ? pal.keyActive : black ? pal.keyBlack : pal.keyWhite
      k.fillRect(black ? 0 : 0, y, black ? KEYBOARD_W * 0.62 : KEYBOARD_W, rowH)
      k.fillStyle = pal.grid
      k.fillRect(0, y + rowH - 0.5, KEYBOARD_W, 0.5)
      if (p % 12 === 0 && rowH >= 5) {
        k.fillStyle = pal.muted
        k.fillText(midiToName(p), KEYBOARD_W - 24, y + rowH / 2)
      }
    }
    k.fillStyle = pal.gridStrong
    k.fillRect(KEYBOARD_W - 1, 0, 1, H)
  }, [width, height, pps, follow, colorBy, sorted, maxDur, lo, hi, rowH, clock, chords, sections, pedals, duration, handSplit, chordDisplay, playback])

  const requestDraw = useCallback(() => {
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(draw)
  }, [draw])

  useEffect(() => {
    paletteRef.current = null
    requestDraw()
  }, [resolvedTheme, requestDraw])

  useEffect(() => playback.subscribe(requestDraw), [playback, requestDraw])
  useEffect(() => requestDraw(), [requestDraw])
  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const zoom = useCallback(
    (factor: number, anchorX?: number) => {
      const el = scrollerRef.current
      if (!el) return
      const ax = anchorX ?? el.clientWidth / 2
      const tAnchor = (el.scrollLeft + ax) / pps
      const next = Math.min(600, Math.max(8, pps * factor))
      setPps(next)
      requestAnimationFrame(() => {
        el.scrollLeft = Math.max(0, tAnchor * next - ax)
      })
    },
    [pps],
  )

  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        const rect = el.getBoundingClientRect()
        zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - rect.left)
      }
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [zoom])

  const hitTest = (clientX: number, clientY: number) => {
    const el = scrollerRef.current!
    const rect = el.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    const t = (el.scrollLeft + x) / pps
    return { x, y, t }
  }

  const onClick = (e: React.MouseEvent) => {
    const { t } = hitTest(e.clientX, e.clientY)
    playback.seek(Math.min(duration, Math.max(0, t)))
  }

  const onMove = (e: React.MouseEvent) => {
    const { x, y, t } = hitTest(e.clientX, e.clientY)
    if (y < TOP) return setHover(null)
    const pitch = Math.round(hi - (y - TOP - rowH / 2) / rowH)
    const n = sorted.find((n) => n.pitch === pitch && t >= n.start && t <= n.end)
    setHover(n ? { x, y, note: n } : null)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" onClick={() => zoom(1 / 1.4)} aria-label="Zoom out">
            <ZoomOut />
          </Button>
          <Button variant="outline" size="icon-sm" onClick={() => zoom(1.4)} aria-label="Zoom in">
            <ZoomIn />
          </Button>
        </div>
        <Toggle size="sm" variant="outline" pressed={follow} onPressedChange={setFollow} aria-label="Follow playhead">
          <Crosshair /> Follow
        </Toggle>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={colorBy}
          onValueChange={(v) => v && setColorBy(v as "hand" | "velocity")}
        >
          <ToggleGroupItem value="hand">By hand</ToggleGroupItem>
          <ToggleGroupItem value="velocity">By velocity</ToggleGroupItem>
        </ToggleGroup>
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {colorBy === "hand" ? (
            <>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm" style={{ background: "var(--note-rh)" }} /> Right hand (≥{" "}
                {midiToName(handSplit, fifths)})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm" style={{ background: "var(--note-lh)" }} /> Left hand
              </span>
            </>
          ) : (
            <span className="flex items-center gap-1.5">
              soft
              <span className="h-2.5 w-16 rounded-sm" style={{ background: "linear-gradient(90deg, hsl(260 80% 55%), hsl(40 80% 55%))" }} />
              loud
            </span>
          )}
          <span className="hidden md:inline">Ctrl/⌘ + scroll to zoom · click to seek</span>
        </div>
      </div>

      <div className="relative flex overflow-hidden rounded-lg border" style={{ height }}>
        <canvas ref={keysRef} style={{ width: KEYBOARD_W, height }} className="shrink-0" />
        <div
          ref={scrollerRef}
          className="relative flex-1 overflow-x-auto overflow-y-hidden"
          onScroll={requestDraw}
          onClick={onClick}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <div style={{ width: contentW, height: height - 1 }}>
            <canvas
              ref={canvasRef}
              className="sticky left-0 top-0 block cursor-crosshair"
              style={{ width, height }}
            />
          </div>
          {hover && (
            <div
              className="pointer-events-none absolute z-10 rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md"
              style={{ left: Math.min(hover.x + 12, width - 150) + (scrollerRef.current?.scrollLeft ?? 0), top: hover.y + 12 }}
            >
              <div className="font-semibold">{midiToName(hover.note.pitch, fifths)}</div>
              <div className="text-muted-foreground">
                {formatTime(hover.note.start, true)} · {((hover.note.end - hover.note.start) * 1000).toFixed(0)} ms · vel{" "}
                {hover.note.velocity}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
