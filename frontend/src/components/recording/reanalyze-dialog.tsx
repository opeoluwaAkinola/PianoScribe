"use client"

import { RefreshCw } from "lucide-react"
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
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useSystem } from "@/hooks/use-api"
import { api } from "@/lib/api"

export function ReanalyzeDialog({
  recordingId,
  currentEngine,
  disabled,
  onQueued,
}: {
  recordingId: string
  currentEngine?: string
  disabled?: boolean
  onQueued: () => void
}) {
  const { data: system } = useSystem()
  const [open, setOpen] = useState(false)
  const [engine, setEngine] = useState<string | undefined>(currentEngine)
  const [busy, setBusy] = useState(false)
  const selected = engine ?? system?.default_engine
  const info = system?.engines.find((e) => e.id === selected)

  const submit = async () => {
    setBusy(true)
    try {
      await api.reanalyze(recordingId, selected)
      toast.success("Analysis queued")
      setOpen(false)
      onQueued()
    } catch (e) {
      toast.error("Couldn't start analysis", { description: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          <RefreshCw /> Re-analyse
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run a new analysis</DialogTitle>
          <DialogDescription>
            Runs the full pipeline again, including AI transcription. Previous results are kept in the version history.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label>Transcription engine</Label>
          <Select value={selected} onValueChange={setEngine}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {system?.engines.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.label}
                  {!e.available && " (not installed)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {info && <p className="text-xs text-muted-foreground">{info.available ? info.description : info.reason}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            Start analysis
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
