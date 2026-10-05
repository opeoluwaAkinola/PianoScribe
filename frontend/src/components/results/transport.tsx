"use client"

import { Pause, Play, SkipBack } from "lucide-react"
import { useEffect } from "react"

import { usePlayback, usePlaybackState, usePlaybackTime } from "@/components/playback/playback-provider"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatTime, prettyAccidentals } from "@/lib/format"
import type { BeatClock } from "@/lib/music"
import type { PlaybackMode } from "@/lib/playback"
import type { ChordSegment } from "@/lib/types"

export function Transport({
  hasAudio,
  hasNotes,
  clock,
  chords,
}: {
  hasAudio: boolean
  hasNotes: boolean
  clock: BeatClock | null
  chords: ChordSegment[]
}) {
  const playback = usePlayback()
  const state = usePlaybackState()
  const time = usePlaybackTime(20)
  const duration = state.duration

  // Space toggles playback (unless typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (e.code !== "Space" || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable) return
      if (target.closest("[role=dialog]")) return
      e.preventDefault()
      playback.toggle()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [playback])

  useEffect(() => {
    if (!hasAudio && state.mode !== "transcription" && hasNotes) void playback.setMode("transcription")
  }, [hasAudio, hasNotes, state.mode, playback])

  const chord = chords.find((c) => time >= c.start && time < c.end)
  const canPlay = hasAudio ? state.audioReady || !!state.audioError : hasNotes

  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-3 shadow-xs sm:flex-row sm:items-center">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => playback.seek(0)} aria-label="Back to start">
          <SkipBack />
        </Button>
        <Button size="icon-lg" className="rounded-full" onClick={() => playback.toggle()} disabled={!canPlay} aria-label={state.playing ? "Pause" : "Play"}>
          {state.playing ? <Pause /> : <Play />}
        </Button>
      </div>
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="w-14 text-right font-mono text-xs tabular-nums">{formatTime(time)}</span>
        <Slider
          value={[Math.min(time, duration || 0)]}
          max={duration || 1}
          step={0.05}
          onValueChange={([v]) => playback.seek(v)}
          className="flex-1"
          aria-label="Seek"
        />
        <span className="w-14 font-mono text-xs text-muted-foreground tabular-nums">{formatTime(duration)}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden min-w-28 text-sm lg:block">
          {clock && (
            <span className="text-muted-foreground tabular-nums">
              {clock.timeToBeat(time) < 0
                ? "Count-in"
                : `Bar ${clock.barAt(time)}.${Math.floor(clock.beatInBar(time)) + 1}`}
            </span>
          )}
          {chord && chord.root && <span className="ml-2 font-semibold">{prettyAccidentals(chord.label)}</span>}
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <ToggleGroup
              type="single"
              size="sm"
              variant="outline"
              value={state.mode}
              onValueChange={(v) => v && void playback.setMode(v as PlaybackMode)}
            >
              <ToggleGroupItem value="recording" disabled={!hasAudio}>
                Recording
              </ToggleGroupItem>
              <ToggleGroupItem value="transcription" disabled={!hasNotes}>
                Transcription
              </ToggleGroupItem>
              <ToggleGroupItem value="both" disabled={!hasAudio || !hasNotes}>
                Both
              </ToggleGroupItem>
            </ToggleGroup>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            Play the original recording, a synthesised rendering of the transcribed notes, or both together to check
            accuracy by ear.
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  )
}
