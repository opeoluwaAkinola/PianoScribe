"use client"

import { use } from "react"

import { RecordingView } from "@/components/recording/recording-view"

export default function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <RecordingView id={id} />
}
