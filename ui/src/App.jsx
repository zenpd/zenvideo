import { STAGES } from './stages'
import { useStatus } from './hooks/useStatus'
import { Header } from './components/Header'
import { StatusPanel } from './components/StatusPanel'
import { StageCard } from './components/StageCard'
import { ShieldCheck } from 'lucide-react'

function Footer() {
  return (
    <footer className="mt-10 pb-8 flex items-center justify-center gap-4 text-xs text-gray-400">
      <ShieldCheck size={12} className="text-zen-500" />
      <span className="font-semibold text-gray-500">TTS Pipeline</span>
      <span>·</span>
      <span>Kokoro ONNX + FFmpeg</span>
      <span>·</span>
      <a
        href="http://localhost:8000/docs"
        target="_blank"
        rel="noopener noreferrer"
        className="text-zen-500 hover:text-zen-700 font-medium transition-colors"
      >
        FastAPI Docs →
      </a>
      <span>·</span>
      <a
        href="http://localhost:8501"
        target="_blank"
        rel="noopener noreferrer"
        className="text-zen-500 hover:text-zen-700 font-medium transition-colors"
      >
        Streamlit UI →
      </a>
    </footer>
  )
}

export default function App() {
  const { files, refresh } = useStatus()

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      <main className="mt-[60px] max-w-6xl mx-auto px-4 sm:px-6 py-6 animate-fade-in">

        {/* ── Page heading ── */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-900">
            Audio / Video Pipeline
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Run any stage at any time · no ordering required · logs stream live
          </p>
        </div>

        {/* ── File status bar ── */}
        <StatusPanel files={files} onRefresh={refresh} />

        {/* ── Stage cards (2-column on large screens) ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {STAGES.map((stage) => (
            <StageCard key={stage.num} stage={stage} />
          ))}
        </div>

        <Footer />
      </main>
    </div>
  )
}
