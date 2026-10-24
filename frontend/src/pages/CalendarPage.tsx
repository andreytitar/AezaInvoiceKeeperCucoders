import { useEffect, useMemo, useState } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { OverdueCell, StatusCell } from '../components/Status'
import { SummaryCards } from '../components/SummaryCards'
import { ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { formatDate, formatMoney, formatMonth, parseISODate, toISODate } from '../i18n/format'
import { useToast } from '../store/toast'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function badgeCls(o: Occurrence) {
  if (o.status === 'paid') return 'border-green text-green'
  if (o.is_overdue) return 'border-red text-red font-semibold'
  if (o.days_until_due <= 3) return 'border-amber text-amber'
  return 'border-rule text-ink'
}
function badgeMark(o: Occurrence) {
  if (o.status === 'paid') return '✓'
  if (o.is_overdue) return '!'
  return '○'
}

export function CalendarPage() {
  const toast = useToast()
  const { today } = useServerToday()
  const [month, setMonth] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [selected, setSelected] = useState<Occurrence | null>(null)
  const [paying, setPaying] = useState<Occurrence | null>(null)
  const [busy, setBusy] = useState(false)
  const [asOf, setAsOf] = useState('')
  const [feed, setFeed] = useState<{ url: string; webcal_url: string } | null>(null)
  const openFeed = async (rotate = false) => {
    try {
      setFeed(unwrap(rotate ? await api.POST('/api/v1/calendar/feed/rotate') : await api.GET('/api/v1/calendar/feed')))
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    }
  }
  // «сегодня» сервера (APP_FAKE_TODAY) определяет стартовый месяц
  useEffect(() => {
    const t = parseISODate(today)
    setMonth(new Date(t.getFullYear(), t.getMonth(), 1))
  }, [today])

  const range = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1)
    const last = new Date(month.getFullYear(), month.getMonth() + 1, 0)
    return { from: toISODate(first), to: toISODate(last), first, last }
  }, [month])

  const cal = useLoad(
    async () => unwrap(await api.GET('/api/v1/payments/calendar', { params: { query: { from: range.from, to: range.to } } })),
    [range.from, range.to],
  )
  const summary = useLoad(
    async () => unwrap(await api.GET('/api/v1/payments/summary', { params: { query: asOf ? { as_of: asOf } : {} } })),
    [asOf],
  )

  const byDay = useMemo(() => new Map((cal.data?.days ?? []).map((d) => [d.date, d])), [cal.data])
  const cells = useMemo(() => {
    const lead = (range.first.getDay() + 6) % 7
    const out: (string | null)[] = Array(lead).fill(null)
    for (let d = 1; d <= range.last.getDate(); d++) out.push(toISODate(new Date(month.getFullYear(), month.getMonth(), d)))
    while (out.length % 7) out.push(null)
    return out
  }, [range, month])

  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1))
  const reload = () => {
    cal.reload()
    summary.reload()
  }

  const patch = async (o: Occurrence, body: { status: 'paid' | 'unpaid'; paid_date?: string }) => {
    setBusy(true)
    try {
      const updated = unwrap(
        await api.PATCH('/api/v1/payment-occurrences/{occurrence_id}', { params: { path: { occurrence_id: o.id } }, body }),
      )
      toast('ok', body.status === 'paid' ? `«${o.title}» — оплата отмечена` : `«${o.title}» — оплата отменена`)
      setSelected(updated)
      setPaying(null)
      reload()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageTitle
        aside={
          <div className="flex items-center gap-2">
            <button className="btn btn-sm" onClick={() => shift(-1)} aria-label="Предыдущий месяц">←</button>
            <span className="font-serif text-lg font-bold min-w-[10rem] text-center" aria-live="polite">{formatMonth(month)}</span>
            <button className="btn btn-sm" onClick={() => shift(1)} aria-label="Следующий месяц">→</button>
            <button className="btn btn-sm btn-ghost" onClick={() => setMonth(new Date(parseISODate(today).getFullYear(), parseISODate(today).getMonth(), 1))}>
              Сегодня
            </button>
            <button className="btn btn-sm" onClick={() => openFeed()}>
              В календарь телефона
            </button>
          </div>
        }
      >
        Календарь
      </PageTitle>

      <div className="flex flex-wrap gap-4 text-xs text-ink-soft mb-3" aria-label="Легенда">
        <span><span className="text-green">✓</span> оплачено</span>
        <span><span className="text-red">!</span> просрочено</span>
        <span><span className="text-amber">○</span> срок в ближайшие 3 дня</span>
        <span>○ предстоит</span>
      </div>

      {cal.error ? (
        <ErrorNote text={cal.error} onRetry={cal.reload} />
      ) : (
        <div className={`sheet ${cal.loading ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-7 border-b-[1.5px] border-ink">
            {WEEKDAYS.map((w) => (
              <div key={w} className="px-2 py-1.5 text-[0.7rem] uppercase tracking-widest text-ink-soft">{w}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {cells.map((iso, i) => {
              const day = iso ? byDay.get(iso) : undefined
              const isToday = iso === today
              return (
                <div
                  key={i}
                  className={`min-h-[5.5rem] sm:min-h-[7rem] border-b border-r border-rule p-1 sm:p-1.5 ${i % 7 === 6 ? 'border-r-0' : ''} ${iso ? '' : 'bg-paper/60'}`}
                >
                  {iso && (
                    <>
                      <div className="flex justify-between items-baseline">
                        <span className={`num text-xs ${isToday ? 'bg-ink text-paper px-1 rounded-sm' : 'text-ink-soft'}`}>
                          {parseISODate(iso).getDate()}
                        </span>
                      </div>
                      <ul className="mt-1 space-y-0.5">
                        {day?.occurrences.map((o) => (
                          <li key={o.id}>
                            <button
                              onClick={() => setSelected(o)}
                              className={`w-full text-left border rounded-sm px-1 py-0.5 text-[0.7rem] leading-tight truncate hover:bg-ink/5 ${badgeCls(o)}`}
                              title={`${o.title} — ${formatMoney(o.amount, o.currency)}`}
                            >
                              <span aria-hidden>{badgeMark(o)} </span>
                              <span className="hidden sm:inline">{o.title}</span>
                              <span className="sm:hidden">{o.currency}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                      {day && (
                        <div className="hidden sm:block mt-1 text-[0.65rem] num text-ink-soft leading-tight">
                          {day.totals.map((t) => (
                            <div key={t.currency}>{formatMoney(t.total.amount, t.currency)}</div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {feed && (
        <section className="sheet p-4 mt-4 fade-in" aria-label="Подписка на календарь">
          <div className="flex justify-between items-start gap-3">
            <div className="min-w-0">
              <h2 className="font-serif text-lg font-bold">Календарь в телефоне</h2>
              <p className="text-sm text-ink-soft mt-1">
                Все сроки появятся в Google или Apple Календаре с напоминанием за 3 дня и в день оплаты; обновляется
                автоматически. Ссылка личная — не пересылайте её.
              </p>
            </div>
            <button className="btn btn-sm btn-ghost" onClick={() => setFeed(null)} aria-label="Закрыть">✕</button>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <a className="btn btn-sm btn-primary" href={feed.webcal_url}>Открыть в Календаре (iPhone, Mac)</a>
            <a className="btn btn-sm" href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(feed.webcal_url)}`} target="_blank" rel="noopener">
              Google Календарь
            </a>
            <button className="btn btn-sm" onClick={() => navigator.clipboard?.writeText(feed.url).then(() => toast('ok', 'Ссылка скопирована'))}>
              Скопировать ссылку
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => openFeed(true)}>Сменить ссылку</button>
          </div>
          <code className="num text-xs break-all block mt-2 text-ink-soft">{feed.url}</code>
        </section>
      )}

      <section className="mt-8" aria-labelledby="asof-title">
        <div className="flex flex-wrap items-end gap-3 mb-3">
          <h2 id="asof-title" className="font-serif text-xl font-bold">Итоги на дату</h2>
          <div>
            <label className="sr-only" htmlFor="as-of">Дата</label>
            <input id="as-of" type="date" className="field num w-auto" value={asOf || today} onChange={(e) => setAsOf(e.target.value)} />
          </div>
          {asOf && <button className="btn btn-sm btn-ghost" onClick={() => setAsOf('')}>На сегодня</button>}
        </div>
        {summary.error ? <ErrorNote text={summary.error} /> : summary.data ? <SummaryCards summary={summary.data} /> : <Loading />}
      </section>

      {selected && (
        <div className="fixed inset-0 z-40 bg-black/40 grid place-items-center p-4" onClick={() => setSelected(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="occ-title"
            className="sheet w-[min(92vw,26rem)] p-5 shadow-[4px_4px_0_var(--ink)] fade-in"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.key === 'Escape' && setSelected(null)}
          >
            <h2 id="occ-title" className="font-serif text-xl font-bold">{selected.title}</h2>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-ink-soft">Сумма</dt><dd className="num">{formatMoney(selected.amount, selected.currency)}</dd>
              <dt className="text-ink-soft">Срок</dt><dd className="num">{formatDate(selected.due_date)}</dd>
              <dt className="text-ink-soft">Статус</dt><dd><StatusCell o={selected} /></dd>
              <dt className="text-ink-soft">Дата оплаты</dt><dd className="num">{formatDate(selected.paid_date)}</dd>
              <dt className="text-ink-soft">Просрочка</dt><dd><OverdueCell o={selected} /></dd>
            </dl>
            {selected.recurring_payment_deleted && <p className="text-xs text-ink-soft mt-2">Регулярный платёж прекращён.</p>}
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button className="btn" onClick={() => setSelected(null)} autoFocus>Закрыть</button>
              {selected.status === 'unpaid' ? (
                <>
                  <button className="btn" onClick={() => setPaying(selected)} disabled={busy}>Дата…</button>
                  <button className="btn btn-primary" onClick={() => patch(selected, { status: 'paid', paid_date: today })} disabled={busy}>Оплачено сегодня</button>
                </>
              ) : (
                <>
                  <button className="btn" onClick={() => setPaying(selected)} disabled={busy}>Изменить дату</button>
                  <button className="btn btn-danger" onClick={() => patch(selected, { status: 'unpaid' })} disabled={busy}>Отменить оплату</button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
      <MarkPaidDialog occurrence={paying} today={today} busy={busy} onClose={() => setPaying(null)} onSubmit={(d) => paying && patch(paying, { status: 'paid', paid_date: d })} />
    </>
  )
}
