"use client"

import { Printer } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { Suspense, use, useCallback, useRef } from "react"

import { SheetMusic } from "@/components/results/sheet-music"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"

function PrintView({ recordingId }: { recordingId: string }) {
  const search = useSearchParams()
  const analysisId = search.get("analysis")
  const printed = useRef(false)
  const load = useCallback(() => {
    if (!analysisId) return Promise.reject(new Error("Missing ?analysis= parameter"))
    return api.musicxml(analysisId)
  }, [analysisId])

  const onRendered = useCallback(() => {
    if (printed.current || search.get("autoprint") === "0") return
    printed.current = true
    setTimeout(() => window.print(), 400)
  }, [search])

  return (
    <div className="mx-auto max-w-[210mm] space-y-4">
      <div className="no-print flex items-center justify-between gap-4 rounded-lg border bg-muted/40 p-3 text-sm">
        <span className="text-muted-foreground">
          Use your browser&apos;s print dialog to print or “Save as PDF”. Recording {recordingId.slice(0, 8)}.
        </span>
        <Button size="sm" onClick={() => window.print()}>
          <Printer /> Print
        </Button>
      </div>
      <SheetMusic
        load={load}
        sourceKey={`print-${analysisId}`}
        pageFormat="A4_P"
        initialZoom={1}
        toolbar={false}
        onRendered={onRendered}
        className="print-sheet"
      />
      <style>{`
        @media print {
          @page { size: A4 portrait; margin: 0; }
          main { padding: 0 !important; max-width: none !important; }
          .print-sheet .sheet-paper { border: 0 !important; padding: 0 !important; border-radius: 0 !important; }
          .print-sheet svg { page-break-after: always; break-after: page; display: block; }
        }
      `}</style>
    </div>
  )
}

export default function PrintPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <Suspense>
      <PrintView recordingId={id} />
    </Suspense>
  )
}
