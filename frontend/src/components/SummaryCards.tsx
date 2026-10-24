import type { Summary } from '../api/client'
import { CURRENCIES, CURRENCY_NAMES, formatMoney } from '../i18n/format'
import { Card } from './ui'

function zero(amount: string) {
  const n = Number(amount)
  return !Number.isFinite(n) || n === 0
}

function Figure({ amount, currency, hot = false }: { amount: string; currency: string; hot?: boolean }) {
  return zero(amount) ? (
    <span className="text-ink-soft">—</span>
  ) : (
    <span className={`num whitespace-nowrap ${hot ? 'text-overdue' : ''}`}>{formatMoney(amount, currency)}</span>
  )
}

/** Валюты считаются отдельно. В боковой панели — вертикальный компактный список. */
export function SummaryCards({ summary, compact = false }: { summary: Summary; compact?: boolean }) {
  const lines = [...summary.currencies].sort((a, b) => CURRENCIES.indexOf(a.currency) - CURRENCIES.indexOf(b.currency))
  return (
    <section className={compact ? 'summary-compact space-y-4' : 'summary-cards mb-5 grid min-w-0 grid-cols-1 gap-4 md:grid-cols-3'} aria-label="Итоги по валютам">
      {lines.map((c) => {
        const details = (
          <dl className={`space-y-2 text-sm ${compact ? 'mt-3' : 'mt-5'}`}>
            {([
              ['Предстоит', c.upcoming, false],
              ['Просрочено', c.overdue, true],
              ['Оплачено', c.paid, false],
            ] as const).map(([label, value, hot]) => (
              <div key={label} className="flex min-w-0 items-baseline justify-between gap-2">
                <dt className="shrink-0 text-ink-soft">{label}</dt>
                <dd className="min-w-0 whitespace-nowrap text-right">
                  <Figure amount={value.amount} currency={c.currency} hot={hot} />
                  {value.count > 0 && <span className="ml-1.5 text-xs text-ink-soft">· {value.count}</span>}
                </dd>
              </div>
            ))}
          </dl>
        )
        return compact ? (
          <div key={c.currency} className="border-b border-rule pb-4 last:border-0 last:pb-0" aria-label={c.currency}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="num text-sm font-medium text-ink-soft">{c.currency}</span>
              <span className="font-display text-xl font-semibold whitespace-nowrap">
                <Figure amount={c.unpaid.amount} currency={c.currency} />
              </span>
            </div>
            {details}
          </div>
        ) : (
          <Card key={c.currency} className="summary-card min-w-0 p-5" aria-label={c.currency}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink-soft">{CURRENCY_NAMES[c.currency]}</span>
              <span className="num text-xs text-ink-soft">{c.currency}</span>
            </div>
            <p className="mt-4 text-xs text-ink-soft">К оплате</p>
            <p className={`balance-num mt-1 whitespace-nowrap font-display text-[28px] md:text-2xl xl:text-[32px] font-semibold tracking-tight ${zero(c.unpaid.amount) ? 'text-ink-soft' : ''}`}>
              {zero(c.unpaid.amount) ? '—' : formatMoney(c.unpaid.amount, c.currency)}
            </p>
            {details}
          </Card>
        )
      })}
    </section>
  )
}
