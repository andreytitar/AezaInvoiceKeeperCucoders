import type { Occurrence } from '../api/client'
import { days, dueHint } from '../i18n/format'

/** Один плоский штамп на оплаченной строке. Красный здесь не используется: его несёт сумма. */
export function StatusCell({ o }: { o: Occurrence }) {
  if (o.status === 'paid') return <span className="stamp text-paid">Оплачено</span>
  const soon = !o.is_overdue && o.days_until_due <= 3
  return (
    <span className="text-sm flex flex-col leading-tight">
      <span>Не оплачено</span>
      {!o.is_overdue && (
        <span className={`text-xs ${soon ? 'font-semibold text-ink' : 'text-ink-soft'}`}>срок {dueHint(o.days_until_due)}</span>
      )}
    </span>
  )
}

export function OverdueCell({ o }: { o: Occurrence }) {
  if (!o.is_overdue) return <span className="text-ink-soft text-sm">—</span>
  if (o.status === 'paid') {
    return (
      <span className="text-xs text-ink-soft num" title="Оплачено позже срока">
        опоздание {days(o.overdue_days)}
      </span>
    )
  }
  return (
    <span className="text-sm num" title="Не оплачено, срок прошёл">
      просрочено {days(o.overdue_days)}
    </span>
  )
}

export function amountHot(o: Occurrence) {
  return o.status === 'unpaid' && o.is_overdue
}
