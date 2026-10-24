import type { Occurrence } from '../api/client'
import { days, dueHint, formatDate } from '../i18n/format'
import { Badge } from './ui'

/** Статус и срок остаются читаемыми независимо от цвета темы. */
export function StatusCell({ o }: { o: Occurrence }) {
  const paid = o.status === 'paid'
  const overdue = !paid && o.is_overdue
  const soon = !paid && !overdue && o.days_until_due <= 3
  const hint = paid
    ? `${o.is_overdue ? 'с опозданием · ' : ''}${formatDate(o.paid_date)}`
    : overdue
      ? `${days(o.overdue_days)} просрочки`
      : dueHint(o.days_until_due)

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Badge tone={paid ? 'paid' : overdue ? 'overdue' : soon ? 'accent' : 'neutral'}>
        {paid ? 'Оплачено' : overdue ? 'Просрочено' : soon ? 'Скоро' : 'К оплате'}
      </Badge>
      <span className="text-xs text-ink-soft whitespace-nowrap">{hint}</span>
    </span>
  )
}

export function OverdueCell({ o }: { o: Occurrence }) {
  if (!o.is_overdue) return <span className="text-ink-soft text-sm">—</span>
  return (
    <span className="text-xs text-ink-soft whitespace-nowrap" title={o.status === 'paid' ? 'Оплачено позже срока' : 'Не оплачено, срок прошёл'}>
      {o.status === 'paid' ? 'Опоздание' : 'Просрочено'} {days(o.overdue_days)}
    </span>
  )
}

export function amountHot(o: Occurrence) {
  return o.status === 'unpaid' && o.is_overdue
}
