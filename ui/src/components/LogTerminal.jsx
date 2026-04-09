import { useEffect, useRef } from 'react'
import { Terminal, X, CheckCircle2, XCircle, Loader } from 'lucide-react'

function lineClass(line) {
  const l = line.toLowerCase()
  if (l.includes('error') || l.includes('failed') || l.includes('❌'))
    return 'text-red-400'
  if (l.includes('done') || l.includes('created') || l.includes('✅') || l.includes('success'))
    return 'text-emerald-400'
  if (l.includes('loading') || l.includes('converting') || l.includes('generating') || l.includes('merging'))
    return 'text-yellow-300'
  if (l.match(/^\[?\d{2}:\d{2}:\d{2}/))
    return 'text-sky-300'
  if (l.includes('warning') || l.includes('⚠'))
    return 'text-amber-300'
  return 'text-slate-300'
}

const STATUS_UI = {
  running: { icon: <Loader size={12} className="animate-spin text-blue-400"  />, label: 'running', cls: 'text-blue-400' },
  done:    { icon: <CheckCircle2 size={12} className="text-emerald-400" />,    label: 'done',    cls: 'text-emerald-400' },
  error:   { icon: <XCircle     size={12} className="text-red-400" />,         label: 'error',   cls: 'text-red-400' },
}

export function LogTerminal({ logs, status, onClear }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  if (logs.length === 0) return null

  const s = STATUS_UI[status]

  return (
    <div className="mx-5 mb-5 rounded-xl overflow-hidden border border-slate-700/60 animate-slide-up shadow-sm">
      {/* Title bar */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-slate-800 border-b border-slate-700/60">
        <div className="flex items-center gap-2 text-xs">
          <Terminal size={11} className="text-slate-400" />
          <span className="font-mono text-slate-400">output</span>
          {s && (
            <span className={`flex items-center gap-1 font-mono ${s.cls}`}>
              {s.icon} {s.label}
            </span>
          )}
        </div>
        <button
          onClick={onClear}
          className="text-slate-500 hover:text-slate-300 transition-colors"
          title="Clear"
        >
          <X size={13} />
        </button>
      </div>

      {/* Lines */}
      <div className="bg-[#0d1117] p-3.5 max-h-60 overflow-y-auto font-mono text-xs leading-relaxed">
        {logs.map((line, i) => (
          <div key={i} className={`${lineClass(line)} whitespace-pre-wrap break-all`}>
            {line || '\u00A0'}
          </div>
        ))}
        {status === 'running' && (
          <span className="text-slate-500 animate-pulse-dot">▌</span>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
