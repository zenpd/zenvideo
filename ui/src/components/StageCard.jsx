import { useState } from 'react'
import {
  Play, RotateCcw, Settings, ChevronDown,
  Video, FileText, Mic, Film, Combine,
  CheckCircle2, XCircle, Loader, Download,
} from 'lucide-react'
import { STAGE_COLORS } from '../stages'
import { useStageRunner } from '../hooks/useStageRunner'
import { StageConfig } from './StageConfig'
// import { VoicePreview } from './VoicePreview'
import { LogTerminal } from './LogTerminal'

const ICONS = { 0: Video, 1: FileText, 2: Mic, 3: Film, 4: Video, 6: Combine }

function StatusBadge({ status }) {
  if (status === 'idle')    return <span className="badge-idle">idle</span>
  if (status === 'running') return (
    <span className="badge-running flex items-center gap-1">
      <Loader size={10} className="animate-spin" /> running
    </span>
  )
  if (status === 'done')    return (
    <span className="badge-done flex items-center gap-1">
      <CheckCircle2 size={10} /> done
    </span>
  )
  if (status === 'error')   return (
    <span className="badge-error flex items-center gap-1">
      <XCircle size={10} /> error
    </span>
  )
}

export function StageCard({ stage }) {
  const { num, name, description, fields, outputs } = stage
  const c    = STAGE_COLORS[num]
  const Icon = ICONS[num]

  const [config, setConfig] = useState(
    Object.fromEntries(fields.map((f) => [f.key, f.default]))
  )
  const [configOpen, setConfigOpen] = useState(false)

  const { status, logs, run, reset } = useStageRunner(num)

  const handleChange = (key, val) => setConfig((prev) => ({ ...prev, [key]: val }))

  return (
    <div
      className={`card flex flex-col overflow-hidden transition-all duration-200
                  hover:-translate-y-0.5 ${c.glow}
                  ${status === 'running' ? 'ring-2 ring-zen-200 shadow-card-hover' : ''}`}
    >
      {/* ── Gradient top bar ── */}
      <div className={`h-1 w-full rounded-t-2xl bg-gradient-to-r ${c.bar}`} />

      {/* ── Header ── */}
      <div className="p-5 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl ${c.icon_bg} flex items-center justify-center shrink-0`}>
              <Icon size={20} className={c.icon_fg} />
            </div>
            <div>
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest leading-tight mb-0.5">
                Stage {num}
              </p>
              <h3 className="text-sm font-bold text-gray-900 leading-snug">{name}</h3>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={status} />
            {(status === 'done' || status === 'error') && (
              <button
                onClick={reset}
                className="btn btn-ghost btn-sm !px-1.5 !py-1 text-gray-400 hover:text-gray-700"
                title="Reset"
              >
                <RotateCcw size={13} />
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-gray-500 mt-3 leading-relaxed">{description}</p>

        {/* Output tags */}
        {outputs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {outputs.map((out) => (
              <span
                key={out}
                className={`inline-flex items-center gap-1 text-[11px] font-semibold
                            px-2.5 py-0.5 rounded-full ${c.tag_bg} ${c.tag_text}`}
              >
                → {out}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Config toggle ── */}
      <button
        onClick={() => setConfigOpen((v) => !v)}
        className="flex items-center gap-2 px-5 py-2.5 text-xs font-medium text-gray-400
                   hover:text-gray-700 hover:bg-gray-50 border-t border-gray-100
                   transition-colors w-full text-left"
      >
        <Settings size={13} />
        <span>Configure</span>
        <ChevronDown
          size={13}
          className={`ml-auto transition-transform duration-200 ${configOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* ── Config panel ── */}
      {configOpen && (
          <StageConfig
            fields={fields}
            values={config}
            onChange={handleChange}
            colors={c}
          />
      )}

      {/* ── Action bar ── */}
      <div className="px-5 py-4 border-t border-gray-100 flex gap-2 mt-auto">
        <button
          onClick={() => run(config)}
          disabled={status === 'running'}
          className="btn-primary flex-1 justify-center"
        >
          {status === 'running' ? (
            <><Loader size={14} className="animate-spin" /> Running…</>
          ) : (
            <><Play size={14} /> Run Stage {num}</>
          )}
        </button>

        {/* Download first output when done */}
        {status === 'done' && outputs[0] && !outputs[0].endsWith('/') && (
          <a
            href={`/api/download/${outputs[0]}`}
            download
            className="btn btn-secondary btn-sm !px-3 shrink-0"
            title={`Download ${outputs[0]}`}
          >
            <Download size={13} />
            <span className="hidden sm:inline text-xs">{outputs[0]}</span>
          </a>
        )}
      </div>

      {/* ── Terminal log ── */}
      <LogTerminal logs={logs} status={status} onClear={reset} />
    </div>
  )
}
