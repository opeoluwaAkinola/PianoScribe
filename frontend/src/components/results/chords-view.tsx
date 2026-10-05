"use client"

import { useMemo } from "react"

import { usePlayback, usePlaybackTime } from "@/components/playback/playback-provider"
import { type ChordDisplay, sectionColorIndex } from "@/components/results/piano-roll"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatTime, prettyAccidentals } from "@/lib/format"
import type { BeatClock } from "@/lib/music"
import type { ChordSegment, KeyResult, SectionResult } from "@/lib/types"
import { cn } from "@/lib/utils"

export function chordText(c: ChordSegment, display: ChordDisplay): string {
  if (!c.root) return "N.C."
  if (display === "roman") return c.roman ?? c.label
  if (display === "nashville") return c.nashville ?? c.label
  return prettyAccidentals(c.label)
}

interface BarCell {
  index: number
  t0: number
  t1: number
  items: { chord: ChordSegment; from: number; to: number; continues: boolean }[]
}

export function ChordsView({
  chords,
  source,
  sections,
  clock,
  barCount,
  keyInfo,
  display,
}: {
  chords: ChordSegment[]
  source: string | null
  sections: SectionResult[]
  clock: BeatClock | null
  barCount: number
  keyInfo: KeyResult | null
  display: ChordDisplay
}) {
  const playback = usePlayback()
  const time = usePlaybackTime(8)
  const bpb = clock?.beatsPerBar ?? 4

  const bars: BarCell[] = useMemo(() => {
    if (!clock) return []
    // Lay chords out on a half-beat grid so tiny timing offsets don't create
    // slivers in neighbouring bars.
    const snap = (b: number) => Math.round(b * 2) / 2
    const snapped = chords
      .map((c) => ({ chord: c, s: snap(c.start_beat), e: snap(c.end_beat) }))
      .filter((x) => x.e > x.s)
    return Array.from({ length: barCount }, (_, i) => {
      const b0 = i * bpb
      const b1 = b0 + bpb
      const items = snapped
        .filter((x) => x.e > b0 && x.s < b1)
        .map((x) => ({
          chord: x.chord,
          from: Math.max(x.s, b0) - b0,
          to: Math.min(x.e, b1) - b0,
          continues: x.s < b0,
        }))
      return { index: i + 1, t0: clock.beatToTime(b0), t1: clock.beatToTime(b1), items }
    })
  }, [chords, clock, barCount, bpb])

  // Group bars into sections for a lead-sheet style chart.
  const groups = useMemo(() => {
    if (!sections.length) return [{ section: null as SectionResult | null, bars }]
    return sections.map((s) => ({
      section: s,
      bars: bars.filter((b) => b.index >= s.start_bar && b.index <= Math.max(s.start_bar, s.end_bar)),
    }))
  }, [sections, bars])

  const vocabulary = useMemo(() => {
    const m = new Map<string, { chord: ChordSegment; count: number; seconds: number }>()
    for (const c of chords) {
      if (!c.root) continue
      const e = m.get(c.label) ?? { chord: c, count: 0, seconds: 0 }
      e.count++
      e.seconds += c.end - c.start
      m.set(c.label, e)
    }
    return [...m.values()].sort((a, b) => b.seconds - a.seconds)
  }, [chords])

  const currentBar = clock ? clock.barAt(time) : -1

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Chord chart</CardTitle>
          <CardDescription>
            Detected from {source === "notes" ? "the transcribed notes" : "the audio chromagram"} beat by beat
            {keyInfo ? `, spelled in ${keyInfo.label}` : ""}. Click a chord to jump there.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {!clock ? (
            <p className="text-sm text-muted-foreground">No beat grid available.</p>
          ) : (
            groups.map(({ section, bars: gbars }, gi) => (
              <div key={gi} className="space-y-2">
                {section && (
                  <div className="flex items-center gap-2 text-xs font-medium">
                    <span className="size-2.5 rounded-sm" style={{ background: `var(--section-${sectionColorIndex(section.letter) + 1})` }} />
                    {section.label}
                    <span className="font-normal text-muted-foreground">
                      bars {section.start_bar}–{section.end_bar} · {formatTime(section.start)}
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-2 overflow-hidden rounded-lg border sm:grid-cols-4 xl:grid-cols-8">
                  {gbars.map((bar) => (
                    <div
                      key={bar.index}
                      className={cn(
                        "relative -mr-px -mb-px flex h-16 flex-col border-r border-b",
                        bar.index === currentBar && "bg-primary/10",
                      )}
                    >
                      <span className="absolute top-1 left-1.5 text-[10px] text-muted-foreground tabular-nums">{bar.index}</span>
                      <div className="relative mt-4 flex flex-1">
                        {bar.items.length === 0 && (
                          <button
                            className="flex-1 px-2 text-left text-sm text-muted-foreground"
                            onClick={() => playback.seek(bar.t0)}
                          >
                            –
                          </button>
                        )}
                        {bar.items.map(({ chord, from, to, continues }, i) => (
                          <button
                            key={i}
                            onClick={() => playback.seek(Math.max(chord.start, bar.t0))}
                            style={{ flexGrow: Math.max(0.5, to - from) }}
                            className={cn(
                              "min-w-0 basis-0 truncate rounded px-1.5 text-left text-sm font-semibold hover:bg-muted",
                              continues && "font-normal text-muted-foreground/70",
                              !chord.root && "font-normal text-muted-foreground",
                              time >= chord.start && time < chord.end && "text-primary",
                            )}
                            title={`${chord.label} · ${chord.roman ?? ""} · ${formatTime(chord.start, true)}`}
                          >
                            {continues ? (chord.root ? "·" : "") : chordText(chord, display)}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chord vocabulary</CardTitle>
          <CardDescription>Every chord found, ordered by how long it sounds.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {vocabulary.length === 0 && <p className="text-sm text-muted-foreground">No chords detected.</p>}
          {vocabulary.map(({ chord, count, seconds }) => (
            <Badge key={chord.label} variant="secondary" className="h-auto gap-2 py-1 text-sm">
              <span className="font-semibold">{prettyAccidentals(chord.label)}</span>
              <span className="text-xs text-muted-foreground">
                {chord.roman} · {count}× · {seconds.toFixed(0)} s
              </span>
            </Badge>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
