import { api, unwrap, type Occurrence } from '../api/client'
import { useLoad } from '../hooks/useLoad'
import { formatDate, formatMoney, parseISODate, toISODate } from '../i18n/format'
import { Icon } from './Icon'
import { StatusCell, amountHot } from './Status'
import { Badge, Button, Card, EmptyState, ErrorNote, Skeleton } from './ui'

type Props = { today: string; version: number; onPay: (o: Occurrence) => void; busy: boolean }

function addDays(iso: string, n: number) {
  const d = parseISODate(iso)
  d.setDate(d.getDate() + n)
  return toISODate(d)
}

function useTop5(query: Record<string, unknown>, deps: unknown[]) {
  return useLoad(
    async () => unwrap(await api.GET('/api/v1/payment-occurrences', { params: { query: { page_size: 5, ...query } as never } })),
    deps,
  )
}

function Section({
  title, data, error, onRetry, empty, pay, busy, onPay, tone,
}: {
  title: string
  data: { items: Occurrence[]; total: number } | null
  error: string | null
  onRetry: () => void
  empty: string
  pay: boolean
  busy: boolean
  onPay: (o: Occurrence) => void
  tone: 'neutral' | 'accent' | 'overdue'
}) {
  return (
    <Card className="upcoming-section min-w-0 overflow-hidden" aria-label={title}>
      <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {data && <Badge tone={data.total ? tone : 'neutral'}>{data.total}</Badge>}
      </div>
      {error ? (
        <div className="px-4 pb-4"><ErrorNote text={error} onRetry={onRetry} /></div>
      ) : !data ? (
        <div className="space-y-2 px-5 pb-5"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
      ) : data.items.length === 0 ? (
        <div className="px-4 pb-4"><EmptyState title={empty} icon={<Icon name={tone === 'overdue' ? 'check' : 'calendar'} />} /></div>
      ) : (
        <ul className="divide-y divide-rule">
          {data.items.map((o) => (
            <li key={o.id} className="flex min-w-0 items-start justify-between gap-3 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="min-w-0 text-sm font-medium">{o.title}</span>
                  <span className={`num shrink-0 text-sm whitespace-nowrap ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <StatusCell o={o} />
                  <span className="num text-xs text-ink-soft whitespace-nowrap">{formatDate(o.due_date)}</span>
                </div>
              </div>
              {pay && (
                <Button size="sm" variant="secondary" className="shrink-0" disabled={busy} onClick={() => onPay(o)} aria-label={`Отметить «${o.title}» оплаченным сегодня`} title="Отметить оплату сегодняшней датой">
                  <Icon name="check" />
                </Button>
              )}
            </li>
          ))}
          {data.total > data.items.length && (
            <li className="px-5 py-2.5 text-xs text-ink-soft">Показаны первые {data.items.length} из {data.total}. Полный список — ниже.</li>
          )}
        </ul>
      )}
    </Card>
  )
}

/** Короткая сводка срочных платежей. История последних оплат раскрывается отдельно. */
export function Upcoming({ today, version, onPay, busy }: Props) {
  const overdue = useTop5({ status: 'unpaid', overdue: true, sort: 'due_date' }, [today, version])
  const soon = useTop5({ status: 'unpaid', overdue: false, to: addDays(today, 7), sort: 'due_date' }, [today, version])
  const paid = useTop5({ status: 'paid', sort: '-paid_date' }, [today, version])

  return (
    <div className="upcoming-block mb-6 space-y-3">
      <div className="upcoming-grid grid min-w-0 gap-4 lg:grid-cols-2">
        <Section title="Просрочено" data={overdue.data} error={overdue.error} onRetry={overdue.reload} empty="Просрочек нет" pay busy={busy} onPay={onPay} tone="overdue" />
        <Section title="Ближайшие 7 дней" data={soon.data} error={soon.error} onRetry={soon.reload} empty="На этой неделе платежей нет" pay busy={busy} onPay={onPay} tone="accent" />
      </div>
      <details className="upcoming-recent">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg px-2 text-sm text-ink-soft [&::-webkit-details-marker]:hidden">
          <span>Оплачено недавно{paid.data ? ` · ${paid.data.total}` : ''}</span>
          <Icon name="chevron-right" />
        </summary>
        <div className="mt-2">
          <Section title="Последние оплаты" data={paid.data} error={paid.error} onRetry={paid.reload} empty="Оплат ещё не было" pay={false} busy={busy} onPay={onPay} tone="neutral" />
        </div>
      </details>
    </div>
  )
}
