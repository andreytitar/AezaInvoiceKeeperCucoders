import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { Toast as ToastMessage } from '../components/ui'

type Toast = { id: number; kind: 'ok' | 'error'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs, { id, kind, text }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 3500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
        {items.map((t) => (
          <ToastMessage key={t.id} kind={t.kind} onDismiss={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}>
            {t.text}
          </ToastMessage>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
