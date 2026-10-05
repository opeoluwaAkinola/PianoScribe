"use client"

import { CircleCheck, CircleX, Copy, FlaskConical, Server, TriangleAlert } from "lucide-react"
import Link from "next/link"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useSystem } from "@/hooks/use-api"
import { API_URL } from "@/lib/api"
import { formatRelative } from "@/lib/format"

function Command({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 font-mono text-xs">
      <code className="flex-1 overflow-x-auto whitespace-pre">{children}</code>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={() => {
          void navigator.clipboard.writeText(children)
          toast.success("Copied")
        }}
        aria-label="Copy command"
      >
        <Copy />
      </Button>
    </div>
  )
}

function Ok({ ok }: { ok: boolean }) {
  return ok ? <CircleCheck className="size-4 text-emerald-600 dark:text-emerald-400" /> : <CircleX className="size-4 text-muted-foreground" />
}

export default function EnginesPage() {
  const { data, error } = useSystem()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Engines &amp; system</h1>
        <p className="text-sm text-muted-foreground">
          The transcription engine is pluggable: anything that turns audio into note events can be connected.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <Server />
          <AlertTitle>Backend not reachable</AlertTitle>
          <AlertDescription>
            <p>
              Tried <code className="font-mono">{API_URL}</code>. Start it with <code className="font-mono">./dev.sh</code>.
            </p>
          </AlertDescription>
        </Alert>
      )}

      {!data && !error && <Skeleton className="h-64 w-full" />}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Ok ok={data.worker_online} /> Background worker
                </CardTitle>
                <CardDescription>
                  {data.worker_online
                    ? `${data.workers.length} online · ${data.queue.queued} queued · ${data.queue.running} running`
                    : "Not running – uploads will wait in the queue."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                {data.workers.map((w) => (
                  <div key={w.worker_id}>
                    {w.worker_id} · seen {formatRelative(w.last_seen)}
                    {w.current_analysis_id ? " · busy" : ""}
                  </div>
                ))}
                {!data.worker_online && <Command>cd backend && .venv/bin/python -m app.worker</Command>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Ok ok={data.ffmpeg.available} /> ffmpeg
                </CardTitle>
                <CardDescription>Decodes MP3, WAV, M4A, FLAC, MP4 and MOV.</CardDescription>
              </CardHeader>
              <CardContent className="text-xs break-all text-muted-foreground">
                {data.ffmpeg.available ? `v${data.ffmpeg.version} · ${data.ffmpeg.path}` : "Not found. Install with: brew install ffmpeg"}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Ok ok={data.musescore.available} /> MuseScore <Badge variant="outline">optional</Badge>
                </CardTitle>
                <CardDescription>Direct PDF export of the sheet music.</CardDescription>
              </CardHeader>
              <CardContent className="text-xs break-all text-muted-foreground">
                {data.musescore.available
                  ? data.musescore.path
                  : "Not installed. Printing from the sheet-music view works without it (Print → Save as PDF)."}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Transcription engines</CardTitle>
              <CardDescription>
                Default: <span className="font-medium text-foreground">{data.engines.find((e) => e.is_default)?.label}</span>{" "}
                (set <code className="font-mono">PIANOSCRIBE_TRANSCRIPTION_ENGINE</code> in <code className="font-mono">backend/.env</code>
                ). Torch device: <code className="font-mono">{data.torch_device}</code>.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.engines.map((e) => (
                <div key={e.id} className="space-y-2 rounded-lg border p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Ok ok={e.available} />
                    <span className="font-medium">{e.label}</span>
                    <code className="font-mono text-xs text-muted-foreground">{e.id}</code>
                    {e.is_default && <Badge>default</Badge>}
                    {e.piano_specific && <Badge variant="secondary">piano-specific</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">{e.description}</p>
                  {e.reason && (
                    <p className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400">
                      <TriangleAlert className="size-3.5" /> {e.reason}
                    </p>
                  )}
                  {e.install_hint && <Command>{e.install_hint}</Command>}
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                To connect another model, add a class in <code className="font-mono">backend/app/transcription/</code> implementing{" "}
                <code className="font-mono">TranscriptionEngine</code> and register it in <code className="font-mono">registry.py</code>, or
                point the External command engine at any CLI that writes a MIDI file.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FlaskConical className="size-4" /> UI preview with development data
              </CardTitle>
              <CardDescription>
                A synthetic sample (generated from a known note list, not a transcription) for working on the interface.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" size="sm" asChild>
                <Link href="/dev/sample">Open development sample</Link>
              </Button>
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            PianoScribe AI v{data.version} · data stored in <code className="font-mono">{data.data_dir}</code>
          </p>
        </>
      )}
    </div>
  )
}
