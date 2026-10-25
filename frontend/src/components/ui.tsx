import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type HTMLAttributes,
  type TableHTMLAttributes,
  type Ref,
} from 'react'
import { createPortal } from 'react-dom'
import { Icon } from './Icon'

export const dialogCls =
  'sheet ui-dialog m-auto w-[min(32rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain p-0 text-ink'
export const dialogActionsCls = 'mt-6 flex flex-wrap justify-end gap-2'
export const dialogBtnCls = 'btn'
export const paymentsFilterRowCls = 'payments-filters payment-filters-grid'
export const filterControlCls = 'field h-11 min-h-11 box-border'
export const filterActionBtnCls = 'btn btn-ghost h-11 min-h-11 box-border shrink-0'

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  children,
  className = '',
  disabled,
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
}) {
  return (
    <button
      {...props}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`btn btn-${variant} ${size === 'sm' ? 'btn-sm' : ''} ${className}`}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}
export function Input({
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  return <input {...props} className={`field ${className}`} />
}
export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`field block w-full min-w-0 max-w-full box-border ${className}`} />
}
export function Checkbox({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} type="checkbox" className={`checkbox ${className}`} />
}

function dateDisplay(iso: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.split('-').reverse().join('.') : ''
}
function dateValue(text: string) {
  if (!/^\d{2}\.\d{2}\.\d{4}$/.test(text)) return ''
  const [day, month, year] = text.split('.').map(Number)
  const d = new Date(0)
  d.setFullYear(year, month - 1, day)
  return year >= 1 && d.getFullYear() === year && d.getMonth() === month - 1 && d.getDate() === day
    ? text.split('.').reverse().join('-')
    : ''
}
/** Visible Russian date; impossible dates block native form submission. */
export function DateInput({
  value,
  onChange,
  className = '',
  min,
  max,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type' | 'min' | 'max'> & {
  value: string
  onChange: (value: string) => void
  min?: string
  max?: string
}) {
  const [draft, setDraft] = useState(() => dateDisplay(value))
  const emitted = useRef(value)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (value !== emitted.current) setDraft(dateDisplay(value))
    emitted.current = value
  }, [value])
  const parsed = dateValue(draft)
  const invalid = Boolean(draft && (!parsed || (min && parsed < min) || (max && parsed > max)))
  useEffect(() => {
    ref.current?.setCustomValidity(
      invalid
        ? `Укажите действительную дату${min ? ` с ${dateDisplay(min)}` : ''}${max ? ` по ${dateDisplay(max)}` : ''} в формате дд.мм.гггг`
        : '',
    )
  }, [draft, invalid, min, max])
  return (
    <Input
      {...props}
      ref={ref}
      type="text"
      inputMode="numeric"
      placeholder="дд.мм.гггг"
      maxLength={10}
      autoComplete="off"
      aria-invalid={invalid || undefined}
      className={`date-input num ${className}`}
      value={draft}
      onChange={(e) => {
        const digits = e.target.value.replace(/\D/g, '').slice(0, 8)
        const masked = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('.')
        setDraft(masked)
        const next = dateValue(masked)
        emitted.current = next
        onChange(next)
      }}
    />
  )
}
export function Badge({
  children,
  tone = 'neutral',
  className = '',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: 'neutral' | 'paid' | 'overdue' | 'accent' }) {
  return (
    <span {...props} className={`badge badge-${tone} ${className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {children}
    </span>
  )
}
export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`sheet ${className}`} />
}
export function Table({ className = '', ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <table {...props} className={`ledger ${className}`} />
}
export function Skeleton({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`skeleton ${className}`} aria-hidden="true" />
}
export function EmptyState({ title, hint, icon }: { title: string; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty-state reveal-up">
      <span className="empty-state-icon" aria-hidden="true">
        {icon ?? <Icon name="wallet" />}
      </span>
      <div>
        <p className="font-medium text-sm">{title}</p>
        {hint && <div className="text-sm text-ink-soft mt-1">{hint}</div>}
      </div>
    </div>
  )
}
export const Empty = EmptyState

export function Toast({
  kind,
  children,
  leaving = false,
  onDismiss,
}: {
  kind: 'ok' | 'error'
  children: ReactNode
  leaving?: boolean
  onDismiss: () => void
}) {
  return (
    <Card className={`toast toast-${kind} text-sm ${leaving ? 'toast-leave' : 'toast-enter'}`}>
      <Icon name={kind === 'ok' ? 'check' : 'bell'} />
      <span className="flex-1">{children}</span>
      <Button variant="ghost" className="icon-button" aria-label="Закрыть уведомление" onClick={onDismiss}>
        <Icon name="close" />
      </Button>
    </Card>
  )
}

export function Tabs({
  items,
  value,
  onChange,
  className = '',
  label = 'Фильтр',
}: {
  items: { value: string; label: string; count?: number }[]
  value: string
  onChange: (value: string) => void
  className?: string
  label?: string
}) {
  return (
    <div
      className={`tabs ${className}`}
      role="tablist"
      aria-label={label}
      onKeyDown={(e) => {
        const direction = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
        if (!direction && e.key !== 'Home' && e.key !== 'End') return
        e.preventDefault()
        const current = items.findIndex((item) => item.value === value)
        const index =
          e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? items.length - 1
              : (current + direction + items.length) % items.length
        onChange(items[index].value)
        ;(e.currentTarget.children[index] as HTMLButtonElement)?.focus()
      }}
    >
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          tabIndex={value === item.value ? 0 : -1}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {item.count !== undefined && <span className="tab-count">{item.count}</span>}
        </button>
      ))}
    </div>
  )
}
export function Dialog({
  open,
  onClose,
  title,
  children,
  className = '',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const id = useId()
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      className={`${dialogCls} ${className}`}
      onClose={onClose}
      aria-labelledby={id}
      onClick={(e) => {
        if (e.target === ref.current) {
          const r = e.currentTarget.getBoundingClientRect()
          if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose()
        }
      }}
    >
      <div className="dialog-head">
        <h2 id={id}>{title}</h2>
        <Button variant="ghost" className="icon-button" aria-label="Закрыть" onClick={onClose}>
          <Icon name="close" />
        </Button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  )
}
export function Menu({ label = 'Действия', children }: { label?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const id = useId()
  useLayoutEffect(() => {
    if (!open) return
    const anchor = trigger.current!.getBoundingClientRect()
    const r = menu.current!.getBoundingClientRect()
    setPosition({
      left: Math.max(8, Math.min(anchor.right - r.width, window.innerWidth - r.width - 8)),
      top:
        anchor.bottom + r.height + 8 > window.innerHeight ? Math.max(8, anchor.top - r.height - 6) : anchor.bottom + 6,
    })
    menu.current?.querySelector('button')?.focus({ preventScroll: true })
  }, [open])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node))
        setOpen(false)
    }
    const reposition = () => {
      if (!trigger.current || !menu.current) return
      const anchor = trigger.current.getBoundingClientRect()
      const rect = menu.current.getBoundingClientRect()
      setPosition({
        left: Math.max(8, Math.min(anchor.right - rect.width, window.innerWidth - rect.width - 8)),
        top:
          anchor.bottom + rect.height + 8 > window.innerHeight
            ? Math.max(8, anchor.top - rect.height - 6)
            : anchor.bottom + 6,
      })
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="btn btn-ghost icon-button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
      >
        <Icon name="more" />
      </button>
      {open &&
        createPortal(
          <div
            id={id}
            ref={menu}
            role="menu"
            aria-label={label}
            className="action-menu"
            style={position}
            onClick={(e) => {
              if ((e.target as Element).closest('button:not(:disabled)')) {
                setOpen(false)
                trigger.current?.focus({ preventScroll: true })
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape' || e.key === 'Tab') {
                setOpen(false)
                if (e.key === 'Escape') {
                  e.preventDefault()
                  trigger.current?.focus({ preventScroll: true })
                }
                return
              }
              if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return
              e.preventDefault()
              const buttons = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
              const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
              buttons[
                e.key === 'Home'
                  ? 0
                  : e.key === 'End'
                    ? buttons.length - 1
                    : (index + (e.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
              ]?.focus()
            }}
          >
            {children}
          </div>,
          document.body,
        )}
    </>
  )
}
export function MenuItem({
  danger,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  return (
    <button
      {...props}
      type="button"
      role="menuitem"
      className={`menu-item ${danger ? 'text-overdue' : ''} ${className}`}
    />
  )
}
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
      <span className="label invisible" aria-hidden="true">
        {label}
      </span>
      {children}
    </div>
  )
}
export function PageTitle({ children, aside }: { children: ReactNode; aside?: ReactNode; hideTitleOnDesk?: boolean }) {
  return (
    <div className="page-title">
      <h1>{children}</h1>
      {aside && <div className="page-actions">{aside}</div>}
    </div>
  )
}
export function Loading({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-label={label}>
      <span className="sr-only">{label}</span>
      <Skeleton className="h-7 w-44 mb-6" />
      <div className="grid gap-4 desk:grid-cols-3 mb-6">
        {[0, 1, 2].map((n) => (
          <Skeleton key={n} className="h-36" />
        ))}
      </div>
      <Skeleton className="h-72" />
    </div>
  )
}
export function ErrorNote({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <Card className="p-4 text-sm flex flex-wrap items-center justify-between gap-3" role="alert">
      <span>{text}</span>
      {onRetry && <Button onClick={onRetry}>Повторить</Button>}
    </Card>
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
  return (
    <Dialog open={open} title={title} onClose={onClose}>
      <div className="text-sm text-ink-soft">{body}</div>
      <div className={dialogActionsCls}>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={busy}>
          {confirmText}
        </Button>
      </div>
    </Dialog>
  )
}
