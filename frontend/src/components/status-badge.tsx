import { Ban, CircleCheck, CircleX, Clock, LoaderCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { Analysis } from "@/lib/types"
import { cn } from "@/lib/utils"

export function StatusBadge({ analysis, className }: { analysis: Analysis | null; className?: string }) {
  if (!analysis) return <Badge variant="outline">No analysis</Badge>
  const { status } = analysis
  if (status === "running")
    return (
      <Badge variant="secondary" className={cn("gap-1 tabular-nums", className)}>
        <LoaderCircle className="animate-spin" /> {Math.round(analysis.progress * 100)}%
      </Badge>
    )
  if (status === "queued")
    return (
      <Badge variant="outline" className={cn("gap-1", className)}>
        <Clock /> Queued
      </Badge>
    )
  if (status === "failed")
    return (
      <Badge variant="destructive" className={cn("gap-1", className)}>
        <CircleX /> Failed
      </Badge>
    )
  if (status === "cancelled")
    return (
      <Badge variant="outline" className={cn("gap-1 text-muted-foreground", className)}>
        <Ban /> Cancelled
      </Badge>
    )
  const partial = analysis.transcription_status !== "completed"
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1",
        partial
          ? "border-amber-500/40 text-amber-700 dark:text-amber-400"
          : "border-emerald-500/40 text-emerald-700 dark:text-emerald-400",
        className,
      )}
    >
      <CircleCheck /> {partial ? "Audio only" : "Transcribed"}
    </Badge>
  )
}
