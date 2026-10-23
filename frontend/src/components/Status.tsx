import type { Occurrence } from '../api/client'
import { days, dueHint } from '../i18n/format'

/** Статус оплаты: штамп «оплачено» или «не оплачено» с подсказкой о сроке. */
export function StatusCell({ o }: { o: Occurrence }) {
  if (o.status === 'paid') return <span className="stamp">Оплачено</span>
  const soon = !o.is_overdue && o.days_until_due <= 3
  return (
    <span className="text-sm flex flex-col leading-tight">
      <span>Не оплачено</span>
      {!o.is_overdue && (
        <span className={`text-xs ${soon ? 'text-amber font-semibold' : 'text-ink-soft'}`}>
          {soon ? '◆ ' : ''}срок {dueHint(o.days_until_due)}
        </span>
      )}
    </span>
  )
}

/** Просрочка: бейдж и число дней. Цвет дублируется текстом и знаком. */
export function OverdueCell({ o }: { o: Occurrence }) {
  if (!o.is_overdue) return <span className="text-ink-soft text-sm" aria-label="Без просрочки">—</span>
  if (o.status === 'paid') {
    return (
      <span className="text-xs text-red num" title="Оплачено позже срока">
        ! опоздание {days(o.overdue_days)}
      </span>
    )
  }
  return (
    <span className="overdue-ink text-sm font-semibold num" title="Не оплачено, срок прошёл">
      ! {days(o.overdue_days)}
    </span>
  )
}
