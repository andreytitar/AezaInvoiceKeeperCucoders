import type { ReactNode } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { useLoad } from '../hooks/useLoad'
import { days, dueHint, formatDate, formatMoney, parseISODate, toISODate } from '../i18n/format'
import { StatusCell, amountHot } from './Status'

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
  title,
  items,
  total,
  empty,
  hint,
  pay,
  busy,
  onPay,
  hideHeading,
}: {
  title: string
  items: Occurrence[] | undefined
  total: number | undefined
  empty: string
  hint: (o: Occurrence) => ReactNode
  pay: boolean
  busy: boolean
  onPay: (o: Occurrence) => void
  hideHeading?: boolean
}) {
  return (
    <section className="upcoming-section mb-4 last:mb-0" aria-label={title}>
      {hideHeading ? (
        <h2 className="sr-only">{title}</h2>
      ) : (
        <h2 className="upcoming-section__title mb-2 flex items-baseline justify-between gap-2 font-sans text-base font-semibold text-ink">
          {title}
          <span className="num text-xs font-normal text-ink-soft desk:text-sm">{total ?? '…'}</span>
        </h2>
      )}
      {!items ? (
        <p className="text-sm text-ink-soft num mt-2">…</p>
      ) : !items.length ? (
        <p className="text-sm text-ink-soft mt-2">{empty}</p>
      ) : (
        <>
          <ul className="hand-only">
            {items.map((o) => (
              <li key={o.id} className="slip">
                <div className="slip-row">
                  <span className="font-semibold min-w-0">{o.title}</span>
                  <span className={`num min-w-0 break-all text-right ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</span>
                </div>
                <div className="slip-row text-sm">
                  <span className="num">{formatDate(o.due_date)}</span>
                  <span className="text-ink-soft">{hint(o)}</span>
                </div>
                <div className="slip-row">
                  {!pay && <StatusCell o={o} />}
                  {pay && (
                    <>
                      <span className="desk-only">
                        <StatusCell o={o} />
                      </span>
                      <button
                        className="btn btn-primary w-full desk:w-auto"
                        disabled={busy}
                        onClick={() => onPay(o)}
                        aria-label={`Отметить «${o.title}» оплаченным сегодня`}
                      >
                        Оплачено
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <table className="ledger desk-only w-full">
            <thead>
              <tr>
                <th>Название</th>
                <th className="text-right">Сумма</th>
                <th>Дата</th>
                <th>Статус</th>
                {pay && (
                  <th className="text-right">
                    <span className="sr-only">Действия</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.id}>
                  <td className="font-semibold">{o.title}</td>
                  <td className={`num text-right whitespace-nowrap ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</td>
                  <td className="num text-sm">{formatDate(o.due_date)}</td>
                  <td>
                    <StatusCell o={o} />
                    <span className="block text-xs text-ink-soft mt-0.5">{hint(o)}</span>
                  </td>
                  {pay && (
                    <td className="text-right">
                      <button className="btn btn-primary whitespace-normal" disabled={busy} onClick={() => onPay(o)} aria-label={`Отметить «${o.title}» оплаченным сегодня`}>
                        Оплачено
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

/** Что просрочено, что оплатить в ближайшие 7 дней, что оплачено недавно. */
export function Upcoming({ today, version, onPay, busy }: Props) {
  const overdue = useTop5({ status: 'unpaid', overdue: true, sort: 'due_date' }, [today, version])
  const soon = useTop5({ status: 'unpaid', overdue: false, to: addDays(today, 7), sort: 'due_date' }, [today, version])
  const paid = useTop5({ status: 'paid', sort: '-paid_date' }, [today, version])

  return (
    <div className="mb-5 upcoming-block">
      <Section
        title="Просрочено"
        items={overdue.data?.items}
        total={overdue.data?.total}
        empty="Просрочек нет"
        pay
        busy={busy}
        onPay={onPay}
        hint={(o) => (
          <>
            <span className="hand-only">{days(o.overdue_days)}</span>
            <span className="desk-only">
              {days(o.overdue_days)}, срок {formatDate(o.due_date)}
            </span>
          </>
        )}
      />
      <Section
        title="Ближайшие 7 дней"
        items={soon.data?.items}
        total={soon.data?.total}
        empty="В ближайшую неделю платежей нет"
        pay
        busy={busy}
        onPay={onPay}
        hint={(o) => (
          <>
            <span className={`hand-only ${o.days_until_due <= 3 ? 'font-semibold text-ink' : ''}`}>{dueHint(o.days_until_due)}</span>
            <span className={`desk-only ${o.days_until_due <= 3 ? 'font-semibold text-ink' : ''}`}>
              {dueHint(o.days_until_due)}, {formatDate(o.due_date)}
            </span>
          </>
        )}
      />
      <details className="upcoming-recent mt-2 border-t border-rule pt-2 desk:mt-0 desk:border-0 desk:pt-0">
        <summary className="cursor-pointer list-none font-sans text-base font-semibold text-ink [&::-webkit-details-marker]:hidden">
          <span className="flex items-baseline justify-between gap-2">
            Оплачено недавно
            <span className="num text-sm font-normal text-ink-soft">{paid.data?.total ?? '…'}</span>
          </span>
        </summary>
        <div className="mt-2">
          <Section
            title="Оплачено недавно"
            hideHeading
            items={paid.data?.items}
            total={paid.data?.total}
            empty="Оплат ещё не было"
            pay={false}
            busy={busy}
            onPay={onPay}
            hint={(o) => (
              <>
                {formatDate(o.paid_date)}
                {o.is_overdue ? <span>, с опозданием</span> : null}
              </>
            )}
          />
        </div>
      </details>
    </div>
  )
}
