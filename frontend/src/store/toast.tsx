import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { Toast as ToastMessage } from '../components/ui'

const EXIT_MS = 160

type Toast = { id: number; kind: 'ok' | 'error'; text: string; leaving?: boolean }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => {
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, leaving: true } : x)))
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), EXIT_MS)
  }, [])

  const push = useCallback(
    (kind: Toast['kind'], text: string) => {
      const id = Date.now() + Math.random()
      setItems((xs) => [...xs, { id, kind, text }])
      window.setTimeout(() => dismiss(id), kind === 'error' ? 6000 : 3500)
    },
    [dismiss],
  )

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
        {items.map((t) => (
          <ToastMessage
            key={t.id}
            kind={t.kind}
            leaving={t.leaving}
            onDismiss={() => dismiss(t.id)}
          >
            {t.text}
          </ToastMessage>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
