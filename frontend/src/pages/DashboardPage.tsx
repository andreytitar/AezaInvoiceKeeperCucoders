import { useEffect, useMemo, useState } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { needsPayConfirm } from '../components/largePayment'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { PaymentRowActions } from '../components/PaymentRowActions'
import { ReceiptDialog } from '../components/ReceiptDialog'
import { OverdueCell, StatusCell, amountHot } from '../components/Status'
import { SummaryCards } from '../components/SummaryCards'
import { Upcoming } from '../components/Upcoming'
import {
  ConfirmDialog,
  Empty,
  ErrorNote,
  FilterField,
  FilterFieldAction,
  Loading,
  PageTitle,
  filterActionBtnCls,
  filterControlCls,
  paymentsFilterRowCls,
} from '../components/ui'
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
  { id: 'topay', label: 'К оплате' },
  { id: 'overdue', label: 'Просрочено' },
  { id: 'paid', label: 'Оплачено' },
  { id: 'all', label: 'Все' },
]
const SORTS: { id: Sort; label: string }[] = [
  { id: 'due_date', label: 'Срок, раньше' },
  { id: '-due_date', label: 'Срок, позже' },
  { id: 'amount', label: 'Сумма по возрастанию' },
  { id: '-amount', label: 'Сумма по убыванию' },
  { id: 'title', label: 'Название, А–Я' },
  { id: '-title', label: 'Название, Я–А' },
  { id: 'paid_date', label: 'Дата оплаты, раньше' },
  { id: '-paid_date', label: 'Дата оплаты, позже' },
]
const DEFAULT: Filters = { tab: 'topay', currency: '', overdue: '', from: '', to: '', q: '', sort: 'due_date' }
const STORE_KEY = 'ik-dashboard-filters'
const PAGE_SIZE = 25

type PendingAction =
  | { kind: 'unpay'; occurrence: Occurrence }
  | { kind: 'pay'; occurrence: Occurrence; paidDate: string }

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
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [receiptFor, setReceiptFor] = useState<Occurrence | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  const [filtersOpen, setFiltersOpen] = useState(false)

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
      setPending(null)
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
      setPending(null)
      refresh()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
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

  const startMarkPaid = (o: Occurrence, paidDate: string) => {
    if (needsPayConfirm(o.status, o.amount, o.currency)) {
      setPending({ kind: 'pay', occurrence: o, paidDate })
      return
    }
    void markPaid(o, paidDate)
  }

  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1
  const hasExtraFilters = f.currency || f.overdue || f.from || f.to || f.q

  return (
    <>
      <div className="win-window min-w-0 max-w-full">
        <div className="win-titlebar">Платежи</div>
        <div className="dashboard-body min-w-0 bg-paper-2 px-3 pt-2 pb-3 text-ink desk:px-4">
      <PageTitle
        hideTitleOnDesk
        aside={
          <span className="flex items-center gap-2 flex-wrap desk:ml-auto">
            <span className="text-sm text-ink-soft">
              <span className="num text-ink">{formatDate(today)}</span>
              {fake && <span className="ml-2 num text-xs text-ink-soft">[fake]</span>}
            </span>
            {isAdmin && (
              <button className="btn btn-primary btn-sm desk:min-h-[44px]" onClick={runChecks} disabled={busy} title="Периоды и напоминания сейчас">
                Проверить
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

      <Upcoming today={today} version={version} busy={busy} onPay={(o) => startMarkPaid(o, today)} />

      <div className="mb-3 flex gap-1 overflow-x-auto pb-0.5" role="tablist" aria-label="Что показать">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={f.tab === t.id}
            onClick={() => set({ tab: t.id })}
            className={`shrink-0 rounded-sm px-2.5 py-1.5 text-sm min-h-[44px] desk:min-h-0 ${
              f.tab === t.id ? 'bg-ink font-semibold text-paper-2' : 'text-ink-soft hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="hand-only mb-4">
        <label className="label" htmlFor="f-sort">
          Сортировка
        </label>
        <select id="f-sort" className="field" value={f.sort} onChange={(e) => set({ sort: e.target.value as Sort })}>
          {SORTS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <div className="hand-only mb-2">
        <button
          type="button"
          className="btn btn-ghost flex w-full min-h-[44px] items-center justify-between gap-2 px-2"
          aria-expanded={filtersOpen}
          onClick={() => setFiltersOpen((v) => !v)}
        >
          <span>Фильтры{hasExtraFilters ? ' · активны' : ''}</span>
          <span className="text-ink-soft" aria-hidden="true">
            {filtersOpen ? '▴' : '▾'}
          </span>
        </button>
      </div>

      <div className={`payments-filters ${paymentsFilterRowCls} ${filtersOpen ? '' : 'hand:hidden'}`}>
        <FilterField label="Поиск" htmlFor="f-q">
          <input
            id="f-q"
            className={filterControlCls}
            placeholder="Название"
            value={f.q}
            onChange={(e) => set({ q: e.target.value })}
          />
        </FilterField>
        <FilterField label="Валюта" htmlFor="f-cur">
          <select id="f-cur" className={filterControlCls} value={f.currency} onChange={(e) => set({ currency: e.target.value })}>
            <option value="">Все</option>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Просрочка" htmlFor="f-over">
          <select
            id="f-over"
            className={filterControlCls}
            value={f.tab === 'overdue' ? 'true' : f.overdue}
            disabled={f.tab === 'overdue'}
            onChange={(e) => set({ overdue: e.target.value as Filters['overdue'] })}
          >
            <option value="">Любая</option>
            <option value="true">С просрочкой</option>
            <option value="false">Без просрочки</option>
          </select>
        </FilterField>
        <FilterField label="Срок с" htmlFor="f-from">
          <input
            id="f-from"
            type="date"
            className={`${filterControlCls} num`}
            value={f.from}
            onChange={(e) => set({ from: e.target.value })}
          />
        </FilterField>
        <FilterField label="По" htmlFor="f-to">
          <input id="f-to" type="date" className={`${filterControlCls} num`} value={f.to} onChange={(e) => set({ to: e.target.value })} />
        </FilterField>
        <FilterFieldAction label="Сбросить">
          <button
            type="button"
            className={filterActionBtnCls}
            disabled={!hasExtraFilters}
            onClick={() => set({ currency: '', overdue: '', from: '', to: '', q: '' })}
          >
            Сбросить
          </button>
        </FilterFieldAction>
      </div>

      <div className="payments-list-sheet sheet min-w-0 desk:rounded-sm">
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
          <ul className={`hand-only ${list.loading ? 'opacity-60' : ''}`}>
            {list.data.items.map((o) => (
              <li key={o.id} className="slip">
                <div className="slip-row">
                  <span className="font-semibold min-w-0">{o.title}</span>
                  <span className={`num min-w-0 break-all text-right ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</span>
                </div>
                <div className="slip-row text-sm">
                  <span className="num">срок {formatDate(o.due_date)}</span>
                  <StatusCell o={o} />
                </div>
                <div className="slip-row text-sm">
                  <OverdueCell o={o} />
                  {o.paid_date && <span className="num text-ink-soft">оплачено {formatDate(o.paid_date)}</span>}
                </div>
                {o.recurring_payment_deleted && <p className="text-xs text-ink-soft">платёж прекращён</p>}
                <PaymentRowActions
                  occurrence={o}
                  busy={busy}
                  placement="slip"
                  onPaidToday={() => startMarkPaid(o, today)}
                  onPickDate={() => setPaying(o)}
                  onReceipt={() => setReceiptFor(o)}
                  onUnpay={() => setPending({ kind: 'unpay', occurrence: o })}
                />
              </li>
            ))}
          </ul>
          <table className={`ledger desk-only w-full ${list.loading ? 'opacity-60' : ''}`}>
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
                <th className="w-px whitespace-nowrap text-right">
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
                      <button className="ml-2 text-xs uppercase tracking-wider text-ink-soft align-middle" onClick={() => setReceiptFor(o)} title="Открыть чек">
                        чек
                      </button>
                    )}
                    {o.recurring_payment_deleted && (
                      <span className="block text-xs text-ink-soft" title="Регулярный платёж прекращён, история сохранена">
                        платёж прекращён
                      </span>
                    )}
                  </td>
                  <td className={`num text-right ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</td>
                  <td className="num text-sm">{o.currency}</td>
                  <td className="num text-sm">{formatDate(o.due_date)}</td>
                  <td>
                    <StatusCell o={o} />
                  </td>
                  <td className="num text-sm">{formatDate(o.paid_date)}</td>
                  <td>
                    <OverdueCell o={o} />
                  </td>
                  <td className="w-px whitespace-nowrap text-right">
                    <PaymentRowActions
                      occurrence={o}
                      busy={busy}
                      placement="table"
                      onPaidToday={() => startMarkPaid(o, today)}
                      onPickDate={() => setPaying(o)}
                      onReceipt={() => setReceiptFor(o)}
                      onUnpay={() => setPending({ kind: 'unpay', occurrence: o })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
      </div>

      {list.data && list.data.total > PAGE_SIZE && (
        <nav className="flex flex-col gap-2 desk:flex-row desk:items-center desk:justify-between mt-3 text-sm" aria-label="Страницы">
          <span className="text-ink-soft">
            Всего: <span className="num">{list.data.total}</span>
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Назад
            </button>
            <span className="num">
              {page} / {pages}
            </span>
            <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Вперёд
            </button>
          </span>
        </nav>
      )}
        </div>
      </div>

      <MarkPaidDialog
        occurrence={paying}
        today={today}
        busy={busy}
        onClose={() => setPaying(null)}
        onSubmit={(d) => paying && markPaid(paying, d)}
      />
      <ReceiptDialog occurrence={receiptFor} onClose={() => setReceiptFor(null)} onChanged={list.reload} />
      <ConfirmDialog
        open={!!pending}
        title={pending?.kind === 'pay' ? 'Отметить оплату?' : 'Отменить оплату?'}
        body={
          pending?.kind === 'pay' ? (
            <>
              <span className="text-ink">«{pending.occurrence.title}»</span>
              {' · '}
              <span className={`num ${amountHot(pending.occurrence) ? 'text-overdue' : 'text-ink'}`}>
                {formatMoney(pending.occurrence.amount, pending.occurrence.currency)}
              </span>
            </>
          ) : (
            pending && `«${pending.occurrence.title}», срок ${formatDate(pending.occurrence.due_date)}. Фактическая дата оплаты будет очищена.`
          )
        }
        confirmText={pending?.kind === 'pay' ? 'Отметить' : 'Отменить оплату'}
        danger={pending?.kind === 'unpay'}
        busy={busy}
        onConfirm={() => {
          if (!pending) return
          if (pending.kind === 'pay') void markPaid(pending.occurrence, pending.paidDate)
          else void markUnpaid(pending.occurrence)
        }}
        onClose={() => setPending(null)}
      />
    </>
  )
}
