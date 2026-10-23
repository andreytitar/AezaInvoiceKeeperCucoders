import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

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
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm" role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={`fade-in sheet px-4 py-3 text-sm shadow-[3px_3px_0_var(--ink)] ${t.kind === 'error' ? 'border-red text-red' : ''}`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
