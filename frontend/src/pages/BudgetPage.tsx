import { useEffect, useState, type FormEvent } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { Badge, Button, Card, ErrorNote, Input, Loading, PageTitle, Tabs } from '../components/ui'
import { Icon } from '../components/Icon'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { CURRENCIES, CURRENCY_NAMES, formatMoney, parseISODate } from '../i18n/format'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'

type Line = Schemas['BudgetLineOut']
const MONTHS = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

function zero(amount: string) {
  const n = Number(amount)
  return !Number.isFinite(n) || n === 0
}

function Fig({ amount, currency }: { amount: string; currency: string }) {
  if (zero(amount)) return <span className="text-ink-soft">—</span>
  return <span className="num whitespace-nowrap">{formatMoney(amount, currency)}</span>
}

function LineCol({ l }: { l: Line }) {
  return (
    <Card className="min-w-0 p-5" aria-label={`Бюджет, ${CURRENCY_NAMES[l.currency]}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="num font-medium">{l.currency}</p>
        {l.is_over && <Badge tone="overdue">Превышен</Badge>}
      </div>
      <p className="mt-5 text-sm text-ink-soft">К оплате</p>
      <p
        className={`mt-1 whitespace-nowrap font-display text-[clamp(1.5rem,2.2vw,2rem)] font-semibold tracking-tight ${zero(l.unpaid) ? 'text-ink-soft' : ''}`}
      >
        {zero(l.unpaid) ? '—' : formatMoney(l.unpaid, l.currency)}
      </p>
      <dl className="mt-5 space-y-3 text-sm">
        <div className="flex flex-wrap justify-between gap-x-3 gap-y-1">
          <dt className="text-ink-soft">Бюджет</dt>
          <dd className="whitespace-nowrap">
            {l.budget === null ? (
              <span className="text-ink-soft">—</span>
            ) : (
              <Fig amount={l.budget} currency={l.currency} />
            )}
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 border-t border-rule pt-3">
          <dt className="text-ink-soft">Запланировано</dt>
          <dd className="whitespace-nowrap">
            <Fig amount={l.scheduled} currency={l.currency} />
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-x-3 gap-y-1">
          <dt className="text-ink-soft">Оплачено</dt>
          <dd className="whitespace-nowrap text-paid">
            <Fig amount={l.paid} currency={l.currency} />
          </dd>
        </div>
        {l.remaining !== null && (
          <div className="flex flex-wrap justify-between gap-x-3 gap-y-1">
            <dt className="text-ink-soft">Остаток бюджета</dt>
            <dd className="whitespace-nowrap">
              <Fig amount={l.remaining} currency={l.currency} />
            </dd>
          </div>
        )}
        {l.is_over && (
          <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-overdue">
            <dt>Превышение</dt>
            <dd className="num whitespace-nowrap font-medium">{formatMoney(l.overrun, l.currency)}</dd>
          </div>
        )}
      </dl>
      <p className="mt-5 border-t border-rule pt-3 text-xs text-ink-soft">
        <span className="num">{l.count}</span> платежей
        {l.usage_percent !== null && (
          <>
            {' '}
            · <span className="num">{l.usage_percent}%</span> бюджета запланировано
          </>
        )}
      </p>
    </Card>
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
            body: {
              period_type: type,
              year,
              month: type === 'month' ? month : null,
              currency: cur,
              planned_amount: raw,
            },
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
      <PageTitle>Бюджет</PageTitle>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          items={[
            { value: 'month', label: 'Месяц' },
            { value: 'year', label: 'Год' },
          ]}
          value={type}
          onChange={(value) => setType(value as 'month' | 'year')}
        />
        <div className="flex min-w-0 items-center gap-1">
          <Button variant="ghost" onClick={() => shift(-1)} aria-label="Предыдущий период">
            <Icon name="chevron-left" />
          </Button>
          <span className="min-w-[8.5rem] whitespace-nowrap text-center text-sm font-semibold min-[390px]:text-base">
            {type === 'month' ? `${MONTHS[month - 1]} ${year}` : year}
          </span>
          <Button variant="ghost" onClick={() => shift(1)} aria-label="Следующий период">
            <Icon name="chevron-right" />
          </Button>
        </div>
      </div>
      {report.error ? (
        <ErrorNote text={report.error} onRetry={report.reload} />
      ) : !report.data ? (
        <Loading />
      ) : (
        <>
          <div
            className={`grid grid-cols-1 items-start gap-4 min-[650px]:grid-cols-2 min-[1280px]:grid-cols-3 ${report.loading ? 'opacity-60' : ''}`}
          >
            {report.data.lines.map((l) => (
              <LineCol key={l.currency} l={l} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-ink-soft">
            Запланировано — сумма периодов со сроком в этом {type === 'month' ? 'месяце' : 'году'}. Валюты считаются
            отдельно.
          </p>
          {isAdmin && (
            <Card className="mt-8 p-5">
              <form onSubmit={save}>
                <h2 className="font-display text-xl font-semibold">Плановые суммы</h2>
                <p className="mt-1 mb-5 text-sm text-ink-soft">
                  Задайте бюджет для выбранного {type === 'month' ? 'месяца' : 'года'} по каждой валюте.
                </p>
                <div className="grid grid-cols-1 gap-4 min-[650px]:grid-cols-3">
                  {CURRENCIES.map((c) => (
                    <div key={c}>
                      <label className="label" htmlFor={`b-${c}`}>
                        {c}
                      </label>
                      <Input
                        id={`b-${c}`}
                        className="num"
                        inputMode="decimal"
                        placeholder="Не задан"
                        value={amounts[c] ?? ''}
                        onChange={(e) => setAmounts({ ...amounts, [c]: e.target.value })}
                      />
                    </div>
                  ))}
                </div>
                <Button type="submit" variant="primary" className="mt-5" loading={busy}>
                  Сохранить бюджет
                </Button>
              </form>
            </Card>
          )}
        </>
      )}
    </>
  )
}
