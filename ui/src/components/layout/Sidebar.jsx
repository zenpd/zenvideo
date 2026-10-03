import { useEffect, useState } from 'react'
import clsx from 'clsx'
import {
  Clapperboard, Video, FileText, Mic, Film,
  Globe, MonitorPlay, Combine,
} from 'lucide-react'

const NAV = [
  { num: 0, label: 'WebM → MP4',        icon: Video },
  { num: 1, label: 'Format Transcript', icon: FileText },
  { num: 2, label: 'Generate TTS',      icon: Mic },
  { num: 3, label: 'Sync & Merge',      icon: Film },
  { num: 4, label: 'Browser Recording', icon: Globe },
  { num: 5, label: 'Screen Recorder',   icon: MonitorPlay },
  { num: 6, label: 'One-Shot Sync',     icon: Combine },
]

function scrollToStage(num) {
  document.getElementById(`stage-${num}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export function Sidebar({ online }) {
  const [activeStage, setActiveStage] = useState(null)

  // Scroll-spy: highlight the row (of this 2-column grid) closest to the header line.
  // AppShell's <main> has no capped height, so the window itself is the real scrolling context.
  useEffect(() => {
    const LINE = 60 + 24 // header height + a little breathing room
    const GAP  = 24      // forward tolerance so an inter-row grid gap can't fall in a dead zone
    let ticking = false

    function computeActive() {
      ticking = false
      // Two cards can share a row/top in this grid, and NAV's numeric order doesn't
      // match the cards' visual order — so pick whichever qualifying top is largest
      // (i.e. the most recently reached row), not "the last one processed".
      let current = NAV[0].num
      let bestTop = -Infinity
      for (const { num } of NAV) {
        const el = document.getElementById(`stage-${num}`)
        if (!el) continue
        const top = el.getBoundingClientRect().top
        if (top <= LINE + GAP && top > bestTop) {
          bestTop = top
          current = num
        }
      }
      setActiveStage(current)
    }

    function onScroll() {
      if (!ticking) {
        ticking = true
        requestAnimationFrame(computeActive)
      }
    }

    computeActive()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  return (
    <aside className="fixed top-0 left-0 bottom-0 w-[240px] bg-white shadow-sidebar z-30 flex flex-col">

      {/* Logo */}
      <div className="h-[60px] flex items-center px-5 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative w-8 h-8 rounded-xl bg-gradient-zen
            flex items-center justify-center shadow-glow-zen flex-shrink-0">
            <Clapperboard size={16} className="text-white" />
          </div>
          <div>
            <span className="font-extrabold text-gray-900 text-sm tracking-tight leading-tight block">
              ZenVideoMaker
            </span>
            <span className="block text-[10px] font-medium text-gray-400 -mt-0.5 tracking-wide uppercase">
              powered by ZenLabs
            </span>
          </div>
        </div>
      </div>

      {/* Stage nav */}
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <p className="section-title px-1 mb-2">Pipeline Stages</p>

        <nav className="space-y-0.5">
          {NAV.map(({ num, label, icon: Icon }) => (
            <button
              key={num}
              onClick={() => scrollToStage(num)}
              className={clsx('sidebar-link w-full text-left', activeStage === num && 'active')}
            >
              <Icon size={16} />
              <span className="flex-1 truncate">{label}</span>
              <span className="text-[10px] font-bold text-gray-300">{num}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* System status pill */}
      <div className="px-4 py-2.5 border-t border-gray-100">
        {online === false ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-50 border border-rose-100">
            <span className="w-2 h-2 rounded-full bg-rose-500 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold text-rose-700 uppercase tracking-wide">API unreachable</p>
              <p className="text-[10px] text-rose-600/70">Start uvicorn on :8010</p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-emerald-50 border border-emerald-100">
            <span className="live-dot flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide">
                {online === null ? 'Connecting…' : 'API online'}
              </p>
              <p className="text-[10px] text-emerald-600/70">FastAPI · :8010</p>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
