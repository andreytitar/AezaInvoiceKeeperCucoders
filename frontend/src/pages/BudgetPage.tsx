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

function Bar({ value, max, over }: { value: number; max: number; over: boolean }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="h-2.5 border border-ink rounded-sm overflow-hidden bg-sheet" aria-hidden>
      <div className={`h-full ${over ? 'bg-red' : 'bg-ink'}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function LineCard({ l }: { l: Line }) {
  const budget = l.budget ? Number(l.budget) : 0
  return (
    <section className="p-4" aria-label={`Бюджет, ${CURRENCY_NAMES[l.currency]}`}>
      <div className="flex justify-between items-baseline">
        <h3 className="num text-xs uppercase tracking-[0.18em] text-ink-soft">{l.currency}</h3>
        {l.is_over && <span className="text-xs font-semibold text-red">! превышение</span>}
      </div>
      {l.budget === null ? (
        <p className="font-serif text-lg mt-1 text-ink-soft">Бюджет не задан</p>
      ) : (
        <p className="font-serif text-2xl font-bold mt-1 num">{formatMoney(l.budget, l.currency)}</p>
      )}
      <div className="mt-3 space-y-2">
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span>Запланировано ({l.count} пер.)</span>
            <span className="num">{formatMoney(l.scheduled, l.currency)}{l.usage_percent !== null && <span className="text-ink-soft"> · {l.usage_percent}%</span>}</span>
          </div>
          {l.budget !== null && <Bar value={Number(l.scheduled)} max={budget} over={l.is_over} />}
        </div>
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span>Оплачено</span>
            <span className="num">{formatMoney(l.paid, l.currency)}</span>
          </div>
          {l.budget !== null && <Bar value={Number(l.paid)} max={budget} over={false} />}
        </div>
      </div>
      <dl className="mt-3 text-sm grid grid-cols-[1fr_auto] gap-y-0.5 border-t-[3px] border-double border-rule pt-1">
        <dt className="text-ink-soft">Осталось оплатить</dt>
        <dd className="num text-right">{formatMoney(l.unpaid, l.currency)}</dd>
        {l.remaining !== null && (
          <>
            <dt className="text-ink-soft">Остаток бюджета</dt>
            <dd className="num text-right">{formatMoney(l.remaining, l.currency)}</dd>
          </>
        )}
        {l.is_over && (
          <>
            <dt className="text-red">Превышение</dt>
            <dd className="num text-right text-red font-semibold">{formatMoney(l.overrun, l.currency)}</dd>
          </>
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
    <>
      <PageTitle
        aside={
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex border border-ink rounded-sm" role="radiogroup" aria-label="Период">
              {(['month', 'year'] as const).map((t) => (
                <button key={t} role="radio" aria-checked={type === t} className={`px-3 py-1 text-sm ${type === t ? 'bg-ink text-paper' : ''}`} onClick={() => setType(t)}>
                  {t === 'month' ? 'Месяц' : 'Год'}
                </button>
              ))}
            </div>
            <button className="btn btn-sm" onClick={() => shift(-1)} aria-label="Назад">←</button>
            <span className="font-serif text-lg font-bold min-w-[9rem] text-center">{type === 'month' ? `${MONTHS[month - 1]} ${year}` : year}</span>
            <button className="btn btn-sm" onClick={() => shift(1)} aria-label="Вперёд">→</button>
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
          <div className={`grid grid-cols-1 md:grid-cols-3 border border-rule bg-sheet divide-y md:divide-y-0 md:divide-x divide-rule ${report.loading ? 'opacity-60' : ''}`}>
            {report.data.lines.map((l) => <LineCard key={l.currency} l={l} />)}
          </div>
          <p className="text-xs text-ink-soft mt-2">
            Запланировано — сумма периодов со сроком в этом {type === 'month' ? 'месяце' : 'году'}. Валюты не конвертируются.
          </p>
          {isAdmin && (
            <form onSubmit={save} className="sheet p-5 mt-6 max-w-2xl">
              <h2 className="font-serif text-lg font-bold mb-3">Плановые суммы</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
    </>
  )
}
