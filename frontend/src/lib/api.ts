import type {
  Analysis,
  AnalysisResult,
  NotationOverrides,
  Recording,
  RecordingDetail,
  SystemStatus,
} from "@/lib/types"

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8484").replace(/\/$/, "")

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new ApiError(`Can't reach the PianoScribe backend at ${API_URL}. Is it running?`, 0)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

export const api = {
  system: () => request<SystemStatus>("/api/system"),
  recordings: () => request<Recording[]>("/api/recordings"),
  recording: (id: string) => request<RecordingDetail>(`/api/recordings/${id}`),
  renameRecording: (id: string, title: string) =>
    request<RecordingDetail>(`/api/recordings/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  deleteRecording: (id: string) => request<void>(`/api/recordings/${id}`, { method: "DELETE" }),
  reanalyze: (id: string, engine?: string) =>
    request<Analysis>(`/api/recordings/${id}/analyses`, json({ engine: engine ?? null })),
  analysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),
  result: (id: string) => request<AnalysisResult>(`/api/analyses/${id}/result`),
  cancel: (id: string) => request<Analysis>(`/api/analyses/${id}/cancel`, { method: "POST" }),
  renotate: (id: string, overrides: NotationOverrides) =>
    request<Analysis>(`/api/analyses/${id}/renotate`, json(overrides)),
  musicxml: async (id: string) => {
    const res = await fetch(`${API_URL}/api/analyses/${id}/files/musicxml?download=false`)
    if (!res.ok) throw new ApiError("Sheet music not available", res.status)
    return res.text()
  },
}

export const urls = {
  audio: (recordingId: string) => `${API_URL}/api/recordings/${recordingId}/audio`,
  original: (recordingId: string) => `${API_URL}/api/recordings/${recordingId}/original`,
  file: (analysisId: string, kind: "midi" | "musicxml" | "pdf" | "json") =>
    `${API_URL}/api/analyses/${analysisId}/files/${kind}`,
}

/** Upload with progress reporting (fetch can't report upload progress). */
export function uploadRecording(
  file: File,
  opts: { title?: string; engine?: string },
  onProgress: (fraction: number) => void,
): { promise: Promise<RecordingDetail>; abort: () => void } {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<RecordingDetail>((resolve, reject) => {
    const form = new FormData()
    form.append("file", file)
    if (opts.title) form.append("title", opts.title)
    if (opts.engine) form.append("engine", opts.engine)
    xhr.open("POST", `${API_URL}/api/recordings`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      let body: { detail?: unknown } | RecordingDetail | null = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as RecordingDetail)
      else {
        const detail = body && "detail" in body ? body.detail : null
        reject(new ApiError(typeof detail === "string" ? detail : `Upload failed (${xhr.status})`, xhr.status))
      }
    }
    xhr.onerror = () => reject(new ApiError(`Can't reach the PianoScribe backend at ${API_URL}.`, 0))
    xhr.onabort = () => reject(new ApiError("Upload cancelled", 0))
    xhr.send(form)
  })
  return { promise, abort: () => xhr.abort() }
}
