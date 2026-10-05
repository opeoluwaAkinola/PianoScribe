"use client"

import { Info, TriangleAlert } from "lucide-react"
import { useMemo, useState } from "react"

import { PlaybackProvider } from "@/components/playback/playback-provider"
import { ChordsView } from "@/components/results/chords-view"
import { type DownloadLinks, Downloads } from "@/components/results/downloads"
import { NotesTable } from "@/components/results/notes-table"
import { type ChordDisplay, PianoRoll } from "@/components/results/piano-roll"
import { SectionsView } from "@/components/results/sections-view"
import { SheetMusic } from "@/components/results/sheet-music"
import { Summary } from "@/components/results/summary"
import { Transport } from "@/components/results/transport"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { BeatClock } from "@/lib/music"
import type { AnalysisResult } from "@/lib/types"

function Unavailable({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-14 text-center text-sm text-muted-foreground">
        <Info className="size-5" />
        {children}
      </CardContent>
    </Card>
  )
}

export function ResultsView({
  result,
  audioSrc,
  links,
  loadMusicXml,
  musicXmlKey,
  printHref,
  tab: controlledTab,
  onTabChange,
}: {
  result: AnalysisResult
  audioSrc: string | null
  links: DownloadLinks
  loadMusicXml?: () => Promise<string>
  musicXmlKey: string
  printHref?: string
  /** Optional controlled tab, so the choice survives switching analysis versions. */
  tab?: string
  onTabChange?: (tab: string) => void
}) {
  const [localTab, setLocalTab] = useState("roll")
  const tab = controlledTab ?? localTab
  const setTab = onTabChange ?? setLocalTab
  const [chordDisplay, setChordDisplay] = useState<ChordDisplay>("label")
  const clock = useMemo(() => (result.tempo.grid ? new BeatClock(result.tempo.grid) : null), [result.tempo.grid])
  const transcribed = result.transcription.status === "completed"
  const fifths = result.key?.fifths ?? 0
  const handSplit = result.notation.hand_split ?? 60
  const chords = result.chords.segments
  const otherWarnings = result.warnings.filter((w) => !w.startsWith("AI transcription"))

  return (
    <PlaybackProvider audioSrc={audioSrc} notes={result.notes} duration={result.duration}>
      <div className="space-y-4">
        {!transcribed && (
          <Alert>
            <TriangleAlert />
            <AlertTitle>
              {result.transcription.status === "failed" ? "AI transcription failed" : "AI transcription not available"}
            </AlertTitle>
            <AlertDescription>
              <p>
                {result.transcription.message ?? "No transcription engine ran."} Tempo, key, chords (from the audio
                chromagram) and sections were still analysed; notes, MIDI and sheet music need a working transcription
                engine.
              </p>
              {result.transcription.install_hint && (
                <code className="mt-1 block rounded bg-muted px-2 py-1 font-mono text-xs">{result.transcription.install_hint}</code>
              )}
            </AlertDescription>
          </Alert>
        )}
        {otherWarnings.length > 0 && (
          <Alert>
            <Info />
            <AlertTitle>Notes from the analysis</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {otherWarnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        <Summary result={result} />
        <div className="sticky top-14 z-30 -mx-1 bg-background/80 px-1 py-2 backdrop-blur">
          <Transport hasAudio={!!audioSrc} hasNotes={transcribed && result.notes.length > 0} clock={clock} chords={chords} />
        </div>

        <Tabs value={tab} onValueChange={setTab} className="gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <TabsList className="flex-wrap">
              <TabsTrigger value="roll">Piano roll</TabsTrigger>
              <TabsTrigger value="sheet">Sheet music</TabsTrigger>
              <TabsTrigger value="chords">Chords</TabsTrigger>
              <TabsTrigger value="sections">Sections</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="downloads">Downloads</TabsTrigger>
            </TabsList>
            {(tab === "roll" || tab === "chords") && (
              <ToggleGroup
                type="single"
                size="sm"
                variant="outline"
                value={chordDisplay}
                onValueChange={(v) => v && setChordDisplay(v as ChordDisplay)}
                aria-label="Chord display"
              >
                <ToggleGroupItem value="label">C·Dm7</ToggleGroupItem>
                <ToggleGroupItem value="roman">I·ii7</ToggleGroupItem>
                <ToggleGroupItem value="nashville">1·2m7</ToggleGroupItem>
              </ToggleGroup>
            )}
          </div>

          <TabsContent value="roll">
            {transcribed ? (
              <PianoRoll
                notes={result.notes}
                pedals={result.pedals}
                duration={result.duration}
                clock={clock}
                chords={chords}
                sections={result.sections}
                handSplit={handSplit}
                fifths={fifths}
                chordDisplay={chordDisplay}
              />
            ) : (
              <div className="space-y-3">
                <PianoRoll
                  notes={[]}
                  duration={result.duration}
                  clock={clock}
                  chords={chords}
                  sections={result.sections}
                  fifths={fifths}
                  chordDisplay={chordDisplay}
                  height={200}
                />
                <p className="text-sm text-muted-foreground">
                  The piano roll shows beats, chords and sections; notes appear once a transcription engine has run.
                </p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="sheet">
            {result.notation.files.musicxml && loadMusicXml ? (
              <SheetMusic key={musicXmlKey} load={loadMusicXml} sourceKey={musicXmlKey} printHref={printHref} />
            ) : (
              <Unavailable>Sheet music needs a transcription. Install a transcription engine and re-analyse.</Unavailable>
            )}
          </TabsContent>

          <TabsContent value="chords">
            <ChordsView
              chords={chords}
              source={result.chords.source}
              sections={result.sections}
              clock={clock}
              barCount={result.tempo.bar_count ?? 0}
              keyInfo={result.key}
              display={chordDisplay}
            />
          </TabsContent>

          <TabsContent value="sections">
            <SectionsView sections={result.sections} duration={result.duration} />
          </TabsContent>

          <TabsContent value="notes">
            {transcribed ? (
              <NotesTable notes={result.notes} fifths={fifths} handSplit={handSplit} clock={clock} />
            ) : (
              <Unavailable>No notes – the transcription engine didn&apos;t run.</Unavailable>
            )}
          </TabsContent>

          <TabsContent value="downloads">
            <Downloads links={links} />
          </TabsContent>
        </Tabs>
      </div>
    </PlaybackProvider>
  )
}
