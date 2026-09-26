import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Play, Square, Loader2 } from 'lucide-react'

const VOICES = [
  'af',
  'af_bella',
  'af_nicole',
  'af_sarah',
  'af_sky',
  'am_adam',
  'am_michael',
  'bf_emma',
  'bf_isabella',
  'bm_george',
  'bm_lewis',
]

export function VoiceSelector({ value, onChange, speed, lang }) {
  const [open, setOpen] = useState(false)
  const [loadingVoice, setLoadingVoice] = useState(null)
  const [playingVoice, setPlayingVoice] = useState(null)
  const containerRef = useRef(null)
  const audioRef = useRef(null)
  const urlRef = useRef(null)

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target)
      ) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)

      if (audioRef.current) {
        audioRef.current.pause()
      }

      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
      }
    }
  }, [])

  const stopPreview = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }

    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }

    setPlayingVoice(null)
    setLoadingVoice(null)
  }

  const previewVoice = async (voice, event) => {
    event.stopPropagation()

    if (playingVoice === voice) {
      stopPreview()
      return
    }

    stopPreview()

    try {
      setLoadingVoice(voice)

      const response = await fetch(
        `/api/tts/preview/${encodeURIComponent(voice)}?speed=${speed}&lang=${encodeURIComponent(lang)}`
      )

      if (!response.ok) {
        throw new Error('Failed to generate voice preview')
      }

      const blob = await response.blob()
      const audioUrl = URL.createObjectURL(blob)

      const audio = new Audio(audioUrl)
      audioRef.current = audio
      urlRef.current = audioUrl

      audio.onended = () => {
        setPlayingVoice(null)
        URL.revokeObjectURL(audioUrl)
        urlRef.current = null
      }

      setLoadingVoice(null)
      setPlayingVoice(voice)

      await audio.play()
    } catch (error) {
      console.error('Voice preview failed:', error)
      setLoadingVoice(null)
      setPlayingVoice(null)
    }
  }

  const selectVoice = (voice) => {
    onChange(voice)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="input flex w-full items-center justify-between text-left"
      >
        <span>{value}</span>

        <ChevronDown
          size={14}
          className={`transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg">
          <div className="max-h-64 overflow-y-auto py-1">
            {VOICES.map((voice) => {
              const isSelected = value === voice
              const isLoading = loadingVoice === voice
              const isPlaying = playingVoice === voice

              return (
                <div
                  key={voice}
                  className={`flex items-center justify-between px-3 py-2 ${
                    isSelected
                      ? 'bg-zen-50'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectVoice(voice)}
                    className="flex-1 text-left text-sm text-gray-700"
                  >
                    {voice}
                  </button>

                  <button
                    type="button"
                    onClick={(event) => previewVoice(voice, event)}
                    disabled={isLoading}
                    className="ml-2 flex items-center gap-1 rounded-md bg-zen-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-zen-700 disabled:cursor-not-allowed disabled:opacity-60"
                    title={`Preview ${voice}`}
                  >
                    {isLoading ? (
                      <Loader2 size={11} className="animate-spin" />
                    ) : isPlaying ? (
                      <Square size={10} />
                    ) : (
                      <Play size={10} />
                    )}

                    {isLoading
                      ? 'Loading'
                      : isPlaying
                        ? 'Stop'
                        : 'Preview'}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}