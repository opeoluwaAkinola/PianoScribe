"use client"

import { usePlayback, usePlaybackTime } from "@/components/playback/playback-provider"
import { sectionColorIndex } from "@/components/results/piano-roll"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatTime } from "@/lib/format"
import type { SectionResult } from "@/lib/types"
import { cn } from "@/lib/utils"

export function SectionsView({ sections, duration }: { sections: SectionResult[]; duration: number }) {
  const playback = usePlayback()
  const time = usePlaybackTime(8)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Song sections</CardTitle>
        <CardDescription>
          Found by grouping bars with similar harmony and texture. Sections that sound alike share a letter; names like
          “verse” or “chorus” can&apos;t be reliably inferred from audio alone, so they aren&apos;t guessed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex h-10 w-full overflow-hidden rounded-lg border">
          {sections.map((s, i) => {
            const active = time >= s.start && time < s.end
            return (
              <button
                key={i}
                onClick={() => playback.seek(s.start)}
                className={cn(
                  "relative flex min-w-0 items-center justify-center truncate px-1 text-xs font-semibold text-white transition-opacity",
                  !active && "opacity-75 hover:opacity-100",
                )}
                style={{
                  width: `${((s.end - s.start) / duration) * 100}%`,
                  background: `var(--section-${sectionColorIndex(s.letter) + 1})`,
                }}
                title={`${s.label} · ${formatTime(s.start)}–${formatTime(s.end)}`}
              >
                {s.label === "Intro" || s.label === "Outro" ? s.label : s.letter}
              </button>
            )
          })}
        </div>
        <div className="divide-y rounded-lg border">
          {sections.map((s, i) => {
            const active = time >= s.start && time < s.end
            return (
              <button
                key={i}
                onClick={() => playback.seek(s.start)}
                className={cn("flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-muted/50", active && "bg-primary/5")}
              >
                <span
                  className="flex size-7 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white"
                  style={{ background: `var(--section-${sectionColorIndex(s.letter) + 1})` }}
                >
                  {s.letter}
                </span>
                <span className="flex-1 font-medium">{s.label}</span>
                <span className="text-muted-foreground tabular-nums">
                  bars {s.start_bar}–{s.end_bar}
                </span>
                <span className="w-28 text-right text-muted-foreground tabular-nums">
                  {formatTime(s.start)} – {formatTime(s.end)}
                </span>
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
