"use client"

import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore } from "react"

import { PlaybackController } from "@/lib/playback"
import type { NoteEvent } from "@/lib/types"

const PlaybackContext = createContext<PlaybackController | null>(null)

export function PlaybackProvider({
  audioSrc,
  notes,
  duration,
  children,
}: {
  audioSrc: string | null
  notes: NoteEvent[]
  duration: number
  children: React.ReactNode
}) {
  const [controller] = useState(() => new PlaybackController())

  useEffect(() => {
    controller.attachAudio(audioSrc)
  }, [controller, audioSrc])

  useEffect(() => {
    controller.setNotes(notes, duration)
  }, [controller, notes, duration])

  useEffect(() => () => controller.destroy(), [controller])

  return <PlaybackContext.Provider value={controller}>{children}</PlaybackContext.Provider>
}

export function usePlayback(): PlaybackController {
  const c = useContext(PlaybackContext)
  if (!c) throw new Error("usePlayback must be used inside <PlaybackProvider>")
  return c
}

/** Re-renders at most `fps` times per second with the current playback time. */
export function usePlaybackTime(fps = 15): number {
  const c = usePlayback()
  const last = useRef({ t: 0, at: 0 })
  return useSyncExternalStore(
    (cb) =>
      c.subscribe(() => {
        const now = performance.now()
        if (now - last.current.at >= 1000 / fps || !c.playing) {
          last.current = { t: c.getTime(), at: now }
          cb()
        }
      }),
    () => last.current.t,
    () => 0,
  )
}

/** Snapshot of non-time playback state (playing, mode, readiness). */
export function usePlaybackState() {
  const c = usePlayback()
  const snap = useRef({ playing: false, mode: c.mode, audioReady: false, audioError: null as string | null, duration: 0 })
  return useSyncExternalStore(
    (cb) =>
      c.subscribe(() => {
        const s = snap.current
        if (
          s.playing !== c.playing ||
          s.mode !== c.mode ||
          s.audioReady !== c.audioReady ||
          s.audioError !== c.audioError ||
          s.duration !== c.duration
        ) {
          snap.current = {
            playing: c.playing,
            mode: c.mode,
            audioReady: c.audioReady,
            audioError: c.audioError,
            duration: c.duration,
          }
          cb()
        }
      }),
    () => snap.current,
    () => snap.current,
  )
}
