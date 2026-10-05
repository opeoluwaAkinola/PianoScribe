"use client"

import useSWR from "swr"

import { api } from "@/lib/api"
import type { Analysis, Recording, RecordingDetail } from "@/lib/types"

const isActive = (a: Analysis | null | undefined) => a?.status === "queued" || a?.status === "running"

export function useSystem() {
  return useSWR("system", api.system, { refreshInterval: 5000 })
}

export function useRecordings() {
  return useSWR<Recording[]>("recordings", api.recordings, {
    refreshInterval: (data) => (data?.some((r) => isActive(r.latest_analysis)) ? 1500 : 10000),
  })
}

export function useRecording(id: string) {
  return useSWR<RecordingDetail>(["recording", id], () => api.recording(id), {
    refreshInterval: (data) => (data?.analyses.some(isActive) ? 1000 : 0),
  })
}

export function useResult(analysisId: string | null | undefined) {
  return useSWR(analysisId ? ["result", analysisId] : null, () => api.result(analysisId!), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  })
}
