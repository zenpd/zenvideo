import { useState, useEffect, useRef } from 'react'
import { FolderOpen, File, X, Loader, AlertCircle } from 'lucide-react'

function fmtSize(bytes) {
  if (!bytes) return ''
  if (bytes > 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes > 1024)      return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

const EXT_ICON = {
  '.mp4': '🎬', '.webm': '🎥', '.mov': '🎥', '.avi': '🎥',
  '.mp3': '🎵', '.wav': '🎵', '.aac': '🎵',
  '.txt': '📄', '.onnx': '🤖', '.bin': '🔊',
}

/**
 * A text input with a server-side file browser dropdown.
 * Fetches GET /api/files?exts=... when the browse button is clicked.
 */
export function FilePicker({ value, onChange, fileExts = '', placeholder = '' }) {
  const [open,    setOpen]    = useState(false)
  const [files,   setFiles]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [query,   setQuery]   = useState('')
  const wrapRef = useRef(null)

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const openPicker = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    setLoading(true)
    setError(null)
    try {
      const res   = await fetch(`/api/files?exts=${encodeURIComponent(fileExts)}`)
      const data  = await res.json()
      setFiles(data)
    } catch (e) {
      setError('Could not reach API')
    } finally {
      setLoading(false)
    }
  }

  const filtered = files.filter((f) =>
    !query || f.name.toLowerCase().includes(query.toLowerCase())
  )

  const select = (name) => {
    onChange(name)
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={wrapRef} className="relative">
      {/* Input row */}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder || `e.g. file.${(fileExts.split(',')[0] || 'txt').replace(/^\./, '')}`}
          className="input flex-1 min-w-0 font-mono text-xs"
        />
        <button
          type="button"
          onClick={openPicker}
          title="Browse files"
          className={`btn btn-secondary btn-sm !px-2.5 shrink-0 transition-colors
                      ${open ? 'bg-zen-50 border-zen-300 text-zen-600' : ''}`}
        >
          <FolderOpen size={14} />
        </button>
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 mt-1.5 w-full min-w-[220px] bg-white rounded-xl
                        border border-gray-200 shadow-card-hover animate-slide-up overflow-hidden">
          {/* Search bar */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter files…"
              className="flex-1 text-xs outline-none placeholder-gray-400 bg-transparent"
            />
            {query && (
              <button onClick={() => setQuery('')} className="text-gray-400 hover:text-gray-600">
                <X size={12} />
              </button>
            )}
          </div>

          {/* File list */}
          <div className="max-h-48 overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center gap-2 py-5 text-xs text-gray-400">
                <Loader size={13} className="animate-spin" /> Loading…
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 px-3 py-3 text-xs text-rose-500">
                <AlertCircle size={13} /> {error}
              </div>
            )}

            {!loading && !error && filtered.length === 0 && (
              <div className="px-3 py-4 text-xs text-gray-400 text-center">
                No matching files found
              </div>
            )}

            {!loading && !error && filtered.map((f) => (
              <button
                key={f.name}
                onClick={() => select(f.name)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left
                            hover:bg-zen-50 transition-colors
                            ${value === f.name ? 'bg-zen-50' : ''}`}
              >
                <span className="text-sm leading-none shrink-0">
                  {EXT_ICON[f.ext] ?? <File size={13} className="text-gray-400" />}
                </span>
                <span className="flex-1 text-xs text-gray-700 font-mono truncate">{f.name}</span>
                <span className="text-[10px] text-gray-400 shrink-0">{fmtSize(f.size)}</span>
              </button>
            ))}
          </div>

          {/* Footer hint */}
          {!loading && !error && filtered.length > 0 && (
            <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400">
              {filtered.length} file{filtered.length !== 1 ? 's' : ''} · click to select
            </div>
          )}
        </div>
      )}
    </div>
  )
}
