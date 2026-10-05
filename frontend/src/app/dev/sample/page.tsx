"use client"

import { FlaskConical } from "lucide-react"
import useSWR from "swr"

import { ResultsView } from "@/components/results/results-view"
import { Skeleton } from "@/components/ui/skeleton"
import type { AnalysisResult } from "@/lib/types"

const BASE = "/dev-sample"

async function loadFixture(): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/result.json`)
  if (!res.ok) throw new Error("Development fixture missing – run: cd backend && .venv/bin/python -m app.devtools.make_dev_fixture")
  return res.json()
}

/**
 * DEVELOPMENT DATA ONLY. Renders the results UI from a synthetic fixture so the
 * interface can be built and tested without running the transcription model.
 */
export default function DevSamplePage() {
  const { data, error } = useSWR("dev-fixture", loadFixture)

  return (
    <div className="space-y-6">
      <div
        className="flex items-start gap-3 rounded-xl border-2 border-dashed border-amber-500/60 p-4"
        style={{ background: "var(--dev-banner)", color: "var(--dev-banner-fg)" }}
      >
        <FlaskConical className="mt-0.5 size-5 shrink-0" />
        <div className="space-y-1 text-sm">
          <div className="font-semibold tracking-wide uppercase">Development data – not a real transcription</div>
          <p>
            Everything on this page comes from a synthetic fixture: the notes were written by hand (a ii–V–I progression in
            A♭) and rendered with a simple synthesiser. It exists only to develop and test the interface. Real results only
            ever come from uploaded recordings processed by a transcription engine.
          </p>
        </div>
      </div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Development sample</h1>
        <p className="text-sm text-muted-foreground">UI preview using fixture files in <code className="font-mono">frontend/public/dev-sample/</code>.</p>
      </div>
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      {!data && !error && <Skeleton className="h-96 w-full" />}
      {data && (
        <ResultsView
          result={data}
          audioSrc={`${BASE}/audio.m4a`}
          links={{ midi: `${BASE}/transcription.mid`, musicxml: `${BASE}/score.musicxml`, json: `${BASE}/result.json` }}
          loadMusicXml={() => fetch(`${BASE}/score.musicxml`).then((r) => r.text())}
          musicXmlKey="dev-sample"
        />
      )}
    </div>
  )
}
