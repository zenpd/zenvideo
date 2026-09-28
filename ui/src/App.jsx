import { useState, useMemo } from 'react'
import { STAGES } from './stages'
import { useStatus } from './hooks/useStatus'
import { AppShell } from './components/layout/AppShell'
import { StatusPanel } from './components/StatusPanel'
import { StageCard } from './components/StageCard'
import { ScreenRecorderCard } from './components/ScreenRecorderCard'

const SCREEN_RECORDER_NAME = 'Screen Recorder'

export default function App() {
  const { files, online, refresh } = useStatus()
  const [search, setSearch] = useState('')

  const q = search.trim().toLowerCase()
  const filteredStages = useMemo(
    () => (q ? STAGES.filter((s) => s.name.toLowerCase().includes(q)) : STAGES),
    [q]
  )
  const showScreenRecorder = !q || SCREEN_RECORDER_NAME.toLowerCase().includes(q)

  return (
    <AppShell
      title="Audio / Video Pipeline"
      subtitle="Run any stage at any time · no ordering required · logs stream live"
      search={search}
      onSearchChange={setSearch}
      online={online}
    >
      {/* ── File status bar ── */}
      <StatusPanel files={files} onRefresh={refresh} />

      {/* ── Stage cards (2-column on large screens) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {filteredStages.map((stage) => (
          <div key={stage.num} id={`stage-${stage.num}`}>
            <StageCard stage={stage} />
          </div>
        ))}
        {showScreenRecorder && (
          <div id="stage-5">
            <ScreenRecorderCard />
          </div>
        )}
      </div>

      {filteredStages.length === 0 && !showScreenRecorder && (
        <div className="text-center py-16 text-sm text-gray-400">
          No stages match “{search}”.
        </div>
      )}
    </AppShell>
  )
}
