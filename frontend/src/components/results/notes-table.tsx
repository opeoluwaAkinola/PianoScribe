"use client"

import { useMemo, useState } from "react"

import { usePlayback } from "@/components/playback/playback-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatTime } from "@/lib/format"
import { type BeatClock, midiToName } from "@/lib/music"
import type { NoteEvent } from "@/lib/types"

const PAGE = 100

export function NotesTable({
  notes,
  fifths,
  handSplit,
  clock,
}: {
  notes: NoteEvent[]
  fifths: number
  handSplit: number
  clock: BeatClock | null
}) {
  const playback = usePlayback()
  const [page, setPage] = useState(0)
  const sorted = useMemo(() => [...notes].sort((a, b) => a.start - b.start || a.pitch - b.pitch), [notes])
  const pages = Math.max(1, Math.ceil(sorted.length / PAGE))
  const rows = sorted.slice(page * PAGE, page * PAGE + PAGE)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Detected notes</CardTitle>
        <CardDescription>
          The raw transcription: {sorted.length.toLocaleString()} notes with exact onset, length and velocity. Click a row to
          hear it in context.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">#</TableHead>
              <TableHead>Time</TableHead>
              {clock && <TableHead>Bar.beat</TableHead>}
              <TableHead>Note</TableHead>
              <TableHead className="hidden sm:table-cell">MIDI</TableHead>
              <TableHead>Length</TableHead>
              <TableHead>Velocity</TableHead>
              <TableHead className="hidden sm:table-cell">Hand</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((n, i) => (
              <TableRow key={`${n.start}-${n.pitch}-${i}`} className="cursor-pointer" onClick={() => playback.seek(Math.max(0, n.start - 0.5))}>
                <TableCell className="text-muted-foreground tabular-nums">{page * PAGE + i + 1}</TableCell>
                <TableCell className="font-mono text-xs tabular-nums">{formatTime(n.start, true)}</TableCell>
                {clock && (
                  <TableCell className="font-mono text-xs tabular-nums">
                    {clock.barAt(n.start)}.{(clock.beatInBar(n.start) + 1).toFixed(2)}
                  </TableCell>
                )}
                <TableCell className="font-semibold">{midiToName(n.pitch, fifths)}</TableCell>
                <TableCell className="hidden text-muted-foreground tabular-nums sm:table-cell">{n.pitch}</TableCell>
                <TableCell className="tabular-nums">{((n.end - n.start) * 1000).toFixed(0)} ms</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${(n.velocity / 127) * 100}%` }} />
                    </div>
                    <span className="text-xs text-muted-foreground tabular-nums">{n.velocity}</span>
                  </div>
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">{n.pitch >= handSplit ? "R" : "L"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {pages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Page {page + 1} of {pages}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
