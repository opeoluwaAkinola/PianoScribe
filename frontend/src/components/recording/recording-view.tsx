"use client"

import { ArrowLeft, Check, CircleX, History, Pencil, Trash2, Video, X } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useSWRConfig } from "swr"

import { AnalysisProgress, StageList } from "@/components/recording/analysis-progress"
import { NotationDialog } from "@/components/recording/notation-dialog"
import { ReanalyzeDialog } from "@/components/recording/reanalyze-dialog"
import { ResultsView } from "@/components/results/results-view"
import { StatusBadge } from "@/components/status-badge"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useRecording, useResult } from "@/hooks/use-api"
import { api, urls } from "@/lib/api"
import { formatBytes, formatDate, formatTime } from "@/lib/format"
import type { Analysis } from "@/lib/types"

function analysisLabel(a: Analysis, index: number) {
  const kind = a.mode === "renotate" ? "Re-engraved" : "Full analysis"
  return `${index === 0 ? "Latest · " : ""}${kind} · ${formatDate(a.created_at)}`
}

function TitleEditor({ id, title, onSaved }: { id: string; title: string; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(title)
  const save = async () => {
    const v = value.trim()
    if (!v || v === title) return setEditing(false)
    try {
      await api.renameRecording(id, v)
      onSaved()
      setEditing(false)
    } catch (e) {
      toast.error("Rename failed", { description: (e as Error).message })
    }
  }
  if (!editing)
    return (
      <div className="group flex min-w-0 items-center gap-2">
        <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
        <Button variant="ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100" onClick={() => {
            setValue(title)
            setEditing(true)
          }}
          aria-label="Rename"
        >
          <Pencil />
        </Button>
      </div>
    )
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Input value={value} onChange={(e) => setValue(e.target.value)} autoFocus className="h-9 max-w-md text-lg" />
      <Button type="submit" size="icon-sm" aria-label="Save">
        <Check />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" onClick={() => setEditing(false)} aria-label="Cancel">
        <X />
      </Button>
    </form>
  )
}

export function RecordingView({ id }: { id: string }) {
  const router = useRouter()
  const { mutate: globalMutate } = useSWRConfig()
  const { data: rec, error, isLoading, mutate } = useRecording(id)
  // A manual pick from the version history stays in effect only until a newer
  // analysis completes; then the view follows the newest result.
  const [selection, setSelection] = useState<{ id: string; base: string | null } | null>(null)
  const [tab, setTab] = useState("roll")

  const analyses = useMemo(() => rec?.analyses ?? [], [rec])
  const active = analyses.find((a) => a.status === "queued" || a.status === "running") ?? null
  const latestCompleted = analyses.find((a) => a.status === "completed") ?? null
  const latest = analyses[0] ?? null
  const picked =
    selection && selection.base === (latestCompleted?.id ?? null)
      ? analyses.find((a) => a.id === selection.id && a.status === "completed")
      : undefined
  const shown = picked ?? latestCompleted
  const setSelectedId = (id: string) => setSelection({ id, base: latestCompleted?.id ?? null })
  const { data: result, error: resultError } = useResult(shown?.files.result ? shown.id : null)

  const refresh = () => {
    void mutate()
    void globalMutate("recordings")
  }

  const remove = async () => {
    try {
      await api.deleteRecording(id)
      toast.success("Recording deleted")
      void globalMutate("recordings")
      router.push("/")
    } catch (e) {
      toast.error("Delete failed", { description: (e as Error).message })
    }
  }

  if (error)
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert variant="destructive">
          <CircleX />
          <AlertTitle>{error.status === 404 ? "Recording not found" : "Couldn't load recording"}</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      </div>
    )

  if (isLoading || !rec)
    return (
      <div className="space-y-4">
        <BackLink />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )

  const failed = latest && (latest.status === "failed" || latest.status === "cancelled") && latest.id !== shown?.id ? latest : null
  const canRenotate = !!shown && !active && result?.transcription.status === "completed"

  return (
    <div className="space-y-6">
      <BackLink />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1.5">
          <TitleEditor id={rec.id} title={rec.title} onSaved={refresh} />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Badge variant="outline" className="uppercase">
                {rec.file_ext}
              </Badge>
              {rec.has_video && (
                <Badge variant="outline" className="gap-1">
                  <Video /> video
                </Badge>
              )}
            </span>
            <span className="truncate">{rec.original_filename}</span>
            <span>{formatTime(rec.duration_sec)}</span>
            <span>{formatBytes(rec.size_bytes)}</span>
            {rec.sample_rate && (
              <span>
                {(rec.sample_rate / 1000).toFixed(1)} kHz{rec.channels ? ` · ${rec.channels === 1 ? "mono" : rec.channels === 2 ? "stereo" : `${rec.channels} ch`}` : ""}
              </span>
            )}
            <span>Uploaded {formatDate(rec.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {shown && result && (
            <NotationDialog
              key={shown.id}
              analysisId={shown.id}
              result={result}
              disabled={!canRenotate}
              onQueued={refresh}
            />
          )}
          <ReanalyzeDialog recordingId={rec.id} currentEngine={latest?.engine} disabled={!!active} onQueued={refresh} />
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Delete recording">
                <Trash2 />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this recording?</AlertDialogTitle>
                <AlertDialogDescription>
                  The uploaded file, all analyses, MIDI and sheet music for “{rec.title}” will be permanently removed.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={remove}>
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {active && <AnalysisProgress analysis={active} onChange={refresh} />}

      {failed && (
        <Card className="border-destructive/40">
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <StatusBadge analysis={failed} /> {failed.mode === "renotate" ? "Re-engraving" : "Analysis"}{" "}
              {failed.status}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {failed.error && <p className="text-sm text-destructive">{failed.error}</p>}
            <StageList analysis={failed} />
          </CardContent>
        </Card>
      )}

      {analyses.filter((a) => a.status === "completed").length > 1 && shown && (
        <div className="flex items-center gap-2">
          <History className="size-4 text-muted-foreground" />
          <Select value={shown.id} onValueChange={setSelectedId}>
            <SelectTrigger className="w-full max-w-md" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {analyses.map((a, i) =>
                a.status === "completed" ? (
                  <SelectItem key={a.id} value={a.id}>
                    {analysisLabel(a, i)}
                  </SelectItem>
                ) : null,
              )}
            </SelectContent>
          </Select>
        </div>
      )}

      {shown && result ? (
        <ResultsView
          key={shown.id}
          result={result}
          audioSrc={rec.playback_ready || ["mp3", "wav", "m4a", "flac", "mp4"].includes(rec.file_ext) ? urls.audio(rec.id) : null}
          links={{
            midi: shown.files.midi ? urls.file(shown.id, "midi") : null,
            musicxml: shown.files.musicxml ? urls.file(shown.id, "musicxml") : null,
            pdf: shown.files.pdf ? urls.file(shown.id, "pdf") : null,
            json: shown.files.result ? urls.file(shown.id, "json") : null,
            original: urls.original(rec.id),
            print: shown.files.musicxml ? `/recordings/${rec.id}/print?analysis=${shown.id}` : null,
          }}
          loadMusicXml={() => api.musicxml(shown.id)}
          musicXmlKey={shown.id}
          printHref={`/recordings/${rec.id}/print?analysis=${shown.id}`}
          tab={tab}
          onTabChange={setTab}
        />
      ) : shown && !resultError ? (
        <Skeleton className="h-96 w-full" />
      ) : resultError ? (
        <Alert variant="destructive">
          <CircleX />
          <AlertTitle>Couldn&apos;t load results</AlertTitle>
          <AlertDescription>{resultError.message}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

function BackLink() {
  return (
    <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Library
    </Link>
  )
}
