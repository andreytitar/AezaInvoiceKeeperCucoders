import type { Summary } from '../api/client'
import { CURRENCY_NAMES, formatMoney } from '../i18n/format'

/** Итоги отдельными карточками по каждой валюте — без суммирования между валютами. */
export function SummaryCards({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-0 border border-rule bg-sheet mb-6">
      {summary.currencies.map((c, i) => (
        <section
          key={c.currency}
          className={`p-4 ${i > 0 ? 'border-t md:border-t-0 md:border-l border-rule' : ''}`}
          aria-label={`Итоги, ${CURRENCY_NAMES[c.currency]}`}
        >
          <div className="flex items-baseline justify-between">
            <h2 className="num text-xs uppercase tracking-[0.18em] text-ink-soft">{c.currency}</h2>
            <span className="text-xs text-ink-soft">{CURRENCY_NAMES[c.currency]}</span>
          </div>
          <p className="font-serif text-2xl font-bold mt-1 num" title="К оплате (не оплачено)">
            {formatMoney(c.unpaid.amount, c.currency)}
          </p>
          <p className="text-xs text-ink-soft">к оплате · {c.unpaid.count} пер.</p>
          <dl className="mt-3 text-sm grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5">
            <dt className="text-ink-soft">Предстоит</dt>
            <dd className="num text-right">
              {formatMoney(c.upcoming.amount, c.currency)} <span className="text-ink-soft">/{c.upcoming.count}</span>
            </dd>
            <dt className={c.overdue.count ? 'text-red' : 'text-ink-soft'}>Просрочено</dt>
            <dd className={`num text-right ${c.overdue.count ? 'text-red font-semibold' : ''}`}>
              {formatMoney(c.overdue.amount, c.currency)} <span className="text-ink-soft">/{c.overdue.count}</span>
            </dd>
            <dt className="text-ink-soft">Оплачено</dt>
            <dd className="num text-right">
              {formatMoney(c.paid.amount, c.currency)} <span className="text-ink-soft">/{c.paid.count}</span>
            </dd>
            <dt className="text-ink-soft border-t-[3px] border-double border-rule pt-0.5">Всего</dt>
            <dd className="num text-right border-t-[3px] border-double border-rule pt-0.5">
              {formatMoney(c.total.amount, c.currency)} <span className="text-ink-soft">/{c.total.count}</span>
            </dd>
          </dl>
        </section>
      ))}
    </div>
  )
}
