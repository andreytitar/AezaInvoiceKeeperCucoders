import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { CalendarDayDetailPanel } from '../components/CalendarDayDetailPanel'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { SummaryCards } from '../components/SummaryCards'
import { ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { formatDate, formatMoney, formatMonth, parseISODate, toISODate } from '../i18n/format'
import { useToast } from '../store/toast'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Подписка Google Calendar: https-адрес ICS в cid, не webcal и не /calendar/r. */
function googleSubscribeHref(icsUrl: string): string {
  return `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(icsUrl)}`
}

function addIsoDays(iso: string, delta: number): string {
  const d = parseISODate(iso)
  d.setDate(d.getDate() + delta)
  return toISODate(d)
}

type DayTone = 'overdue' | 'pay' | 'd1' | 'd2' | 'd3'

const TONE_CLASS: Record<DayTone, string> = {
  overdue: 'cal-overdue',
  pay: 'cal-pay',
  d1: 'cal-d1',
  d2: 'cal-d2',
  d3: 'cal-d3',
}

/** К предстоящему платежу: день срока самый тёмный, три дня до него светлее. Просрочка не затирается. */
function approachTones(days: { date: string; occurrences: Occurrence[] }[], today: string): Map<string, DayTone> {
  const tones = new Map<string, DayTone>()
  const upcoming: string[] = []
  for (const day of days) {
    if (day.occurrences.some((o) => o.is_overdue)) tones.set(day.date, 'overdue')
    if (day.occurrences.some((o) => o.status === 'unpaid' && !o.is_overdue && o.due_date >= today)) upcoming.push(day.date)
  }
  const step: DayTone[] = ['pay', 'd1', 'd2', 'd3']
  const rank: Record<DayTone, number> = { d3: 1, d2: 2, d1: 3, pay: 4, overdue: 5 }
  for (const due of upcoming) {
    for (let i = 0; i < step.length; i++) {
      const iso = addIsoDays(due, -i)
      if (tones.get(iso) === 'overdue') continue
      const next = step[i]
      const prev = tones.get(iso)
      if (!prev || rank[next] > rank[prev]) tones.set(iso, next)
    }
  }
  return tones
}

function pickOccurrence(day: { occurrences: Occurrence[] } | undefined, current: Occurrence | null): Occurrence | null {
  if (!day?.occurrences.length) return null
  if (current && day.occurrences.some((o) => o.id === current.id)) return current
  return day.occurrences[0]
}

export function CalendarPage() {
  const toast = useToast()
  const { today } = useServerToday()
  const [month, setMonth] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
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
    const horizon = new Date(last.getFullYear(), last.getMonth(), last.getDate() + 3)
    return { from: toISODate(first), to: toISODate(horizon), first, last }
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
  const tones = useMemo(() => approachTones(cal.data?.days ?? [], today), [cal.data, today])
  const cells = useMemo(() => {
    const lead = (range.first.getDay() + 6) % 7
    const out: (string | null)[] = Array(lead).fill(null)
    for (let d = 1; d <= range.last.getDate(); d++) out.push(toISODate(new Date(month.getFullYear(), month.getMonth(), d)))
    while (out.length % 7) out.push(null)
    return out
  }, [range, month])

  const selectedDayData = selectedDay ? byDay.get(selectedDay) : undefined
  const activeOccurrence = useMemo(
    () => pickOccurrence(selectedDayData, selected),
    [selectedDayData, selected],
  )

  useEffect(() => {
    if (!selected) return
    for (const d of cal.data?.days ?? []) {
      const found = d.occurrences.find((o) => o.id === selected.id)
      if (found) {
        setSelected(found)
        return
      }
    }
  }, [cal.data, selected?.id])

  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1))
  const reload = () => {
    cal.reload()
    summary.reload()
  }

  const selectDay = (iso: string, occurrence?: Occurrence) => {
    setSelectedDay(iso)
    const day = byDay.get(iso)
    setSelected(occurrence ?? pickOccurrence(day, null))
  }

  const patch = async (o: Occurrence, body: { status: 'paid' | 'unpaid'; paid_date?: string }) => {
    setBusy(true)
    try {
      const updated = unwrap(
        await api.PATCH('/api/v1/payment-occurrences/{occurrence_id}', { params: { path: { occurrence_id: o.id } }, body }),
      )
      toast('ok', body.status === 'paid' ? `«${o.title}» — оплата отмечена` : `«${o.title}» — оплата отменена`)
      setSelected(updated)
      setSelectedDay(updated.due_date)
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
      <div className="win-window min-w-0 max-w-full">
        <div className="win-titlebar">Календарь</div>
        <div className="min-w-0 bg-paper-2 px-2 pt-2 pb-3 text-ink">
          <PageTitle
            hideTitleOnDesk
            aside={
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="btn cal-nav" onClick={() => shift(-1)} aria-label="Предыдущий месяц">
                  ‹
                </button>
                <span className="font-sans text-lg font-semibold text-center" aria-live="polite">
                  {formatMonth(month)}
                </span>
                <button type="button" className="btn cal-nav" onClick={() => shift(1)} aria-label="Следующий месяц">
                  ›
                </button>
                <button className="btn btn-ghost" onClick={() => setMonth(new Date(parseISODate(today).getFullYear(), parseISODate(today).getMonth(), 1))}>
                  Сегодня
                </button>
                <button className="btn" onClick={() => openFeed()}>
                  В календарь телефона
                </button>
              </div>
            }
          >
            Календарь
          </PageTitle>

          <div
            className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-soft"
            aria-label="Легенда"
          >
            <span className="text-paid font-medium">Оплачено</span>
            <span>не оплачено</span>
            <span className="text-overdue">просроченная сумма</span>
          </div>

          <div className="cal-main desk:grid desk:grid-cols-2 desk:gap-4 desk:items-start">
            <div className="cal-main-grid min-w-0">
              {cal.error ? (
                <ErrorNote text={cal.error} onRetry={cal.reload} />
              ) : (
                <div className={`sheet min-w-0 ${cal.loading ? 'opacity-60' : ''}`} data-cal-grid>
                  <div className="grid grid-cols-7 border-b border-rule">
                    {WEEKDAYS.map((w) => (
                      <div key={w} className="px-1 py-1.5 text-[0.65rem] desk:text-[0.7rem] uppercase tracking-widest text-ink-soft">
                        {w}
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-7 min-w-0">
                    {cells.map((iso, i) => {
                      const day = iso ? byDay.get(iso) : undefined
                      const isToday = iso === today
                      const isSelected = iso === selectedDay
                      const tone = iso ? tones.get(iso) : undefined
                      const onDark = tone === 'overdue' || tone === 'pay'
                      const dayLabel = iso ? formatDate(iso) : undefined
                      return (
                        <div
                          key={i}
                          data-tone={tone ?? undefined}
                          {...(iso
                            ? {
                                role: 'button' as const,
                                tabIndex: 0,
                                onClick: () => selectDay(iso),
                                onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => {
                                  if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault()
                                    selectDay(iso)
                                  }
                                },
                                'aria-label': dayLabel,
                                'aria-pressed': isSelected,
                              }
                            : {})}
                          className={`cal-day-cell min-h-16 desk:min-h-[4.5rem] min-w-0 overflow-hidden border-b border-r border-rule p-1 ${i % 7 === 6 ? 'border-r-0' : ''} ${tone ? TONE_CLASS[tone] : ''} ${isSelected ? 'cal-day-selected' : ''}`}
                        >
                          {iso && (
                            <>
                              <div className="flex justify-between items-baseline pointer-events-none">
                                <span
                                  className={`num text-xs rounded-sm ${isToday ? (onDark ? 'bg-paper text-ink px-1' : 'bg-ink text-paper px-1') : 'text-ink-soft'} ${isSelected && !isToday ? 'underline' : ''}`}
                                >
                                  {parseISODate(iso).getDate()}
                                </span>
                              </div>
                              <ul className="mt-1 space-y-0.5">
                                {day?.occurrences.map((o) => (
                                  <li key={o.id} className="min-w-0">
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        selectDay(iso, o)
                                      }}
                                      className={`w-full min-w-0 text-left border-b border-rule py-0.5 text-[0.65rem] desk:text-[0.7rem] leading-tight truncate ${selected?.id === o.id ? 'font-semibold' : ''}`}
                                      style={{ minHeight: 0 }}
                                      title={`${o.title} — ${formatMoney(o.amount, o.currency)}`}
                                    >
                                      <span className="hand-only num">{o.currency}</span>
                                      <span className="desk-only truncate block">{o.title}</span>
                                    </button>
                                  </li>
                                ))}
                              </ul>
                              {day && (
                                <div className="desk-only mt-0.5 text-[0.6rem] leading-tight pointer-events-none">
                                  {day.totals.map((t) => (
                                    <div key={t.currency}>
                                      <div className="num text-ink-soft">{formatMoney(t.total.amount, t.currency)}</div>
                                      {Number(t.overdue.amount) > 0 && (
                                        <div className="num text-overdue">{formatMoney(t.overdue.amount, t.currency)}</div>
                                      )}
                                    </div>
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
            </div>

            <aside className="cal-detail-column min-w-0" aria-label="День и итоги">
              <div className="cal-detail-column-inner sheet min-w-0">
                <CalendarDayDetailPanel
                  selectedDay={selectedDay}
                  day={selectedDayData}
                  selectedOccurrence={activeOccurrence}
                  busy={busy}
                  onSelectOccurrence={setSelected}
                  onPayToday={(o) => patch(o, { status: 'paid', paid_date: today })}
                  onPayWithDate={setPaying}
                  onUnpay={(o) => patch(o, { status: 'unpaid' })}
                  onChangeDate={setPaying}
                />
                <section className="cal-asof-summary px-4 pb-4 pt-3 border-t border-rule" aria-labelledby="asof-title">
                  <div className="flex flex-wrap items-end gap-3 mb-3">
                    <h2 id="asof-title" className="font-sans text-lg font-semibold">
                      Итоги на дату
                    </h2>
                    <div>
                      <label className="sr-only" htmlFor="as-of">
                        Дата
                      </label>
                      <input
                        id="as-of"
                        type="date"
                        className="field num w-full min-w-0 desk:w-auto"
                        value={asOf || today}
                        onChange={(e) => setAsOf(e.target.value)}
                      />
                    </div>
                    {asOf && (
                      <button type="button" className="btn btn-ghost" onClick={() => setAsOf('')}>
                        На сегодня
                      </button>
                    )}
                  </div>
                  {summary.error ? (
                    <ErrorNote text={summary.error} />
                  ) : summary.data ? (
                    <SummaryCards summary={summary.data} />
                  ) : (
                    <Loading />
                  )}
                </section>
              </div>
            </aside>
          </div>

          {feed && (
            <section className="sheet p-4 mt-4 fade-in" aria-label="Подписка на календарь">
              <div className="flex justify-between items-start gap-3">
                <div className="min-w-0">
                  <h2 className="font-sans text-lg font-semibold">Календарь в телефоне</h2>
                  <p className="text-sm text-ink-soft mt-1">
                    Все сроки появятся в Google или Apple Календаре с напоминанием за 3 дня и в день оплаты; обновляется
                    автоматически. Ссылка личная — не пересылайте её. Если сменить ссылку, старая перестанет открывать календарь.
                  </p>
                </div>
                <button className="btn btn-ghost" onClick={() => setFeed(null)}>
                  Закрыть
                </button>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                <a className="btn btn-primary" href={feed.webcal_url}>
                  Открыть в Календаре (iPhone, Mac)
                </a>
                <a className="btn" href={googleSubscribeHref(feed.url)} target="_blank" rel="noopener noreferrer">
                  Google Календарь
                </a>
                <button className="btn" onClick={() => navigator.clipboard?.writeText(feed.url).then(() => toast('ok', 'Ссылка скопирована'))}>
                  Скопировать ссылку
                </button>
                <button className="btn btn-ghost whitespace-normal text-center" onClick={() => openFeed(true)}>
                  Сменить ссылку, старая перестанет работать
                </button>
              </div>
              <code className="num text-xs break-all block mt-2 text-ink-soft">{feed.url}</code>
            </section>
          )}

        </div>
      </div>

      <MarkPaidDialog occurrence={paying} today={today} busy={busy} onClose={() => setPaying(null)} onSubmit={(d) => paying && patch(paying, { status: 'paid', paid_date: d })} />
    </>
  )
}
