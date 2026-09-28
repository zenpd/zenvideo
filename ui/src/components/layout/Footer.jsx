import { ShieldCheck } from 'lucide-react'

export function Footer() {
  return (
    <footer
      className="fixed bottom-0 left-[240px] right-0 h-[44px] z-20
                 bg-white/90 backdrop-blur-sm border-t border-gray-100
                 flex items-center justify-center gap-4 px-6 text-xs text-gray-400"
    >
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
