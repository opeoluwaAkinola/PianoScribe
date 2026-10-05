"use client"

import { FileAudio, Upload, X } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useRef, useState } from "react"
import { toast } from "sonner"
import { useSWRConfig } from "swr"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useSystem } from "@/hooks/use-api"
import { uploadRecording } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

const FALLBACK_EXTS = ["mp3", "wav", "m4a", "flac", "mp4", "mov"]

export function UploadCard() {
  const router = useRouter()
  const { mutate } = useSWRConfig()
  const { data: system } = useSystem()
  const inputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState("")
  const [engine, setEngine] = useState<string | undefined>(undefined)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)

  const exts = system?.allowed_extensions ?? FALLBACK_EXTS
  const accept = exts.map((e) => `.${e}`).join(",")
  const selectedEngine = engine ?? system?.default_engine
  const engineInfo = system?.engines.find((e) => e.id === selectedEngine)

  const choose = useCallback(
    (f: File | undefined | null) => {
      if (!f) return
      const ext = f.name.split(".").pop()?.toLowerCase() ?? ""
      if (!exts.includes(ext)) {
        toast.error(`.${ext} isn't supported`, { description: `Use ${exts.map((e) => e.toUpperCase()).join(", ")}` })
        return
      }
      setFile(f)
      setTitle(f.name.replace(/\.[^.]+$/, ""))
    },
    [exts],
  )

  const submit = async () => {
    if (!file) return
    setProgress(0)
    const { promise, abort } = uploadRecording(file, { title: title.trim() || undefined, engine: selectedEngine }, setProgress)
    abortRef.current = abort
    try {
      const rec = await promise
      toast.success("Uploaded – analysis queued", { description: rec.title })
      void mutate("recordings")
      setFile(null)
      setTitle("")
      router.push(`/recordings/${rec.id}`)
    } catch (e) {
      toast.error("Upload failed", { description: (e as Error).message })
    } finally {
      setProgress(null)
      abortRef.current = null
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Transcribe a recording</CardTitle>
        <CardDescription>
          Audio or video of a piano performance: {exts.map((e) => e.toUpperCase()).join(", ")}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            choose(e.dataTransfer.files?.[0])
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
            dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/40",
          )}
        >
          <span className="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Upload className="size-5" />
          </span>
          <div className="text-sm font-medium">Drop a file here or click to browse</div>
          <div className="text-xs text-muted-foreground">Up to {system?.max_upload_mb ?? 2048} MB · stays on this computer</div>
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="hidden"
            onChange={(e) => {
              choose(e.target.files?.[0])
              e.target.value = ""
            }}
          />
        </div>

        {file && (
          <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
            <div className="flex items-center gap-3">
              <FileAudio className="size-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{file.name}</div>
                <div className="text-xs text-muted-foreground">{formatBytes(file.size)}</div>
              </div>
              {progress === null && (
                <Button variant="ghost" size="icon-sm" onClick={() => setFile(null)} aria-label="Remove file">
                  <X />
                </Button>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="title">Title</Label>
                <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} disabled={progress !== null} />
              </div>
              <div className="space-y-1.5">
                <Label>Transcription engine</Label>
                <Select value={selectedEngine} onValueChange={setEngine} disabled={progress !== null}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Default engine" />
                  </SelectTrigger>
                  <SelectContent>
                    {system?.engines.map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.label}
                        {!e.available && " (not installed)"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {engineInfo && !engineInfo.available && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {engineInfo.label} isn&apos;t available ({engineInfo.reason}). Tempo, key, chords and sections will still be
                analysed from the audio, but notes, MIDI and sheet music need a transcription engine.
              </p>
            )}
            {progress !== null ? (
              <div className="space-y-2">
                <Progress value={progress * 100} />
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : "Checking file…"}</span>
                  <Button variant="ghost" size="xs" onClick={() => abortRef.current?.()}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={submit} className="w-full sm:w-auto">
                <Upload /> Upload &amp; transcribe
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
