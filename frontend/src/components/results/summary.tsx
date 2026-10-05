"use client"

import { Activity, Clock, Cpu, Gauge, KeyRound, Layers, ListMusic, Music } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatTime, pct } from "@/lib/format"
import type { AnalysisResult } from "@/lib/types"
import { cn } from "@/lib/utils"

function Stat({
  icon: Icon,
  label,
  value,
  sub,
  tip,
  muted,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  tip?: React.ReactNode
  muted?: boolean
}) {
  const body = (
    <Card className="gap-0 py-0">
      <CardContent className="p-4">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Icon className="size-3.5" />
          {label}
        </div>
        <div className={cn("mt-1.5 truncate text-xl font-semibold tracking-tight tabular-nums", muted && "text-muted-foreground")}>
          {value}
        </div>
        {sub && <div className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  )
  if (!tip) return body
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div>{body}</div>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  )
}

function confidenceWord(c: number) {
  return c >= 0.75 ? "high confidence" : c >= 0.5 ? "medium confidence" : "low confidence"
}

export function Summary({ result }: { result: AnalysisResult }) {
  const { tempo, key, transcription } = result
  const chords = result.chords.segments.filter((c) => c.root)
  const uniqueChords = new Set(chords.map((c) => c.label)).size
  const transcribed = transcription.status === "completed"

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
      <Stat
        icon={KeyRound}
        label="Key"
        value={key?.label ?? "–"}
        sub={key ? `${confidenceWord(key.confidence)} · from ${key.source}` : undefined}
        tip={
          key && (
            <div className="space-y-1">
              <div>
                Estimated by correlating the {key.source === "notes" ? "transcribed notes" : "audio chromagram"} with key
                profiles{key.refined_by_chords ? ", then re-ranked using the chord progression" : ""}.
              </div>
              {key.alternatives.length > 0 && (
                <div>Alternatives: {key.alternatives.map((a) => a.label).join(", ")}</div>
              )}
            </div>
          )
        }
      />
      <Stat
        icon={Gauge}
        label="Tempo"
        value={
          <>
            {Math.round(tempo.bpm)} <span className="text-sm font-normal text-muted-foreground">BPM</span>
          </>
        }
        sub={tempo.fallback ? "no steady beat found" : tempo.stability < 0.04 ? "steady" : tempo.stability < 0.1 ? "some rubato" : "free tempo"}
        tip={`Median of ${tempo.beat_count} detected beats${tempo.compound ? " (dotted-quarter pulse)" : ""}. Tempo variation: ${pct(tempo.stability)}.`}
      />
      <Stat
        icon={Activity}
        label="Time signature"
        value={tempo.time_signature}
        sub={confidenceWord(tempo.meter_confidence)}
        tip="Estimated from periodic accents (onsets, bass notes and chord changes). Override it in Notation settings if it's wrong."
      />
      <Stat icon={Clock} label="Duration" value={formatTime(result.duration)} sub={`${tempo.bar_count ?? "–"} bars`} />
      <Stat
        icon={Music}
        label="Notes"
        value={transcribed ? result.notes.length.toLocaleString() : "–"}
        sub={transcribed ? `${result.pedals.length} pedal events` : "no transcription"}
        muted={!transcribed}
      />
      <Stat
        icon={ListMusic}
        label="Chords"
        value={chords.length}
        sub={`${uniqueChords} distinct · from ${result.chords.source ?? "–"}`}
      />
      <Stat icon={Layers} label="Sections" value={result.sections.length} sub={[...new Set(result.sections.map((s) => s.letter))].join(" ")} />
      <Stat
        icon={Cpu}
        label="Engine"
        value={<span className="text-base">{transcription.engine_label ?? transcription.engine ?? "–"}</span>}
        sub={
          transcribed
            ? `${transcription.elapsed_sec ?? "?"} s · ${(transcription.details?.device as string) ?? ""}`
            : transcription.status
        }
        tip={transcription.model ?? transcription.message ?? undefined}
        muted={!transcribed}
      />
    </div>
  )
}
