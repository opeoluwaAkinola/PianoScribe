"use client"

import { Download, FileAudio, FileJson, FileMusic, FileText, Printer } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export interface DownloadLinks {
  midi?: string | null
  musicxml?: string | null
  pdf?: string | null
  json?: string | null
  original?: string | null
  print?: string | null
}

function Row({
  icon: Icon,
  title,
  description,
  href,
  unavailable,
  action = "Download",
  newTab,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  description: string
  href?: string | null
  unavailable?: string
  action?: string
  newTab?: boolean
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
        <Icon className="size-4.5 text-muted-foreground" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{href ? description : unavailable}</div>
      </div>
      <Button variant="outline" size="sm" asChild={!!href} disabled={!href}>
        {href ? (
          <a href={href} target={newTab ? "_blank" : undefined} rel="noreferrer">
            {action === "Download" ? <Download /> : <Printer />} {action}
          </a>
        ) : (
          <span>
            <Download /> {action}
          </span>
        )}
      </Button>
    </div>
  )
}

export function Downloads({ links }: { links: DownloadLinks }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Downloads</CardTitle>
        <CardDescription>Everything is generated and stored locally on this computer.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y border-t">
          <Row
            icon={FileMusic}
            title="MIDI"
            description="Exact performance timing with a tempo map that follows the beat, so bars line up in your DAW. Includes sustain pedal."
            href={links.midi}
            unavailable="Needs a transcription engine."
          />
          <Row
            icon={FileMusic}
            title="MusicXML"
            description="Quantised two-staff piano score with chord symbols. Opens in MuseScore, Sibelius, Finale, Dorico, Logic…"
            href={links.musicxml}
            unavailable="Needs a transcription engine."
          />
          <Row
            icon={FileText}
            title="PDF sheet music"
            description="Rendered by MuseScore."
            href={links.pdf ?? links.print}
            action={links.pdf ? "Download" : "Print"}
            newTab={!links.pdf}
            unavailable="Needs sheet music. (Install MuseScore for direct PDF export, or use Print.)"
          />
          <Row
            icon={FileJson}
            title="Analysis data (JSON)"
            description="Notes, pedals, beats, tempo curve, key, chords and sections."
            href={links.json}
            unavailable="Not available."
          />
          {links.original !== undefined && (
            <Row icon={FileAudio} title="Original upload" description="The file exactly as uploaded." href={links.original} unavailable="Missing." />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
