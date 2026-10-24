import { useEffect, useState, type FormEvent } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { CURRENCIES, CURRENCY_NAMES, formatMoney, parseISODate } from '../i18n/format'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'

type Line = Schemas['BudgetLineOut']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

function zero(amount: string) {
  const n = Number(amount)
  return !Number.isFinite(n) || n === 0
}

function Fig({ amount, currency }: { amount: string; currency: string }) {
  if (zero(amount)) return <span className="balance-empty">—</span>
  return <span className="num">{formatMoney(amount, currency)}</span>
}

function LineCol({ l }: { l: Line }) {
  return (
    <section className="sheet min-w-0 p-4" aria-label={`Бюджет, ${CURRENCY_NAMES[l.currency]}`}>
      <p className="balance-kicker">{l.currency}</p>
      <p className="mt-3 text-xs font-sans font-semibold uppercase tracking-[0.14em] text-ink-soft">к оплате</p>
      <p className={`balance-num break-all ${zero(l.unpaid) ? 'balance-empty' : ''}`}>{zero(l.unpaid) ? '—' : formatMoney(l.unpaid, l.currency)}</p>
      <dl className="mt-3 text-sm">
        <div className="flex justify-between gap-3 py-0.5">
          <dt className="text-ink-soft">Бюджет</dt>
          <dd>{l.budget === null ? <span className="balance-empty">—</span> : <Fig amount={l.budget} currency={l.currency} />}</dd>
        </div>
        <div className="sum-line mt-1 flex justify-between gap-3 py-0.5">
          <dt className="text-ink-soft">Запланировано</dt>
          <dd>
            <Fig amount={l.scheduled} currency={l.currency} /> <span className="num text-ink-soft">{l.count}</span>
            {l.usage_percent !== null && <span className="num text-ink-soft"> · {l.usage_percent}%</span>}
          </dd>
        </div>
        <div className="flex justify-between gap-3 py-0.5">
          <dt className="text-ink-soft">Оплачено</dt>
          <dd><Fig amount={l.paid} currency={l.currency} /></dd>
        </div>
        {l.remaining !== null && (
          <div className="flex justify-between gap-3 py-0.5">
            <dt className="text-ink-soft">Остаток бюджета</dt>
            <dd><Fig amount={l.remaining} currency={l.currency} /></dd>
          </div>
        )}
        {l.is_over && (
          <div className="flex justify-between gap-3 py-0.5">
            <dt className="font-semibold">Превышение</dt>
            <dd className="num font-semibold">{formatMoney(l.overrun, l.currency)}</dd>
          </div>
        )}
      </dl>
    </section>
  )
}

export function BudgetPage() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const { today } = useServerToday()
  const [type, setType] = useState<'month' | 'year'>('month')
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState(new Date().getMonth() + 1)
  useEffect(() => {
    const t = parseISODate(today)
    setYear(t.getFullYear())
    setMonth(t.getMonth() + 1)
  }, [today])

  const report = useLoad(
    async () =>
      unwrap(
        await api.GET('/api/v1/budgets/report', {
          params: { query: { period_type: type, year, ...(type === 'month' ? { month } : {}) } },
        }),
      ),
    [type, year, month],
  )
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  useEffect(() => {
    if (report.data) setAmounts(Object.fromEntries(report.data.lines.map((l) => [l.currency, l.budget ?? ''])))
  }, [report.data])
  const [busy, setBusy] = useState(false)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      for (const cur of CURRENCIES) {
        const raw = (amounts[cur] ?? '').replace(',', '.').replace(/\s/g, '')
        const current = report.data?.lines.find((l) => l.currency === cur)?.budget ?? ''
        if (!raw || raw === current) continue
        unwrap(
          await api.PUT('/api/v1/budgets', {
            body: { period_type: type, year, month: type === 'month' ? month : null, currency: cur, planned_amount: raw },
          }),
        )
      }
      toast('ok', 'Бюджет сохранён')
      report.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const shift = (n: number) => {
    if (type === 'year') return setYear(year + n)
    const d = new Date(year, month - 1 + n, 1)
    setYear(d.getFullYear())
    setMonth(d.getMonth() + 1)
  }

  return (
    <div className="win-window min-w-0 max-w-full">
      <div className="win-titlebar">Бюджет</div>
      <div className="min-w-0 bg-paper-2 px-2 pt-2 pb-3 text-ink">
      <PageTitle
        hideTitleOnDesk
        aside={
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex shrink-0 gap-2" role="radiogroup" aria-label="Период">
              {(['month', 'year'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  aria-checked={type === t}
                  className={`btn h-11 min-h-11 w-28 shrink-0 rounded-sm px-3 leading-none ${type === t ? 'btn-primary' : ''}`}
                  onClick={() => setType(t)}
                >
                  {t === 'month' ? 'Месяц' : 'Год'}
                </button>
              ))}
            </div>
            <div className="inline-flex items-center gap-2">
              <button type="button" className="btn h-11 min-h-11 w-11 shrink-0 px-0 text-2xl leading-none" onClick={() => shift(-1)} aria-label="Назад">
                ‹
              </button>
              <span className="min-w-[7.5rem] whitespace-nowrap text-center font-sans text-lg font-semibold">{type === 'month' ? `${MONTHS[month - 1]} ${year}` : year}</span>
              <button type="button" className="btn h-11 min-h-11 w-11 shrink-0 px-0 text-2xl leading-none" onClick={() => shift(1)} aria-label="Вперёд">
                ›
              </button>
            </div>
          </div>
        }
      >
        Бюджет
      </PageTitle>
      {report.error ? (
        <ErrorNote text={report.error} onRetry={report.reload} />
      ) : !report.data ? (
        <Loading />
      ) : (
        <>
          <div className={`grid grid-cols-1 gap-3 desk:grid-cols-3 ${report.loading ? 'opacity-60' : ''}`}>
            {report.data.lines.map((l) => <LineCol key={l.currency} l={l} />)}
          </div>
          <p className="text-xs text-ink-soft mt-2">
            Запланировано — сумма периодов со сроком в этом {type === 'month' ? 'месяце' : 'году'}. Валюты не конвертируются.
          </p>
          {isAdmin && (
            <form onSubmit={save} className="sheet p-4 mt-6 min-w-0">
              <h2 className="font-sans text-lg font-semibold mb-3">Плановые суммы</h2>
              <div className="grid grid-cols-1 desk:grid-cols-3 gap-3">
                {CURRENCIES.map((c) => (
                  <div key={c}>
                    <label className="label" htmlFor={`b-${c}`}>{c}</label>
                    <input id={`b-${c}`} className="field num" inputMode="decimal" placeholder="не задан" value={amounts[c] ?? ''} onChange={(e) => setAmounts({ ...amounts, [c]: e.target.value })} />
                  </div>
                ))}
              </div>
              <button className="btn btn-primary mt-4" disabled={busy}>Сохранить</button>
            </form>
          )}
        </>
      )}
      </div>
    </div>
  )
}
