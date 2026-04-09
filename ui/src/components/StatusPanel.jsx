import { RefreshCw, HardDrive } from 'lucide-react'

function fmtSize(bytes) {
  if (!bytes) return null
  if (bytes > 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes > 1024)      return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

const FILE_META = {
  raw_transcript: { label: 'raw_transcript.txt', icon: '📄' },
  transcript:     { label: 'transcript.txt',     icon: '📝' },
  final_audio:    { label: 'final_audio.mp3',    icon: '🎵' },
  video_file:     { label: 'Input video',         icon: '🎥' },
  output_video:   { label: 'output.mp4',          icon: '🎬' },
  kokoro_model:   { label: 'Kokoro model',        icon: '🤖' },
  voices_bin:     { label: 'voices.bin',          icon: '🔊' },
  segments:       { label: 'segments/',           icon: '📁' },
}

function FileChip({ fileKey, item }) {
  const meta = FILE_META[fileKey] ?? { label: fileKey, icon: '📄' }
  const ok   = item?.exists

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-medium
                  transition-colors ${ok
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                    : 'bg-gray-50  border-gray-200   text-gray-400'}`}
    >
      <span className="text-sm leading-none">{meta.icon}</span>
      <span className="truncate">{meta.label}</span>
      {ok && item.size > 0 && (
        <span className="ml-auto text-emerald-500 font-mono text-[10px] shrink-0">
          {fmtSize(item.size)}
        </span>
      )}
      {ok && item.count !== undefined && (
        <span className="ml-auto text-emerald-500 font-mono text-[10px] shrink-0">
          {item.count} segs
        </span>
      )}
    </div>
  )
}

export function StatusPanel({ files, onRefresh }) {
  const ready  = Object.values(files).filter((f) => f?.exists).length
  const total  = Object.keys(FILE_META).length

  return (
    <div className="card p-5 mb-6 animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <HardDrive size={14} className="text-gray-400" />
          <span className="section-title mb-0">Pipeline Files</span>
          <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px]
                           font-bold bg-zen-50 text-zen-600 ring-1 ring-zen-200">
            {ready} / {total}
          </span>
        </div>
        <button
          onClick={onRefresh}
          className="btn btn-ghost btn-sm"
          title="Refresh file status"
        >
          <RefreshCw size={13} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {Object.keys(FILE_META).map((key) => (
          <FileChip key={key} fileKey={key} item={files[key]} />
        ))}
      </div>
    </div>
  )
}
