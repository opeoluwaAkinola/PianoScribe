"use client"

import { ServerCrash, TriangleAlert } from "lucide-react"
import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { useSystem } from "@/hooks/use-api"
import { API_URL } from "@/lib/api"

/** Surfaces setup problems (backend down, no worker, no engine) where they matter. */
export function SetupNotice() {
  const { data, error } = useSystem()
  if (error)
    return (
      <Alert variant="destructive">
        <ServerCrash />
        <AlertTitle>Backend not reachable</AlertTitle>
        <AlertDescription>
          <p>
            Can&apos;t connect to <code className="font-mono">{API_URL}</code>. Start everything with{" "}
            <code className="font-mono">./dev.sh</code> from the project folder.
          </p>
        </AlertDescription>
      </Alert>
    )
  if (!data) return null
  const issues: string[] = []
  if (!data.worker_online)
    issues.push("The background worker isn't running, so uploads will wait in the queue (start: cd backend && .venv/bin/python -m app.worker).")
  const def = data.engines.find((e) => e.id === data.default_engine)
  if (def && !def.available) issues.push(`The default transcription engine (${def.label}) isn't available: ${def.reason}`)
  if (!data.ffmpeg.available) issues.push("ffmpeg wasn't found; audio decoding will fail.")
  if (!issues.length) return null
  return (
    <Alert>
      <TriangleAlert />
      <AlertTitle>Setup needs attention</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          {issues.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
        <Link href="/engines" className="font-medium underline underline-offset-4">
          Open engines &amp; system
        </Link>
      </AlertDescription>
    </Alert>
  )
}
