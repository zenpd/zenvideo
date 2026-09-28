import { useState, useEffect, useCallback } from 'react'

/**
 * Polls /api/status every `interval` ms.
 * Returns { files, online, refresh }
 */
export function useStatus(interval = 4000) {
  const [files,  setFiles]  = useState({})
  const [online, setOnline] = useState(null)   // null = not yet checked

  const refresh = useCallback(async () => {
    try {
      const res  = await fetch('/api/status')
      const data = await res.json()
      setFiles(data)
      setOnline(true)
    } catch (_) {
      // server not reachable — keep previous file state, flag offline
      setOnline(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, interval)
    return () => clearInterval(id)
  }, [refresh, interval])

  return { files, online, refresh }
}
