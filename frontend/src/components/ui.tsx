import { useEffect, useRef, type ReactNode } from 'react'

export const dialogCls =
  'sheet m-auto w-[min(32rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain p-0 text-ink'

export const dialogActionsCls = 'mt-5 flex flex-col gap-2 desk:flex-row desk:flex-wrap desk:justify-end'

export const dialogBtnCls = 'btn w-full desk:w-auto'

/** Строка фильтров на дашборде: одинаковая высота контролов 44px, зазор ~12px. */
export const paymentsFilterRowCls =
  'payments-filters grid grid-cols-1 desk:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-2.5 desk:gap-3 items-end mb-3 desk:mb-4'

export const filterControlCls = 'field h-11 min-h-11 box-border'

export const filterActionBtnCls = 'btn btn-ghost h-11 min-h-11 box-border w-full desk:w-auto shrink-0'

export function FilterField({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label className="label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  )
}

export function FilterFieldAction({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 flex flex-col">
      <span className="label invisible block" aria-hidden="true">
        {label}
      </span>
      {children}
    </div>
  )
}

export function PageTitle({
  children,
  aside,
  hideTitleOnDesk,
}: {
  children: ReactNode
  aside?: ReactNode
  /** Заголовок уже на win-titlebar — на desktop не дублируем визуально. */
  hideTitleOnDesk?: boolean
}) {
  return (
    <div
      className={`page-title flex flex-wrap items-end justify-between gap-2 mb-4 pb-1 ${aside && hideTitleOnDesk ? 'desk:mb-3 desk:border-0 desk:pb-0 desk:justify-end' : 'border-b border-rule pb-2'}`}
    >
      <h1
        className={`font-sans text-xl desk:text-2xl font-semibold tracking-tight ${hideTitleOnDesk ? 'desk:sr-only' : ''}`}
      >
        {children}
      </h1>
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
    <div className="sheet p-4 text-sm text-ink flex flex-wrap items-center justify-between gap-3" role="alert">
      <span>{text}</span>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="py-12 px-4 text-center">
      <p className="font-sans text-lg">{title}</p>
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
    <dialog ref={ref} onClose={onClose} className={dialogCls} aria-labelledby="confirm-title">
      <div className="p-4">
        <h2 id="confirm-title" className="font-sans text-xl font-semibold mb-2">
          {title}
        </h2>
        {body && <div className="text-sm text-ink-soft">{body}</div>}
        <div className={dialogActionsCls}>
          <button className={dialogBtnCls} onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button className={`${dialogBtnCls} ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm} disabled={busy} autoFocus>
            {busy ? '…' : confirmText}
          </button>
        </div>
      </div>
    </dialog>
  )
}
