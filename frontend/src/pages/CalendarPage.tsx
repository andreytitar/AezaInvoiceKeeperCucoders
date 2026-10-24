import { useMemo, useState } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { CalendarDayDetailPanel } from '../components/CalendarDayDetailPanel'
import { Icon } from '../components/Icon'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { SummaryCards } from '../components/SummaryCards'
import { Badge, Button, Card, DateInput, ErrorNote, PageTitle, Skeleton } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { formatDate, formatMoney, formatMonth, parseISODate, toISODate } from '../i18n/format'
import { useToast } from '../store/toast'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Google accepts an https ICS URL in cid, rather than webcal or /calendar/r. */
function googleSubscribeHref(icsUrl: string): string {
  return `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(icsUrl)}`
}

function occurrenceTone(o: Occurrence): string {
  if (o.status === 'paid') return 'bg-paid'
  return o.is_overdue ? 'bg-overdue' : 'bg-accent'
}

function pickOccurrence(day: { occurrences: Occurrence[] } | undefined, current: Occurrence | null): Occurrence | null {
  if (!day?.occurrences.length) return null
  return day.occurrences.find((o) => o.id === current?.id) ?? day.occurrences[0]
}

export function CalendarPage() {
  const { today } = useServerToday()
  // Resolve the server date before retaining month/day selection, including APP_FAKE_TODAY.
  return <CalendarView key={today} today={today} />
}

function CalendarView({ today }: { today: string }) {
  const toast = useToast()
  const [month, setMonth] = useState(() => {
    const d = parseISODate(today)
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [selectedDay, setSelectedDay] = useState(today)
  const [selected, setSelected] = useState<Occurrence | null>(null)
  const [paying, setPaying] = useState<Occurrence | null>(null)
  const [busy, setBusy] = useState(false)
  const [asOf, setAsOf] = useState('')
  const [feed, setFeed] = useState<{ url: string; webcal_url: string } | null>(null)
  const [feedBusy, setFeedBusy] = useState(false)

  const openFeed = async (rotate = false) => {
    setFeedBusy(true)
    try {
      setFeed(unwrap(rotate ? await api.POST('/api/v1/calendar/feed/rotate') : await api.GET('/api/v1/calendar/feed')))
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setFeedBusy(false)
    }
  }

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
    const count = Math.ceil((lead + range.last.getDate()) / 7) * 7
    return Array.from({ length: count }, (_, i) => {
      const date = new Date(month.getFullYear(), month.getMonth(), i - lead + 1)
      return { iso: toISODate(date), date, inMonth: date.getMonth() === month.getMonth() }
    })
  }, [range, month])

  const selectedDayData = byDay.get(selectedDay)
  const activeOccurrence = pickOccurrence(selectedDayData, selected)

  const shift = (n: number) => {
    const next = new Date(month.getFullYear(), month.getMonth() + n, 1)
    setMonth(next)
    const t = parseISODate(today)
    setSelectedDay(next.getFullYear() === t.getFullYear() && next.getMonth() === t.getMonth() ? today : toISODate(next))
    setSelected(null)
  }

  const goToday = () => {
    const t = parseISODate(today)
    setMonth(new Date(t.getFullYear(), t.getMonth(), 1))
    setSelectedDay(today)
    setSelected(null)
  }

  const selectDay = (iso: string, occurrence?: Occurrence) => {
    setSelectedDay(iso)
    setSelected(occurrence ?? pickOccurrence(byDay.get(iso), null))
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
      cal.reload()
      summary.reload()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const copyFeed = async () => {
    if (!feed) return
    try {
      if (!navigator.clipboard) throw new Error('Не удалось скопировать ссылку. Скопируйте её из строки ниже.')
      await navigator.clipboard.writeText(feed.url)
      toast('ok', 'Ссылка скопирована')
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Не удалось скопировать ссылку')
    }
  }

  return (
    <>
      <PageTitle>Календарь</PageTitle>
      <div className="mb-4 flex min-w-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-0.5 rounded-xl border border-rule bg-paper-2 p-0.5">
          <Button variant="ghost" size="sm" className="w-9 shrink-0 !px-0" onClick={() => shift(-1)} aria-label="Предыдущий месяц">
            <Icon name="chevron-left" />
          </Button>
          <span className="min-w-0 whitespace-nowrap px-1 text-center text-sm font-semibold md:px-3 md:text-base" aria-live="polite">
            {formatMonth(month)}
          </span>
          <Button variant="ghost" size="sm" className="w-9 shrink-0 !px-0" onClick={() => shift(1)} aria-label="Следующий месяц">
            <Icon name="chevron-right" />
          </Button>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" size="sm" onClick={goToday}>Сегодня</Button>
          <Button variant="secondary" size="sm" className="max-md:w-10 max-md:!px-0" onClick={() => openFeed()} loading={feedBusy} aria-label="В календарь телефона">
            <Icon name="calendar" />
            <span className="hidden md:inline">В календарь телефона</span>
          </Button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Легенда календаря">
        <Badge tone="paid">Оплачено</Badge>
        <Badge tone="accent">К оплате</Badge>
        <Badge tone="overdue">Просрочено</Badge>
      </div>

      <div className="grid min-w-0 grid-cols-1 items-start gap-4 min-[1200px]:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {cal.error ? (
            <ErrorNote text={cal.error} onRetry={cal.reload} />
          ) : !cal.data ? (
            <Skeleton className="h-[440px] w-full" />
          ) : (
            <Card className={`overflow-hidden !p-0 ${cal.loading ? 'opacity-60' : ''}`} data-cal-grid aria-busy={cal.loading}>
              <div className="grid grid-cols-7 border-b border-rule bg-paper px-1">
                {WEEKDAYS.map((w) => (
                  <div key={w} className="py-3 text-center text-xs font-medium text-ink-soft">{w}</div>
                ))}
              </div>
              <div className="grid min-w-0 grid-cols-7 gap-px bg-rule">
                {cells.map(({ iso, date, inMonth }) => {
                  if (!inMonth) {
                    return (
                      <div key={iso} className="min-h-[68px] bg-paper p-1.5 text-center min-[1024px]:min-h-[124px] min-[1024px]:p-2 min-[1024px]:text-left" aria-hidden="true">
                        <span className="num inline-flex h-7 w-7 items-center justify-center text-xs text-ink-soft opacity-40">{date.getDate()}</span>
                      </div>
                    )
                  }
                  const day = byDay.get(iso)
                  const occurrences = day?.occurrences ?? []
                  const isToday = iso === today
                  const isSelected = iso === selectedDay
                  return (
                    <div key={iso} className={`relative min-h-[68px] min-w-0 p-1.5 min-[1024px]:min-h-[124px] min-[1024px]:p-2 ${isSelected ? 'bg-accent/10' : 'bg-paper-2'}`}>
                      <button
                        type="button"
                        className="absolute inset-0 z-0 rounded-none outline-offset-[-3px] transition-colors hover:bg-accent/5 focus-visible:outline-2 focus-visible:outline-accent"
                        onClick={() => selectDay(iso)}
                        aria-label={`${formatDate(iso)}${isToday ? ', сегодня' : ''}; платежей: ${occurrences.length}`}
                        aria-pressed={isSelected}
                        aria-current={isToday ? 'date' : undefined}
                      />
                      <span className={`num pointer-events-none relative mx-auto flex h-7 w-7 items-center justify-center rounded-full text-xs min-[1024px]:mx-0 ${isToday ? 'bg-accent font-semibold text-black' : 'text-ink'}`}>
                        {date.getDate()}
                      </span>
                      {occurrences.length > 0 && (
                        <>
                          <div className="pointer-events-none relative mt-2 flex items-center justify-center gap-1 min-[1024px]:hidden" aria-hidden="true">
                            {occurrences.slice(0, 3).map((o) => <span key={o.id} className={`h-1.5 w-1.5 shrink-0 rounded-full ${occurrenceTone(o)}`} />)}
                            {occurrences.length > 3 && <span className="text-[9px] leading-none text-ink-soft">+{occurrences.length - 3}</span>}
                          </div>
                          <div className="relative mt-1 hidden min-w-0 space-y-1 min-[1024px]:block">
                            {occurrences.slice(0, 2).map((o) => (
                              <button
                                key={o.id}
                                type="button"
                                className="block w-full min-w-0 rounded-md bg-paper px-1.5 py-1 text-left text-[10px] leading-tight transition-colors hover:bg-accent/15 focus-visible:outline-2 focus-visible:outline-accent"
                                onClick={() => selectDay(iso, o)}
                                title={`${o.title} · ${formatMoney(o.amount, o.currency)}`}
                              >
                                <span className="flex min-w-0 items-center gap-1">
                                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${occurrenceTone(o)}`} />
                                  <span className="min-w-0 truncate">{o.title}</span>
                                </span>
                                <span className="num mt-0.5 block whitespace-nowrap text-[9px] min-[1440px]:text-[10px]">{formatMoney(o.amount, o.currency)}</span>
                              </button>
                            ))}
                            {occurrences.length > 2 && <span className="pointer-events-none block px-1.5 text-[10px] text-ink-soft">+{occurrences.length - 2}</span>}
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
          <p className="mt-3 text-xs text-ink-soft">Выберите день, чтобы посмотреть платежи и отметить оплату.</p>
        </div>

        <aside className="grid min-w-0 gap-4 min-[768px]:grid-cols-2 min-[1200px]:grid-cols-1" aria-label="День и итоги">
          <Card className="min-w-0 !p-0">
            {cal.loading && !cal.data ? <div className="p-4"><Skeleton className="h-32 w-full" /></div> : (
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
            )}
          </Card>
          <Card className="min-w-0 !p-4">
            <div className="mb-4 flex items-center justify-between gap-2">
              <h2 id="asof-title" className="text-base font-semibold">Итоги на дату</h2>
              {asOf && <Button variant="ghost" size="sm" onClick={() => setAsOf('')}>Сегодня</Button>}
            </div>
            <label className="sr-only" htmlFor="as-of">Дата итогов</label>
            <DateInput id="as-of" className="mb-4 w-full" value={asOf || today} onChange={setAsOf} />
            {summary.error ? <ErrorNote text={summary.error} onRetry={summary.reload} /> : summary.data ? (
              <SummaryCards summary={summary.data} compact />
            ) : <Skeleton className="h-60 w-full" />}
          </Card>
        </aside>
      </div>

      {feed && (
        <Card className="mt-4 min-w-0 p-4" aria-label="Подписка на календарь">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold">Календарь в телефоне</h2>
              <p className="mt-1 max-w-3xl text-sm text-ink-soft">
                Все сроки появятся в Google или Apple Календаре с напоминанием за 3 дня и в день оплаты. Календарь обновляется автоматически. Ссылка личная — не пересылайте её.
              </p>
            </div>
            <Button variant="ghost" size="sm" className="w-10 shrink-0 !px-0" onClick={() => setFeed(null)} aria-label="Закрыть подписку на календарь"><Icon name="close" /></Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <a className="btn btn-primary" href={feed.webcal_url}>Apple Календарь</a>
            <a className="btn" href={googleSubscribeHref(feed.url)} target="_blank" rel="noopener noreferrer">Google Календарь</a>
            <Button variant="secondary" onClick={copyFeed}><Icon name="link" />Скопировать ссылку</Button>
            <Button variant="ghost" onClick={() => openFeed(true)} loading={feedBusy}>Сменить ссылку</Button>
          </div>
          <p className="mt-3 text-xs text-ink-soft">После смены ссылки прежняя подписка перестанет работать.</p>
          <code className="num mt-2 block whitespace-normal break-all text-xs text-ink-soft">{feed.url}</code>
        </Card>
      )}

      <MarkPaidDialog occurrence={paying} today={today} busy={busy} onClose={() => setPaying(null)} onSubmit={(d) => paying && patch(paying, { status: 'paid', paid_date: d })} />
    </>
  )
}
