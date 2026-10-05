"use client"

import Link from "next/link"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useSystem } from "@/hooks/use-api"
import { cn } from "@/lib/utils"

export function WorkerIndicator() {
  const { data, error } = useSystem()
  const state = error ? "offline" : !data ? "loading" : data.worker_online ? "online" : "no-worker"
  const label = {
    offline: "Backend offline",
    loading: "Connecting…",
    online: data?.queue.running ? "Worker busy" : "Worker ready",
    "no-worker": "Worker not running",
  }[state]
  const tip = {
    offline: "Can't reach the API. Start everything with ./dev.sh.",
    loading: "Checking the backend…",
    online: `${data?.queue.queued ?? 0} queued · ${data?.queue.running ?? 0} running`,
    "no-worker": "Uploads will wait in the queue. Start it with: cd backend && .venv/bin/python -m app.worker",
  }[state]
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href="/engines"
          className="flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
        >
          <span
            className={cn(
              "size-2 rounded-full",
              state === "online" && (data?.queue.running ? "animate-pulse bg-amber-500" : "bg-emerald-500"),
              state === "no-worker" && "bg-amber-500",
              state === "offline" && "bg-red-500",
              state === "loading" && "bg-muted-foreground/40",
            )}
          />
          <span className="hidden md:inline">{label}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  )
}
