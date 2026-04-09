import { useState, useEffect, useCallback } from 'react'

/**
 * Polls /api/status every `interval` ms.
 * Returns { files, refresh }
 */
export function useStatus(interval = 4000) {
  const [files, setFiles] = useState({})

  const refresh = useCallback(async () => {
    try {
      const res  = await fetch('/api/status')
      const data = await res.json()
      setFiles(data)
    } catch (_) {
      // server not yet available — keep previous state
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, interval)
    return () => clearInterval(id)
  }, [refresh, interval])

  return { files, refresh }
}
