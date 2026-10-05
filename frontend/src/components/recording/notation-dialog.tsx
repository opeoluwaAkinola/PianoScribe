"use client"

import { SlidersHorizontal } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"
import { KEY_OPTIONS, midiToName } from "@/lib/music"
import type { AnalysisResult, NotationOverrides } from "@/lib/types"

const AUTO = "auto"

export function NotationDialog({
  analysisId,
  result,
  disabled,
  onQueued,
}: {
  analysisId: string
  result: AnalysisResult
  disabled?: boolean
  onQueued: () => void
}) {
  const opts = result.options ?? {}
  const compound = result.tempo.compound
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [bpm, setBpm] = useState<string>(opts.bpm ? String(opts.bpm) : "")
  const [ts, setTs] = useState<string>(opts.time_signature ?? AUTO)
  const [key, setKey] = useState<string>(opts.key ?? AUTO)
  const [split, setSplit] = useState<number>(opts.hand_split ?? result.notation.hand_split ?? 60)
  const [sub, setSub] = useState<string>(opts.subdivisions ? String(opts.subdivisions) : AUTO)
  const [chordSymbols, setChordSymbols] = useState<boolean>(opts.chord_symbols ?? true)
  const [shift, setShift] = useState<number>(0)

  const submit = async () => {
    const body: NotationOverrides = {
      bpm: bpm ? Number(bpm) : null,
      time_signature: ts === AUTO ? null : ts,
      key: key === AUTO ? null : key,
      hand_split: split,
      subdivisions: sub === AUTO ? null : Number(sub),
      chord_symbols: chordSymbols,
      downbeat_shift: shift || null,
    }
    setBusy(true)
    try {
      await api.renotate(analysisId, body)
      toast.success("Re-engraving queued", { description: "Reusing the existing transcription – no model run needed." })
      setOpen(false)
      onQueued()
    } catch (e) {
      toast.error("Couldn't queue re-engraving", { description: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const detected = `${Math.round(result.tempo.bpm)} BPM`

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          <SlidersHorizontal /> Notation settings
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Notation settings</DialogTitle>
          <DialogDescription>
            Correct the tempo, meter or key, or change how notes are quantised. The sheet music, MIDI tempo map and chord
            chart are regenerated from the same transcribed notes.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 py-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="bpm">Tempo (BPM)</Label>
              <div className="flex gap-1.5">
                <Input id="bpm" inputMode="decimal" placeholder={`Auto (${detected})`} value={bpm} onChange={(e) => setBpm(e.target.value.replace(/[^\d.]/g, ""))} />
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setBpm(String(Math.round(result.tempo.bpm / 2)))} title="Half tempo">
                  ½×
                </Button>
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setBpm(String(Math.round(result.tempo.bpm * 2)))} title="Double tempo">
                  2×
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">Fixes double/half-time beat tracking.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Time signature</Label>
              <Select value={ts} onValueChange={setTs}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO}>Auto ({result.tempo.time_signature})</SelectItem>
                  {["4/4", "3/4", "2/4", "12/8", "6/8"].map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex items-center gap-1.5 pt-1">
                <span className="text-xs text-muted-foreground">Shift bar lines</span>
                <Button type="button" variant="outline" size="xs" onClick={() => setShift((s) => s - 1)}>
                  −1 beat
                </Button>
                <Button type="button" variant="outline" size="xs" onClick={() => setShift((s) => s + 1)}>
                  +1 beat
                </Button>
                {shift !== 0 && <span className="text-xs tabular-nums">{shift > 0 ? `+${shift}` : shift}</span>}
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Key</Label>
              <Select value={key} onValueChange={setKey}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value={AUTO}>Auto ({result.key?.label ?? "–"})</SelectItem>
                  {KEY_OPTIONS.map((k) => (
                    <SelectItem key={k} value={k}>
                      {k.replace("b ", "♭ ").replace("# ", "♯ ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Rhythm quantisation</Label>
              <Select value={sub} onValueChange={setSub}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO}>Auto – simplest fit per beat</SelectItem>
                  <SelectItem value="2">{compound ? "Duplets" : "8th notes only (simplest)"}</SelectItem>
                  <SelectItem value="4">16th notes</SelectItem>
                  <SelectItem value="3">{compound ? "8th notes (12/8)" : "Triplets (swing feel)"}</SelectItem>
                  <SelectItem value="6">{compound ? "16th notes (12/8)" : "16th-note triplets"}</SelectItem>
                  <SelectItem value="8">32nd notes (detailed)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Auto picks quarter, 8th, 16th or triplet rhythm beat by beat, using 16ths and triplets only where the
                playing clearly has them.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Hand split</Label>
              <span className="text-sm tabular-nums">
                {midiToName(split, result.key?.fifths ?? 0)} <span className="text-muted-foreground">(MIDI {split})</span>
              </span>
            </div>
            <Slider value={[split]} min={48} max={72} step={1} onValueChange={([v]) => setSplit(v)} />
            <p className="text-xs text-muted-foreground">Notes at or above this pitch go on the treble staff.</p>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <Label htmlFor="chord-symbols">Chord symbols above the staff</Label>
              <p className="text-xs text-muted-foreground">Write the detected chords into the score.</p>
            </div>
            <Switch id="chord-symbols" checked={chordSymbols} onCheckedChange={setChordSymbols} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            Re-engrave
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
