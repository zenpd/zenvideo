import { useState, useCallback, useRef } from 'react'

/**
 * Manages the lifecycle of a single pipeline stage:
 *   idle → running → done | error
 *
 * Returns { status, logs, run(config), reset }
 */
export function useStageRunner(stageNum) {
  const [status, setStatus] = useState('idle')   // idle | running | done | error
  const [logs,   setLogs]   = useState([])
  const esRef = useRef(null)

  const reset = useCallback(() => {
    esRef.current?.close()
    setStatus('idle')
    setLogs([])
  }, [])

  const run = useCallback(async (config) => {
    // Cancel any existing stream
    esRef.current?.close()
    setStatus('running')
    setLogs([])

    try {
      const res = await fetch(`/api/stage/${stageNum}/run`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(config),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        setLogs([`API error: ${err.detail ?? res.statusText}`])
        setStatus('error')
        return
      }
      const { job_id } = await res.json()

      const es = new EventSource(`/api/jobs/${job_id}/stream`)
      esRef.current = es

      es.onmessage = (e) => {
        const event = JSON.parse(e.data)
        if (event.type === 'log') {
          setLogs((prev) => [...prev, event.msg])
        } else if (event.type === 'done') {
          setStatus('done')
          es.close()
        } else if (event.type === 'error') {
          setLogs((prev) => [...prev, `ERROR: ${event.msg}`])
          setStatus('error')
          es.close()
        }
      }
      es.onerror = () => {
        setLogs((prev) => [...prev, 'Connection lost.'])
        setStatus('error')
        es.close()
      }
    } catch (err) {
      setLogs([`Request failed: ${err.message}`])
      setStatus('error')
    }
  }, [stageNum])

  return { status, logs, run, reset }
}
