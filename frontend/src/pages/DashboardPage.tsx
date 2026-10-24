import { useEffect, useMemo, useRef, useState } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { ReceiptDialog } from '../components/ReceiptDialog'
import { OverdueCell, StatusCell } from '../components/Status'
import { SummaryCards } from '../components/SummaryCards'
import { Upcoming } from '../components/Upcoming'
import { ConfirmDialog, Empty, ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { CURRENCIES, formatDate, formatMoney } from '../i18n/format'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'

type Tab = 'topay' | 'overdue' | 'paid' | 'all'
type Sort = 'due_date' | '-due_date' | 'amount' | '-amount' | 'title' | '-title' | 'paid_date' | '-paid_date'
type Filters = {
  tab: Tab
  currency: string
  overdue: '' | 'true' | 'false'
  from: string
  to: string
  q: string
  sort: Sort
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'topay', label: 'Что оплатить' },
  { id: 'overdue', label: 'Просрочено' },
  { id: 'paid', label: 'Оплачено' },
  { id: 'all', label: 'Все периоды' },
]
const DEFAULT: Filters = { tab: 'topay', currency: '', overdue: '', from: '', to: '', q: '', sort: 'due_date' }
const STORE_KEY = 'ik-dashboard-filters'
const PAGE_SIZE = 25

function loadFilters(): Filters {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (raw) return { ...DEFAULT, ...JSON.parse(raw) }
  } catch {
    /* ignore */
  }
  return DEFAULT
}

export function DashboardPage() {
  const toast = useToast()
  const { isAdmin } = useAuth()
  const { today, fake } = useServerToday()
  const [f, setF] = useState<Filters>(loadFilters)
  const [page, setPage] = useState(1)
  const [paying, setPaying] = useState<Occurrence | null>(null)
  const [unpaying, setUnpaying] = useState<Occurrence | null>(null)
  const [receiptFor, setReceiptFor] = useState<Occurrence | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(f))
    } catch {
      /* ignore */
    }
  }, [f])

  const query = useMemo(() => {
    const q: Record<string, string | number | boolean> = { sort: f.sort, page, page_size: PAGE_SIZE }
    if (f.tab === 'topay') q.status = 'unpaid'
    if (f.tab === 'paid') q.status = 'paid'
    if (f.tab === 'overdue') {
      q.status = 'unpaid'
      q.overdue = true
    }
    if (f.tab !== 'overdue' && f.overdue) q.overdue = f.overdue === 'true'
    if (f.currency) q.currency = f.currency
    if (f.from) q.from = f.from
    if (f.to) q.to = f.to
    if (f.q.trim()) q.q = f.q.trim()
    return q
  }, [f, page])

  const list = useLoad(
    async () => unwrap(await api.GET('/api/v1/payment-occurrences', { params: { query: query as never } })),
    [JSON.stringify(query)],
  )
  const summaryQuery = useMemo(() => ({ ...(f.from ? { from: f.from } : {}), ...(f.to ? { to: f.to } : {}) }), [f.from, f.to])
  const summary = useLoad(
    async () => unwrap(await api.GET('/api/v1/payments/summary', { params: { query: summaryQuery as never } })),
    [JSON.stringify(summaryQuery)],
  )

  const set = (patch: Partial<Filters>) => {
    setF((x) => ({ ...x, ...patch }))
    setPage(1)
  }
  const toggleSort = (col: 'due_date' | 'amount' | 'title' | 'paid_date') =>
    set({ sort: (f.sort === col ? `-${col}` : col) as Sort })
  const sortMark = (col: string) => (f.sort === col ? ' ↑' : f.sort === `-${col}` ? ' ↓' : '')
  const ariaSort = (col: string) => (f.sort === col ? 'ascending' : f.sort === `-${col}` ? 'descending' : 'none')

  const refresh = () => {
    list.reload()
    summary.reload()
    setVersion((v) => v + 1)
  }

  const markPaid = async (o: Occurrence, paidDate: string) => {
    setBusy(true)
    try {
      unwrap(
        await api.PATCH('/api/v1/payment-occurrences/{occurrence_id}', {
          params: { path: { occurrence_id: o.id } },
          body: { status: 'paid', paid_date: paidDate },
        }),
      )
      toast('ok', `«${o.title}» — оплата отмечена`)
      setPaying(null)
      refresh()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const markUnpaid = async (o: Occurrence) => {
    setBusy(true)
    try {
      unwrap(
        await api.PATCH('/api/v1/payment-occurrences/{occurrence_id}', {
          params: { path: { occurrence_id: o.id } },
          body: { status: 'unpaid' },
        }),
      )
      toast('ok', `«${o.title}» — оплата отменена`)
      setUnpaying(null)
      refresh()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const qrInput = useRef<HTMLInputElement>(null)
  const scanReceipt = async (file: File) => {
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/v1/receipts/scan', { method: 'POST', body: form, credentials: 'same-origin' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body?.error?.message ?? `Ошибка ${res.status}`)
      toast(body.status === 'matched' ? 'ok' : 'error', body.message)
      if (body.status === 'matched') refresh()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
      if (qrInput.current) qrInput.current.value = ''
    }
  }

  const runChecks = async () => {
    setBusy(true)
    try {
      const r = unwrap(await api.POST('/api/v1/admin/run-checks'))
      const parts = [
        r.sent ? `отправлено уведомлений: ${r.sent}` : null,
        r.reminders_queued ? `в очереди: ${r.reminders_queued}` : null,
        r.periods_created ? `новых периодов: ${r.periods_created}` : null,
        r.failed ? `ошибок отправки: ${r.failed}` : null,
      ].filter(Boolean)
      toast(r.failed ? 'error' : 'ok', parts.length ? `Проверка: ${parts.join(', ')}` : 'Проверка: всё уже отправлено, новых напоминаний нет')
      refresh()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1
  const hasExtraFilters = f.currency || f.overdue || f.from || f.to || f.q

  return (
    <>
      <PageTitle
        aside={
          <span className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-ink-soft">
              Сегодня <span className="num text-ink">{formatDate(today)}</span>
              {fake && <span className="ml-2 text-amber num text-xs">[APP_FAKE_TODAY]</span>}
            </span>
            <input
              ref={qrInput}
              type="file"
              accept="image/png,image/jpeg,application/pdf"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && scanReceipt(e.target.files[0])}
            />
            <button
              className="btn btn-sm"
              onClick={() => qrInput.current?.click()}
              disabled={busy}
              title="Фото или PDF кассового чека: сумма и дата берутся из QR, оплата отмечается сама"
            >
              Чек по QR
            </button>
            {isAdmin && (
              <button className="btn btn-sm" onClick={runChecks} disabled={busy} title="Сгенерировать периоды и разослать напоминания прямо сейчас">
                Проверить сейчас
              </button>
            )}
          </span>
        }
      >
        Платежи
      </PageTitle>

      {summary.error ? (
        <ErrorNote text={summary.error} onRetry={summary.reload} />
      ) : summary.data ? (
        <SummaryCards summary={summary.data} />
      ) : (
        <Loading />
      )}

      <Upcoming today={today} version={version} busy={busy} onPay={(o) => markPaid(o, today)} />

      <div className="flex flex-wrap gap-x-1 gap-y-2 mb-3" role="tablist" aria-label="Что показать">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={f.tab === t.id}
            onClick={() => set({ tab: t.id })}
            className={`px-3 py-1.5 text-sm border-b-2 ${
              f.tab === t.id ? 'border-ink font-semibold' : 'border-transparent text-ink-soft hover:text-ink'
            } ${t.id === 'overdue' ? 'text-red' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-2 items-end mb-4">
        <div className="col-span-2 md:col-span-1">
          <label className="label" htmlFor="f-q">
            Поиск
          </label>
          <input id="f-q" className="field" placeholder="Название" value={f.q} onChange={(e) => set({ q: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="f-cur">
            Валюта
          </label>
          <select id="f-cur" className="field" value={f.currency} onChange={(e) => set({ currency: e.target.value })}>
            <option value="">Все</option>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-over">
            Просрочка
          </label>
          <select
            id="f-over"
            className="field"
            value={f.tab === 'overdue' ? 'true' : f.overdue}
            disabled={f.tab === 'overdue'}
            onChange={(e) => set({ overdue: e.target.value as Filters['overdue'] })}
          >
            <option value="">Любая</option>
            <option value="true">С просрочкой</option>
            <option value="false">Без просрочки</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-from">
            Срок с
          </label>
          <input id="f-from" type="date" className="field num" value={f.from} onChange={(e) => set({ from: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="f-to">
            по
          </label>
          <input id="f-to" type="date" className="field num" value={f.to} onChange={(e) => set({ to: e.target.value })} />
        </div>
        <button
          className="btn btn-sm btn-ghost col-span-2 md:col-span-1"
          disabled={!hasExtraFilters}
          onClick={() => set({ currency: '', overdue: '', from: '', to: '', q: '' })}
        >
          Сбросить
        </button>
      </div>

      <div className="sheet overflow-x-auto">
        {list.error ? (
          <div className="p-4">
            <ErrorNote text={list.error} onRetry={list.reload} />
          </div>
        ) : !list.data ? (
          <Loading />
        ) : list.data.items.length === 0 ? (
          <Empty
            title={f.tab === 'overdue' ? 'Просрочек нет' : f.tab === 'topay' ? 'Всё оплачено' : 'Ничего не найдено'}
            hint={hasExtraFilters ? 'Попробуйте сбросить фильтры' : undefined}
          />
        ) : (
          <>
          <ul className={`md:hidden divide-y divide-rule ${list.loading ? 'opacity-60' : ''}`}>
            {list.data.items.map((o) => (
              <li key={o.id} className="p-3">
                <div className="flex justify-between gap-3">
                  <span className="font-semibold">{o.title}</span>
                  <span className="num whitespace-nowrap">{formatMoney(o.amount, o.currency)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm">
                  <span className="num text-ink-soft">срок {formatDate(o.due_date)}</span>
                  <StatusCell o={o} />
                  <OverdueCell o={o} />
                </div>
                {o.paid_date && <p className="text-xs text-ink-soft mt-1 num">оплачено {formatDate(o.paid_date)}</p>}
                {o.recurring_payment_deleted && <p className="text-xs text-ink-soft">платёж прекращён</p>}
                <div className="flex flex-wrap gap-1 mt-2">
                  {o.status === 'unpaid' ? (
                    <>
                      <button className="btn btn-sm btn-primary" onClick={() => markPaid(o, today)} disabled={busy}>Оплачено</button>
                      <button className="btn btn-sm" onClick={() => setPaying(o)} disabled={busy}>Дата…</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-sm" onClick={() => setPaying(o)} disabled={busy}>Изменить дату</button>
                      <button className="btn btn-sm btn-danger" onClick={() => setUnpaying(o)} disabled={busy}>Отменить оплату</button>
                    </>
                  )}
                  <button className="btn btn-sm btn-ghost" onClick={() => setReceiptFor(o)}>{o.has_receipt ? 'Чек ✓' : 'Чек'}</button>
                </div>
              </li>
            ))}
          </ul>
          <table className={`ledger hidden md:table w-full min-w-[760px] ${list.loading ? 'opacity-60' : ''}`}>
            <thead>
              <tr>
                <th aria-sort={ariaSort('title')}>
                  <button onClick={() => toggleSort('title')}>Название{sortMark('title')}</button>
                </th>
                <th className="text-right" aria-sort={ariaSort('amount')}>
                  <button onClick={() => toggleSort('amount')}>Сумма{sortMark('amount')}</button>
                </th>
                <th>Валюта</th>
                <th aria-sort={ariaSort('due_date')}>
                  <button onClick={() => toggleSort('due_date')}>Срок{sortMark('due_date')}</button>
                </th>
                <th>Статус</th>
                <th aria-sort={ariaSort('paid_date')}>
                  <button onClick={() => toggleSort('paid_date')}>Дата оплаты{sortMark('paid_date')}</button>
                </th>
                <th>Просрочка</th>
                <th className="text-right">
                  <span className="sr-only">Действия</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((o) => (
                <tr key={o.id}>
                  <td>
                    <span className="font-semibold">{o.title}</span>
                    {o.has_receipt && (
                      <button className="ml-2 num text-[0.65rem] uppercase tracking-wider border border-ink-soft text-ink-soft px-1 rounded-sm align-middle" onClick={() => setReceiptFor(o)} title="Открыть чек">
                        чек
                      </button>
                    )}
                    {o.recurring_payment_deleted && (
                      <span className="block text-xs text-ink-soft" title="Регулярный платёж прекращён, история сохранена">
                        платёж прекращён
                      </span>
                    )}
                  </td>
                  <td className="num text-right whitespace-nowrap">{formatMoney(o.amount, o.currency)}</td>
                  <td className="num text-sm">{o.currency}</td>
                  <td className="num text-sm whitespace-nowrap">{formatDate(o.due_date)}</td>
                  <td>
                    <StatusCell o={o} />
                  </td>
                  <td className="num text-sm whitespace-nowrap">{formatDate(o.paid_date)}</td>
                  <td>
                    <OverdueCell o={o} />
                  </td>
                  <td className="text-right whitespace-nowrap">
                    <button className="btn btn-sm btn-ghost mr-1" onClick={() => setReceiptFor(o)} aria-label={`Чек для «${o.title}»`}>
                      Чек
                    </button>
                    {o.status === 'unpaid' ? (
                      <span className="inline-flex gap-1">
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => markPaid(o, today)}
                          disabled={busy}
                          title="Отметить оплату сегодняшней датой"
                        >
                          Оплачено
                        </button>
                        <button className="btn btn-sm" onClick={() => setPaying(o)} disabled={busy} aria-label={`Выбрать дату оплаты для «${o.title}»`}>
                          Дата…
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex gap-1">
                        <button className="btn btn-sm" onClick={() => setPaying(o)} disabled={busy}>
                          Изменить дату
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => setUnpaying(o)} disabled={busy}>
                          Отменить оплату
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
      </div>

      {list.data && list.data.total > PAGE_SIZE && (
        <nav className="flex items-center justify-between mt-3 text-sm" aria-label="Страницы">
          <span className="text-ink-soft">
            Всего: <span className="num">{list.data.total}</span>
          </span>
          <span className="flex items-center gap-2">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ← Назад
            </button>
            <span className="num">
              {page} / {pages}
            </span>
            <button className="btn btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Вперёд →
            </button>
          </span>
        </nav>
      )}

      <MarkPaidDialog
        occurrence={paying}
        today={today}
        busy={busy}
        onClose={() => setPaying(null)}
        onSubmit={(d) => paying && markPaid(paying, d)}
      />
      <ReceiptDialog occurrence={receiptFor} onClose={() => setReceiptFor(null)} onChanged={list.reload} />
      <ConfirmDialog
        open={!!unpaying}
        title="Отменить оплату?"
        body={unpaying && `«${unpaying.title}», срок ${formatDate(unpaying.due_date)}. Фактическая дата оплаты будет очищена.`}
        confirmText="Отменить оплату"
        danger
        busy={busy}
        onConfirm={() => unpaying && markUnpaid(unpaying)}
        onClose={() => setUnpaying(null)}
      />
    </>
  )
}
