/**
 * Stage metadata + default configs.
 * Any stage runs independently — no ordering enforced.
 */

/** Light-theme color tokens per stage (ZenArc palette) */
export const STAGE_COLORS = {
  0: {  // WebM → MP4       — amber
    bar:      'from-amber-500 to-amber-600',
    icon_bg:  'bg-amber-50',
    icon_fg:  'text-amber-600',
    badge:    'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    tag_bg:   'bg-amber-50',
    tag_text: 'text-amber-700',
    cfg_bg:   'bg-amber-50/30',
    glow:     'hover:shadow-glow-amber',
  },
  1: {  // Format Transcript — violet
    bar:      'from-violet-500 to-violet-600',
    icon_bg:  'bg-violet-50',
    icon_fg:  'text-violet-600',
    badge:    'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
    tag_bg:   'bg-violet-50',
    tag_text: 'text-violet-700',
    cfg_bg:   'bg-violet-50/30',
    glow:     '',
  },
  2: {  // Generate TTS      — zen/indigo
    bar:      'from-zen-500 to-zen-600',
    icon_bg:  'bg-zen-50',
    icon_fg:  'text-zen-600',
    badge:    'bg-zen-50 text-zen-700 ring-1 ring-zen-200',
    tag_bg:   'bg-zen-50',
    tag_text: 'text-zen-700',
    cfg_bg:   'bg-zen-50/30',
    glow:     'hover:shadow-glow-zen',
  },
  3: {  // Sync & Merge      — emerald
    bar:      'from-emerald-500 to-emerald-600',
    icon_bg:  'bg-emerald-50',
    icon_fg:  'text-emerald-600',
    badge:    'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    tag_bg:   'bg-emerald-50',
    tag_text: 'text-emerald-700',
    cfg_bg:   'bg-emerald-50/30',
    glow:     'hover:shadow-glow-emerald',
  },
}

export const STAGES = [
  {
    num:         0,
    name:        'Convert WebM → MP4',
    description: 'Convert a .webm screen recording to MP4. Run this before Stage 3 if your video is a webm.',
    outputs:     ['Recording.mp4'],
    fields: [
      { key: 'webm_path',   label: 'WebM input file',  type: 'text',   default: 'Recording.webm',  help: 'Path to your .webm screen recording' },
      { key: 'output_path', label: 'MP4 output file',  type: 'text',   default: 'Recording.mp4' },
      { key: 'preset',      label: 'Encoding preset',  type: 'select', default: 'medium', options: ['fast','medium','slow'], help: 'Slower = smaller file' },
      { key: 'crf',         label: 'CRF quality',      type: 'number', default: '23', min: 0, max: 51, help: '0=lossless · 23=default · 51=worst' },
    ],
  },
  {
    num:         1,
    name:        'Format Transcript',
    description: 'Reads raw_transcript.txt, converts numbers to spoken words, and writes timed transcript.txt.',
    outputs:     ['transcript.txt'],
    fields: [
      { key: 'raw_path', label: 'Raw transcript',           type: 'text',   default: 'raw_transcript.txt' },
      { key: 'out_path', label: 'Output transcript',        type: 'text',   default: 'transcript.txt' },
      { key: 'wpm',      label: 'WPM (words / min)',        type: 'number', default: 180, min: 60, max: 400, help: 'Sets the segment timing' },
      { key: 'gap_sec',  label: 'Gap between segments (s)', type: 'number', default: 1, min: 0, max: 10 },
    ],
  },
  {
    num:         2,
    name:        'Generate TTS Audio',
    description: 'Synthesises speech from transcript.txt using Kokoro ONNX. Outputs per-segment MP3s + final_audio.mp3.',
    outputs:     ['final_audio.mp3', 'segments/'],
    fields: [
      { key: 'transcript_path',  label: 'Transcript',              type: 'text',   default: 'transcript.txt' },
      { key: 'model_path',       label: 'Kokoro model (.onnx)',    type: 'text',   default: 'kokoro-v0_19.onnx' },
      { key: 'voices_path',      label: 'Voices file (.bin)',      type: 'text',   default: 'voices.bin' },
      { key: 'voice',            label: 'Voice ID',                type: 'text',   default: 'af_sky', help: 'e.g. af_sky · af_bella · am_adam' },
      { key: 'speed',            label: 'Speed',                   type: 'number', default: 1.1, min: 0.5, max: 2.0, step: 0.05 },
      { key: 'lang',             label: 'Language',                type: 'select', default: 'en-us', options: ['en-us','en-gb','ja','zh','ko','fr','de'] },
      { key: 'segments_dir',     label: 'Segments folder',         type: 'text',   default: 'segments' },
      { key: 'final_audio_path', label: 'Output audio',            type: 'text',   default: 'final_audio.mp3' },
      { key: 'gap_ms',           label: 'Gap between segments (ms)',type: 'number', default: 1000, min: 0, max: 5000, step: 100 },
    ],
  },
  {
    num:         3,
    name:        'Sync & Merge',
    description: 'Merges TTS audio with video, auto-adjusting audio tempo so both tracks match in length.',
    outputs:     ['output.mp4'],
    fields: [
      { key: 'video_path',    label: 'Input video',           type: 'text',   default: 'paycontrol_sb_trim2.mp4' },
      { key: 'audio_path',    label: 'TTS audio',             type: 'text',   default: 'final_audio.mp3' },
      { key: 'output_path',   label: 'Output video',          type: 'text',   default: 'output.mp4' },
      { key: 'audio_bitrate', label: 'Audio bitrate',         type: 'text',   default: '128k' },
      { key: 'sample_rate',   label: 'Sample rate (Hz)',      type: 'number', default: 48000, step: 1000 },
      { key: 'tolerance',     label: 'Tempo tolerance (0–1)', type: 'number', default: 0.1, min: 0, max: 0.5, step: 0.01, help: 'Skip adjustment if diff < this fraction' },
    ],
  },
]
