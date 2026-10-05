import { RecordingsList } from "@/components/library/recordings-list"
import { UploadCard } from "@/components/library/upload-card"
import { SetupNotice } from "@/components/setup-notice"

export default function LibraryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <p className="text-sm text-muted-foreground">
          Upload a piano performance to get notes, MIDI, sheet music, chords, tempo, key and song sections.
        </p>
      </div>
      <SetupNotice />
      <UploadCard />
      <RecordingsList />
    </div>
  )
}
