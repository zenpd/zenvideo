import { Clapperboard, ExternalLink } from 'lucide-react'

export function Header() {
  return (
    <header
      className="fixed top-0 left-0 right-0 z-20 h-[60px]
                 bg-white/90 backdrop-blur-sm border-b border-gray-100 shadow-header
                 flex items-center justify-between px-6"
    >
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-zen flex items-center justify-center shadow-sm">
          <Clapperboard className="w-4.5 h-4.5 text-white" size={18} />
        </div>
        <div>
          <h1 className="text-sm font-bold text-gray-900 leading-tight">
            ZenVideoMaker(TTS, Video + Audio Merger)
          </h1>
          <p className="text-[11px] text-gray-400 leading-tight hidden sm:block">
            powered by ZenLabs
          </p>
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm hidden sm:inline-flex"
        >
          <ExternalLink size={12} />
          Swagger API
        </a>

        <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
          <span className="live-dot" />
          <span>API</span>
        </div>
      </div>
    </header>
  )
}
