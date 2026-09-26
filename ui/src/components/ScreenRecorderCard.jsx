import { useState, useEffect, useRef } from 'react'
import {
  MonitorPlay, Square, Settings, ChevronDown,
  Mic, Monitor, RefreshCw, Download, Circle,
  AlertCircle,
} from 'lucide-react'

const COLORS = {
  bar:      'from-rose-500 to-pink-500',
  icon_bg:  'bg-rose-50',
  icon_fg:  'text-rose-600',
  tag_bg:   'bg-rose-50',
  tag_text: 'text-rose-700',
  cfg_bg:   'bg-rose-50/20',
}

function ElapsedTimer({ active }) {
  const [secs, setSecs] = useState(0)
  const ref = useRef(null)

  useEffect(() => {
    if (active) {
      setSecs(0)
      ref.current = setInterval(() => setSecs(s => s + 1), 1000)
    } else {
      clearInterval(ref.current)
    }
    return () => clearInterval(ref.current)
  }, [active])

  if (!active) return null
  const m = String(Math.floor(secs / 60)).padStart(2, '0')
  const s = String(secs % 60).padStart(2, '0')
  return (
    <span className="font-mono text-sm font-bold text-rose-600 tabular-nums">
      {m}:{s}
    </span>
  )
}

export function ScreenRecorderCard() {
  const [devices, setDevices]         = useState({ video: [], audio: [] })
  const [devicesLoaded, setDevicesLoaded] = useState(false)
  const [configOpen, setConfigOpen]   = useState(false)
  const [recording, setRecording]     = useState(false)
  const [outputPath, setOutputPath]   = useState('recording.webm')
  const [videoIdx, setVideoIdx]       = useState('1')
  const [audioIdx, setAudioIdx]       = useState('0')
  const [framerate, setFramerate]     = useState(30)
  const [audioBitrate, setAudioBitrate] = useState('192k')
  const [error, setError]             = useState(null)
  const [lastFile, setLastFile]       = useState(null)

  const loadDevices = async () => {
    try {
      const res  = await fetch('/api/stage/5/devices')
      const data = await res.json()
      setDevices(data)
      setDevicesLoaded(true)
      // auto-pick screen device
      const screenDev = data.video?.find(d => /screen|display/i.test(d.name))
      if (screenDev) setVideoIdx(screenDev.idx)
    } catch {
      setError('Could not reach API — is the FastAPI server running?')
    }
  }

  // Poll recording status on mount
  useEffect(() => {
    fetch('/api/stage/5/status')
      .then(r => r.json())
      .then(d => setRecording(d.active))
      .catch(() => {})
    loadDevices()
  }, [])

  const startRecording = async () => {
    setError(null)
    try {
      const res = await fetch('/api/stage/5/start', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_path:   outputPath,
          video_idx:     videoIdx,
          audio_idx:     audioIdx,
          framerate,
          audio_bitrate: audioBitrate,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail ?? 'Failed to start recording')
        return
      }
      setRecording(true)
      setLastFile(null)
    } catch (e) {
      setError(`Request failed: ${e.message}`)
    }
  }

  const stopRecording = async () => {
    try {
      const res  = await fetch('/api/stage/5/stop', { method: 'POST' })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail ?? 'Failed to stop')
        return
      }
      setRecording(false)
      setLastFile(outputPath)
      if (data.note) {
        setError(`${data.note}. If this keeps happening, grant your terminal/ffmpeg Screen
                   Recording permission in System Settings → Privacy & Security.`)
      }
    } catch (e) {
      setError(`Request failed: ${e.message}`)
    }
  }

  return (
    <div className={`card flex flex-col overflow-hidden transition-all duration-200
                     border-rose-200/60
                     ${recording ? 'ring-2 ring-rose-400 shadow-card-hover' : ''}`}>

      {/* ── Gradient bar ── */}
      <div className={`h-1 w-full rounded-t-2xl bg-gradient-to-r ${COLORS.bar}`} />

      {/* ── Header ── */}
      <div className="p-5 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl ${COLORS.icon_bg} flex items-center justify-center shrink-0`}>
              <MonitorPlay size={20} className={COLORS.icon_fg} />
            </div>
            <div>
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest leading-tight mb-0.5">
                Stage 5
              </p>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900">Screen Recorder</h3>
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full
                                 bg-rose-500 text-white uppercase tracking-wider">
                  NEW
                </span>
              </div>
            </div>
          </div>

          {/* Recording indicator */}
          {recording && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500" />
              </span>
              <ElapsedTimer active={recording} />
            </div>
          )}
        </div>

        <p className="text-xs text-gray-500 mt-3 leading-relaxed">
          Capture screen + microphone using FFmpeg avfoundation (macOS).
          Output is a <code className="text-xs bg-gray-100 px-1 rounded">.webm</code> ready for Stage 6.
        </p>

        {/* ── Input source selects ── */}
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div>
            <label className="label flex items-center gap-1.5">
              <Monitor size={11} /> Video source
              <button onClick={loadDevices} className="ml-auto text-gray-400 hover:text-gray-700" title="Refresh devices">
                <RefreshCw size={10} />
              </button>
            </label>
            <select value={videoIdx} onChange={e => setVideoIdx(e.target.value)}
                    className="input" disabled={recording}>
              {devicesLoaded
                ? devices.video.map(d => (
                    <option key={d.idx} value={d.idx}>[{d.idx}] {d.name}</option>
                  ))
                : <option>Loading…</option>
              }
            </select>
          </div>
          <div>
            <label className="label flex items-center gap-1.5">
              <Mic size={11} /> Audio source
            </label>
            <select value={audioIdx} onChange={e => setAudioIdx(e.target.value)}
                    className="input" disabled={recording}>
              {devicesLoaded
                ? devices.audio.map(d => (
                    <option key={d.idx} value={d.idx}>[{d.idx}] {d.name}</option>
                  ))
                : <option>Loading…</option>
              }
            </select>
          </div>
        </div>

        {/* Output tag */}
        <div className="mt-3">
          <span className={`inline-flex items-center gap-1 text-[11px] font-semibold
                            px-2.5 py-0.5 rounded-full ${COLORS.tag_bg} ${COLORS.tag_text}`}>
            → {outputPath}
          </span>
        </div>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="mx-5 mb-2 flex items-start gap-2 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
          <AlertCircle size={13} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Config toggle ── */}
      <button
        onClick={() => setConfigOpen(v => !v)}
        className="flex items-center gap-2 px-5 py-2.5 text-xs font-medium text-gray-400
                   hover:text-gray-700 hover:bg-gray-50 border-t border-gray-100
                   transition-colors w-full text-left"
      >
        <Settings size={13} />
        <span>Configure</span>
        <ChevronDown size={13}
          className={`ml-auto transition-transform duration-200 ${configOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* ── Config panel ── */}
      {configOpen && (
        <div className={`px-5 pb-5 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4
                         border-t border-gray-100 ${COLORS.cfg_bg}`}>

          {/* Output path */}
          <div className="sm:col-span-2">
            <label className="label">Output file</label>
            <input value={outputPath} onChange={e => setOutputPath(e.target.value)}
                   className="input" placeholder="recording.webm" disabled={recording} />
            <p className="mt-1 text-[11px] text-gray-400">Use .webm for Stage 4, or .mp4 for direct use</p>
          </div>

          {/* Framerate */}
          <div>
            <label className="label">Frame rate (fps)</label>
            <select value={framerate} onChange={e => setFramerate(Number(e.target.value))}
                    className="input" disabled={recording}>
              {[15, 24, 30, 60].map(f => <option key={f} value={f}>{f} fps</option>)}
            </select>
          </div>

          {/* Audio bitrate */}
          <div>
            <label className="label">Audio bitrate</label>
            <select value={audioBitrate} onChange={e => setAudioBitrate(e.target.value)}
                    className="input" disabled={recording}>
              {['96k','128k','192k','256k'].map(b => <option key={b}>{b}</option>)}
            </select>
          </div>
        </div>
      )}

      {/* ── Action bar ── */}
      <div className="px-5 py-4 border-t border-gray-100 flex gap-2 mt-auto">
        {!recording ? (
          <button
            onClick={startRecording}
            className="flex-1 btn-primary justify-center"
          >
            <Circle size={14} className="fill-white" />
            Start Recording
          </button>
        ) : (
          <button
            onClick={stopRecording}
            className="flex-1 btn flex items-center justify-center gap-2
                       bg-rose-600 hover:bg-rose-700 text-white shadow-sm"
          >
            <Square size={14} className="fill-white" />
            Stop Recording
          </button>
        )}

        {lastFile && (
          <a
            href={`/api/download/${lastFile}`}
            download
            className="btn btn-secondary btn-sm !px-3"
            title={`Download ${lastFile}`}
          >
            <Download size={13} />
            <span className="hidden sm:inline text-xs">{lastFile}</span>
          </a>
        )}
      </div>

      {/* ── Quick tip ── */}
      <div className="px-5 pb-4 text-[11px] text-gray-400">
        Tip: after recording, feed the output into{' '}
        <span className="font-semibold text-rose-500">Stage 6</span> with your transcript for a synced MP4.
      </div>
    </div>
  )
}
