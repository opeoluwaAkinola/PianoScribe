"use client"

import { LoaderCircle, Printer, ZoomIn, ZoomOut } from "lucide-react"
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface SheetMusicProps {
  /** Loads the MusicXML text. */
  load: () => Promise<string>
  /** Identifies the score; give the component a matching React `key` so it remounts. */
  sourceKey: string
  printHref?: string
  pageFormat?: string
  initialZoom?: number
  toolbar?: boolean
  onRendered?: () => void
  className?: string
}

export function SheetMusic({
  load,
  sourceKey,
  printHref,
  pageFormat = "Endless",
  initialZoom = 0.85,
  toolbar = true,
  onRendered,
  className,
}: SheetMusicProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null)
  const loadRef = useRef(load)
  const renderedRef = useRef(onRendered)
  const [zoom, setZoom] = useState(initialZoom)
  const [state, setState] = useState<"loading" | "ready" | "error">("loading")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRef.current = load
    renderedRef.current = onRendered
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const [{ OpenSheetMusicDisplay }, xml] = await Promise.all([import("opensheetmusicdisplay"), loadRef.current()])
      if (cancelled || !containerRef.current) return
      containerRef.current.innerHTML = ""
      const osmd = new OpenSheetMusicDisplay(containerRef.current, {
        autoResize: true,
        backend: "svg",
        drawTitle: true,
        drawComposer: true,
        drawPartNames: false,
        drawMeasureNumbers: true,
        drawingParameters: "default",
        pageFormat,
        pageBackgroundColor: pageFormat === "Endless" ? undefined : "#FFFFFF",
      })
      await osmd.load(xml)
      if (cancelled) return
      osmd.Zoom = initialZoom
      osmd.render()
      osmdRef.current = osmd
      setState("ready")
      renderedRef.current?.()
    })().catch((e: Error) => {
      if (!cancelled) {
        setError(e.message)
        setState("error")
      }
    })
    return () => {
      cancelled = true
      try {
        osmdRef.current?.clear()
      } catch {
        /* ignore */
      }
      osmdRef.current = null
    }
  }, [sourceKey, pageFormat, initialZoom])

  useEffect(() => {
    const osmd = osmdRef.current
    if (!osmd || state !== "ready") return
    osmd.Zoom = zoom
    osmd.render()
  }, [zoom, state])

  return (
    <div className={cn("space-y-3", className)}>
      {toolbar && (
        <div className="no-print flex flex-wrap items-center gap-2">
          <Button variant="outline" size="icon-sm" onClick={() => setZoom((z) => Math.max(0.4, z - 0.1))} aria-label="Zoom out">
            <ZoomOut />
          </Button>
          <span className="w-12 text-center text-xs text-muted-foreground tabular-nums">{Math.round(zoom * 100)}%</span>
          <Button variant="outline" size="icon-sm" onClick={() => setZoom((z) => Math.min(2, z + 0.1))} aria-label="Zoom in">
            <ZoomIn />
          </Button>
          {printHref && (
            <Button variant="outline" size="sm" asChild className="ml-auto">
              <a href={printHref} target="_blank" rel="noreferrer">
                <Printer /> Print / save as PDF
              </a>
            </Button>
          )}
        </div>
      )}
      <div className="sheet-paper relative min-h-64 overflow-x-auto rounded-lg border bg-white p-4 text-black">
        {state === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-neutral-500">
            <LoaderCircle className="size-4 animate-spin" /> Engraving…
          </div>
        )}
        {state === "error" && (
          <div className="flex h-48 items-center justify-center text-sm text-red-600">Couldn&apos;t render sheet music: {error}</div>
        )}
        <div ref={containerRef} />
      </div>
    </div>
  )
}
