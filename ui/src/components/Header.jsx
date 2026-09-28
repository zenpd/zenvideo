import { Search, ExternalLink, X } from 'lucide-react'

export function Header({ title, subtitle, search = '', onSearchChange, online }) {
  return (
    <header
      className="fixed top-0 left-[240px] right-0 z-20 h-[60px]
                 bg-white/90 backdrop-blur-sm border-b border-gray-100 shadow-header
                 flex items-center justify-between px-6 gap-4"
    >
      {/* Page title */}
      <div className="min-w-0">
        {title && <h1 className="text-sm font-semibold text-gray-900 truncate">{title}</h1>}
        {subtitle && <p className="text-xs text-gray-400 truncate">{subtitle}</p>}
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2 flex-shrink-0">

        {/* Search / filter stages */}
        {onSearchChange && (
          <div className="relative hidden md:flex items-center">
            <Search size={14} className="absolute left-3 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Filter stages…"
              className="pl-8 pr-7 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-lg
                w-52 outline-none focus:border-zen-400 focus:ring-2 focus:ring-zen-100 transition-all"
            />
            {search && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute right-2 text-gray-400 hover:text-gray-600"
              >
                <X size={12} />
              </button>
            )}
          </div>
        )}

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
          <span className={online === false ? 'w-2 h-2 rounded-full bg-rose-400 inline-block' : 'live-dot'} />
          <span>API</span>
        </div>
      </div>
    </header>
  )
}
