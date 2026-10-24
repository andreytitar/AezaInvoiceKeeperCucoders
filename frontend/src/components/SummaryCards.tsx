import type { Summary } from '../api/client'
import { CURRENCIES, formatMoney } from '../i18n/format'

function zero(amount: string) {
  const n = Number(amount)
  return !Number.isFinite(n) || n === 0
}

function Fig({ amount, currency, hot = false }: { amount: string; currency: string; hot?: boolean }) {
  if (zero(amount)) return <span className="balance-empty">—</span>
  return <span className={hot ? 'num text-overdue' : 'num'}>{formatMoney(amount, currency)}</span>
}

/** Три карточки валют. Крупная цифра — «к оплате». */
export function SummaryCards({ summary }: { summary: Summary }) {
  const lines = [...summary.currencies].sort(
    (a, b) =>
      CURRENCIES.indexOf(a.currency as (typeof CURRENCIES)[number]) -
      CURRENCIES.indexOf(b.currency as (typeof CURRENCIES)[number]),
  )
  return (
    <section className="summary-cards mb-5 grid grid-cols-1 gap-3 desk:grid-cols-3 desk:gap-4" aria-label="Итоги по валютам">
      {lines.map((c) => (
        <section key={c.currency} className="summary-card sheet min-w-0 p-3 desk:p-4 text-ink" aria-label={c.currency}>
          <p className="balance-kicker">{c.currency}</p>
          <p className="summary-card__due-label mt-2 desk:mt-3 text-xs font-sans font-medium text-ink-soft">
            К оплате
          </p>
          <p className={`balance-num break-all ${zero(c.unpaid.amount) ? 'balance-empty' : ''}`}>
            {zero(c.unpaid.amount) ? '—' : formatMoney(c.unpaid.amount, c.currency)}
          </p>
          <dl className="mt-3 text-sm">
            <div className="flex justify-between gap-3 py-0.5 min-w-0">
              <dt className="text-ink-soft shrink-0">Предстоит</dt>
              <dd className="min-w-0 text-right break-all">
                <Fig amount={c.upcoming.amount} currency={c.currency} />
                <span className="num text-ink-soft"> · {c.upcoming.count}</span>
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-0.5 min-w-0">
              <dt className="text-ink-soft shrink-0">Просрочено</dt>
              <dd className="min-w-0 text-right break-all">
                <Fig amount={c.overdue.amount} currency={c.currency} hot />
                <span className="num text-ink-soft"> · {c.overdue.count}</span>
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-0.5 min-w-0">
              <dt className="text-ink-soft shrink-0">Оплачено</dt>
              <dd className="min-w-0 text-right break-all">
                <Fig amount={c.paid.amount} currency={c.currency} />
                <span className="num text-ink-soft"> · {c.paid.count}</span>
              </dd>
            </div>
          </dl>
        </section>
      ))}
    </section>
  )
}
