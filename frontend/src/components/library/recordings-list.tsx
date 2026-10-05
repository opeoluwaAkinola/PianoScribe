"use client"

import { Ellipsis, Music, Search, Trash2, Video } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/status-badge"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRecordings } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { formatRelative, formatTime } from "@/lib/format"
import type { Recording } from "@/lib/types"

export function RecordingsList() {
  const router = useRouter()
  const { data, error, isLoading, mutate } = useRecordings()
  const [query, setQuery] = useState("")
  const [toDelete, setToDelete] = useState<Recording | null>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data ?? []).filter((r) => !q || r.title.toLowerCase().includes(q) || r.original_filename.toLowerCase().includes(q))
  }, [data, query])

  const confirmDelete = async () => {
    if (!toDelete) return
    try {
      await api.deleteRecording(toDelete.id)
      toast.success("Recording deleted", { description: toDelete.title })
      void mutate()
    } catch (e) {
      toast.error("Delete failed", { description: (e as Error).message })
    } finally {
      setToDelete(null)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle>Recordings</CardTitle>
        <div className="relative w-full max-w-60">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…" className="pl-8" />
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            {error.message}
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-10 text-center">
            <Music className="size-6 text-muted-foreground" />
            <div className="text-sm font-medium">{data?.length ? "No matches" : "No recordings yet"}</div>
            <div className="text-xs text-muted-foreground">
              {data?.length ? "Try a different search." : "Upload a piano recording above to get started."}
            </div>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead className="hidden md:table-cell">Length</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden sm:table-cell">Key</TableHead>
                <TableHead className="hidden sm:table-cell">Tempo</TableHead>
                <TableHead className="hidden lg:table-cell">Notes</TableHead>
                <TableHead className="hidden lg:table-cell">Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const a = r.latest_analysis
                const done = a?.status === "completed"
                return (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => router.push(`/recordings/${r.id}`)}>
                    <TableCell className="max-w-72">
                      <Link href={`/recordings/${r.id}`} className="block truncate font-medium" onClick={(e) => e.stopPropagation()}>
                        {r.title}
                      </Link>
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                        {r.has_video ? <Video className="size-3" /> : <Music className="size-3" />}
                        <Badge variant="outline" className="h-4 px-1 text-[10px] uppercase">
                          {r.file_ext}
                        </Badge>
                        <span className="truncate">{r.original_filename}</span>
                      </div>
                    </TableCell>
                    <TableCell className="hidden tabular-nums md:table-cell">{formatTime(r.duration_sec)}</TableCell>
                    <TableCell>
                      <StatusBadge analysis={a} />
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">{done ? (a?.key ?? "–") : "–"}</TableCell>
                    <TableCell className="hidden tabular-nums sm:table-cell">
                      {done && a?.bpm ? (
                        <span>
                          {Math.round(a.bpm)} <span className="text-muted-foreground">BPM · {a.time_signature}</span>
                        </span>
                      ) : (
                        "–"
                      )}
                    </TableCell>
                    <TableCell className="hidden tabular-nums lg:table-cell">
                      {done && a?.transcription_status === "completed" ? a.note_count?.toLocaleString() : "–"}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{formatRelative(r.created_at)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" aria-label="Actions">
                            <Ellipsis />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem variant="destructive" onSelect={() => setToDelete(r)}>
                            <Trash2 /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{toDelete?.title}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the uploaded file and all of its transcriptions from this computer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
