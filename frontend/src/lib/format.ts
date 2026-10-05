export function formatTime(seconds: number | null | undefined, withMs = false): string {
  if (seconds == null || !Number.isFinite(seconds)) return "–"
  const s = Math.max(0, seconds)
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  const secs = withMs ? rest.toFixed(2).padStart(5, "0") : Math.floor(rest).toString().padStart(2, "0")
  return `${m}:${secs}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

export function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 45) return "just now"
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)} d ago`
  return formatDate(iso)
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`
}

/** "Bb" -> "B♭", "F#m7" -> "F♯m7" (display only). */
export function prettyAccidentals(label: string): string {
  return label.replace(/([A-G])b/g, "$1♭").replace(/([A-G])#/g, "$1♯")
}
