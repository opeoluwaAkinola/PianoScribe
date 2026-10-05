"use client"

import { Ban, CircleCheck, CircleDashed, CircleMinus, CircleX, LoaderCircle, TriangleAlert } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { useSystem } from "@/hooks/use-api"
import { api } from "@/lib/api"
import type { Analysis, StageStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const ICONS: Record<StageStatus, React.ComponentType<{ className?: string }>> = {
  pending: CircleDashed,
  running: LoaderCircle,
  done: CircleCheck,
  skipped: CircleMinus,
  unavailable: TriangleAlert,
  failed: CircleX,
  cancelled: Ban,
}

const COLORS: Record<StageStatus, string> = {
  pending: "text-muted-foreground/50",
  running: "text-primary animate-spin",
  done: "text-emerald-600 dark:text-emerald-400",
  skipped: "text-muted-foreground",
  unavailable: "text-amber-600 dark:text-amber-400",
  failed: "text-destructive",
  cancelled: "text-muted-foreground",
}

function useElapsed(since: string | null, running: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])
  if (!since) return null
  return Math.max(0, Math.round((now - new Date(since).getTime()) / 1000))
}

export function StageList({ analysis }: { analysis: Analysis }) {
  return (
    <ol className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
      {analysis.stages.map((s) => {
        const Icon = ICONS[s.status] ?? CircleDashed
        return (
          <li key={s.name} className={cn("flex items-start gap-2 rounded-md px-2 py-1.5 text-sm", s.status === "running" && "bg-primary/5")}>
            <Icon className={cn("mt-0.5 size-4 shrink-0", COLORS[s.status])} />
            <div className="min-w-0">
              <div className={cn(s.status === "pending" && "text-muted-foreground")}>{s.label}</div>
              {s.message && <div className="truncate text-xs text-muted-foreground" title={s.message}>{s.message}</div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function AnalysisProgress({ analysis, onChange }: { analysis: Analysis; onChange: () => void }) {
  const { data: system } = useSystem()
  const running = analysis.status === "running"
  const elapsed = useElapsed(analysis.started_at, running)
  const [cancelling, setCancelling] = useState(false)

  const cancel = async () => {
    setCancelling(true)
    try {
      await api.cancel(analysis.id)
      onChange()
    } catch (e) {
      toast.error("Couldn't cancel", { description: (e as Error).message })
    } finally {
      setCancelling(false)
    }
  }

  const current = analysis.stages.find((s) => s.name === analysis.stage)

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2">
            <LoaderCircle className={cn("size-4", running ? "animate-spin text-primary" : "text-muted-foreground")} />
            {analysis.mode === "renotate" ? "Re-engraving" : "Analysing recording"}
          </CardTitle>
          <CardDescription>
            {running
              ? `${current?.label ?? "Working"}${analysis.stage_message ? ` – ${analysis.stage_message}` : ""}`
              : "Waiting in the queue"}
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={cancel} disabled={cancelling || analysis.status === "cancelled"}>
          Cancel
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {analysis.status === "queued" && system && !system.worker_online && (
          <Alert>
            <TriangleAlert />
            <AlertTitle>No worker is running</AlertTitle>
            <AlertDescription>
              <p>
                This job will start as soon as a worker is available. Start one with{" "}
                <code className="font-mono text-xs">cd backend &amp;&amp; .venv/bin/python -m app.worker</code> (or use{" "}
                <code className="font-mono text-xs">./dev.sh</code>).
              </p>
            </AlertDescription>
          </Alert>
        )}
        <div className="space-y-1.5">
          <Progress value={analysis.progress * 100} />
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{Math.round(analysis.progress * 100)}%</span>
            {elapsed != null && running && <span>{elapsed}s elapsed</span>}
          </div>
        </div>
        <StageList analysis={analysis} />
      </CardContent>
    </Card>
  )
}
