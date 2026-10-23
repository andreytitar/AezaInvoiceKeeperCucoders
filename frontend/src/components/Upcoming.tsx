import { api, unwrap, type Occurrence } from '../api/client'
import { useLoad } from '../hooks/useLoad'
import { days, dueHint, formatDate, formatMoney, parseISODate, toISODate } from '../i18n/format'

type Props = { today: string; version: number; onPay: (o: Occurrence) => void; busy: boolean }

function addDays(iso: string, n: number) {
  const d = parseISODate(iso)
  d.setDate(d.getDate() + n)
  return toISODate(d)
}

function Column({ title, tone, items, total, render, empty }: {
  title: string
  tone?: 'red'
  items: Occurrence[] | undefined
  total: number | undefined
  render: (o: Occurrence) => React.ReactNode
  empty: string
}) {
  return (
    <section className="p-4 min-w-0" aria-label={title}>
      <h2 className={`font-serif text-lg font-bold flex items-baseline justify-between ${tone === 'red' ? 'text-red' : ''}`}>
        {title}
        <span className="num text-sm font-normal text-ink-soft">{total ?? '…'}</span>
      </h2>
      {!items ? (
        <p className="text-sm text-ink-soft num mt-2">…</p>
      ) : !items.length ? (
        <p className="text-sm text-ink-soft mt-2">{empty}</p>
      ) : (
        <ul className="mt-2 divide-y divide-rule">{items.map((o) => <li key={o.id} className="py-1.5 flex items-center gap-2">{render(o)}</li>)}</ul>
      )}
    </section>
  )
}

function useTop5(query: Record<string, unknown>, deps: unknown[]) {
  return useLoad(
    async () => unwrap(await api.GET('/api/v1/payment-occurrences', { params: { query: { page_size: 5, ...query } as never } })),
    deps,
  )
}

/** Дашборд: что просрочено, что оплатить в ближайшие 7 дней, что оплачено недавно. */
export function Upcoming({ today, version, onPay, busy }: Props) {
  const overdue = useTop5({ status: 'unpaid', overdue: true, sort: 'due_date' }, [today, version])
  const soon = useTop5({ status: 'unpaid', overdue: false, to: addDays(today, 7), sort: 'due_date' }, [today, version])
  const paid = useTop5({ status: 'paid', sort: '-paid_date' }, [today, version])

  const line = (o: Occurrence, hint: React.ReactNode, action = true) => (
    <>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{o.title}</span>
        <span className="block text-xs text-ink-soft">{hint}</span>
      </span>
      <span className="num text-sm whitespace-nowrap">{formatMoney(o.amount, o.currency)}</span>
      {action && (
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => onPay(o)} aria-label={`Отметить «${o.title}» оплаченным сегодня`}>
          Оплачено
        </button>
      )}
    </>
  )

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 border border-rule bg-sheet divide-y md:divide-y-0 md:divide-x divide-rule mb-6">
      <Column title="Просрочено" tone="red" items={overdue.data?.items} total={overdue.data?.total} empty="Просрочек нет"
        render={(o) => line(o, <span className="overdue-ink">! {days(o.overdue_days)} · срок {formatDate(o.due_date)}</span>)} />
      <Column title="Ближайшие 7 дней" items={soon.data?.items} total={soon.data?.total} empty="В ближайшую неделю платежей нет"
        render={(o) => line(o, <span className={o.days_until_due <= 3 ? 'text-amber font-semibold' : ''}>{o.days_until_due <= 3 ? '◆ ' : ''}{dueHint(o.days_until_due)} · {formatDate(o.due_date)}</span>)} />
      <Column title="Оплачено недавно" items={paid.data?.items} total={paid.data?.total} empty="Оплат ещё не было"
        render={(o) => line(o, <>{formatDate(o.paid_date)}{o.is_overdue ? <span className="text-red"> · с опозданием</span> : ''}</>, false)} />
    </div>
  )
}
