import { useEffect, useRef, type ReactNode } from 'react'

export function PageTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5 border-b-[3px] border-double border-ink pb-2">
      <h1 className="font-serif text-2xl sm:text-3xl font-bold tracking-tight">{children}</h1>
      {aside}
    </div>
  )
}

export function Loading({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="py-10 text-center text-ink-soft text-sm" role="status">
      <span className="num animate-pulse">{label}</span>
    </div>
  )
}

export function ErrorNote({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="sheet border-red p-4 text-sm text-red flex items-center justify-between gap-3" role="alert">
      <span>{text}</span>
      {onRetry && (
        <button className="btn btn-sm btn-danger" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="py-12 px-4 text-center">
      <p className="font-serif text-lg">{title}</p>
      {hint && <p className="text-sm text-ink-soft mt-1">{hint}</p>}
    </div>
  )
}

type ConfirmProps = {
  open: boolean
  title: string
  body?: ReactNode
  confirmText: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function ConfirmDialog({ open, title, body, confirmText, danger, busy, onConfirm, onClose }: ConfirmProps) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="sheet m-auto w-[min(92vw,26rem)] p-0 text-ink backdrop:bg-black/40 shadow-[4px_4px_0_var(--ink)]"
      aria-labelledby="confirm-title"
    >
      <div className="p-5">
        <h2 id="confirm-title" className="font-serif text-xl font-bold mb-2">
          {title}
        </h2>
        {body && <div className="text-sm text-ink-soft">{body}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm} disabled={busy} autoFocus>
            {busy ? '…' : confirmText}
          </button>
        </div>
      </div>
    </dialog>
  )
}
