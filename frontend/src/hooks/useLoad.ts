import { useCallback, useEffect, useRef, useState } from 'react'

/** Загрузка данных с состояниями loading/error и ручной перезагрузкой. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)

  const reload = useCallback(async () => {
    const my = ++seq.current
    setLoading(true)
    try {
      const d = await run()
      if (my === seq.current) {
        setData(d)
        setError(null)
      }
    } catch (e) {
      if (my === seq.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (my === seq.current) setLoading(false)
    }
  }, [run])

  useEffect(() => {
    reload()
  }, [reload])

  return { data, error, loading, reload, setData }
}
