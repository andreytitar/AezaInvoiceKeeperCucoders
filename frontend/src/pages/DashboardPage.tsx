import { useEffect, useMemo, useState } from 'react'
import { api, unwrap, type Occurrence } from '../api/client'
import { needsPayConfirm } from '../components/largePayment'
import { MarkPaidDialog } from '../components/MarkPaidDialog'
import { PaymentRowActions } from '../components/PaymentRowActions'
import { ReceiptDialog } from '../components/ReceiptDialog'
import { StatusCell, amountHot } from '../components/Status'
import { Icon } from '../components/Icon'
import { SummaryCards } from '../components/SummaryCards'
import { Upcoming } from '../components/Upcoming'
import {
  Button, Card, ConfirmDialog, DateInput, Dialog, EmptyState, ErrorNote,
  FilterField, Input, PageTitle, Select, Skeleton, Table, Tabs,
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
  const [filterResetVersion, setFilterResetVersion] = useState(0)

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

  const countQuery = useMemo(() => {
    const base = { ...query }
    for (const key of ['status', 'overdue', 'page', 'page_size', 'sort']) delete base[key]
    return base
  }, [query])
  const counts = useLoad(async () => {
    const values = await Promise.all(TABS.map(async ({ id }) => {
      const q: Record<string, string | number | boolean> = { ...countQuery, page_size: 1 }
      if (id === 'topay' || id === 'overdue') q.status = 'unpaid'
      if (id === 'paid') q.status = 'paid'
      if (id === 'overdue') q.overdue = true
      else if (f.overdue) q.overdue = f.overdue === 'true'
      const data = unwrap(await api.GET('/api/v1/payment-occurrences', { params: { query: q as never } }))
      return [id, data.total] as const
    }))
    return Object.fromEntries(values) as Record<Tab, number>
  }, [JSON.stringify(countQuery), f.overdue])

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
    counts.reload()
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
  useEffect(() => {
    if (list.data && page > pages) setPage(pages)
  }, [list.data, page, pages])
  const hasExtraFilters = Boolean(f.currency || f.overdue || f.from || f.to || f.q)
  const activeFilters = [f.currency, f.overdue, f.from, f.to, f.q].filter(Boolean).length
  const resetFilters = () => {
    set({ currency: '', overdue: '', from: '', to: '', q: '' })
    setFilterResetVersion((value) => value + 1)
  }
  const filterControls = (prefix: string) => (
    <div className={prefix === 'mobile' ? 'grid grid-cols-1 gap-4' : 'payment-filters-grid'}>
      <FilterField label="Поиск" htmlFor={`${prefix}-q`}>
        <Input id={`${prefix}-q`} placeholder="Название платежа" value={f.q} onChange={(e) => set({ q: e.target.value })} />
      </FilterField>
      <FilterField label="Валюта" htmlFor={`${prefix}-cur`}>
        <Select id={`${prefix}-cur`} value={f.currency} onChange={(e) => set({ currency: e.target.value })}>
          <option value="">Все валюты</option>
          {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
        </Select>
      </FilterField>
      <FilterField label="Просрочка" htmlFor={`${prefix}-over`}>
        <Select id={`${prefix}-over`} value={f.tab === 'overdue' ? 'true' : f.overdue} disabled={f.tab === 'overdue'} onChange={(e) => set({ overdue: e.target.value as Filters['overdue'] })}>
          <option value="">Любая</option>
          <option value="true">С просрочкой</option>
          <option value="false">Без просрочки</option>
        </Select>
      </FilterField>
      <FilterField label="Срок с" htmlFor={`${prefix}-from`}>
        <DateInput key={`${prefix}-from-${filterResetVersion}`} id={`${prefix}-from`} value={f.from} max={f.to || undefined} onChange={(value) => set({ from: value })} />
      </FilterField>
      <FilterField label="По" htmlFor={`${prefix}-to`}>
        <DateInput key={`${prefix}-to-${filterResetVersion}`} id={`${prefix}-to`} value={f.to} min={f.from || undefined} onChange={(value) => set({ to: value })} />
      </FilterField>
      <Button type="button" variant="ghost" onClick={resetFilters}>Сбросить</Button>
    </div>
  )

  return (
    <>
      <PageTitle aside={
        <div className="dashboard-toolbar flex flex-wrap items-center gap-3">
          <span className="num whitespace-nowrap text-sm text-ink-soft">
            {formatDate(today)}
            {fake && <span className="ml-2 text-xs" title="Дата в демонстрационном окружении">Демо-дата</span>}
          </span>
          {isAdmin && (
            <Button variant="secondary" onClick={runChecks} loading={busy} title="Создать периоды и отправить напоминания сейчас">
              <Icon name="bell" />
              Проверить напоминания
            </Button>
          )}
        </div>
      }>
        Платежи
      </PageTitle>

      {summary.error ? (
        <ErrorNote text={summary.error} onRetry={summary.reload} />
      ) : summary.data ? (
        <SummaryCards summary={summary.data} />
      ) : (
        <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-3" aria-label="Загрузка итогов" role="status">
          {[0, 1, 2].map((key) => <Card key={key} className="space-y-4 p-5"><Skeleton className="h-4 w-20" /><Skeleton className="h-9 w-3/4" /><Skeleton className="h-20 w-full" /></Card>)}
        </div>
      )}

      <Upcoming today={today} version={version} busy={busy} onPay={(o) => startMarkPaid(o, today)} />

      <Card className="payments-list-sheet min-w-0">
        <div className="space-y-4 p-4 lg:p-5">
          <Tabs label="Статус платежей" items={TABS.map((t) => ({ value: t.id, label: t.label, count: counts.data?.[t.id] ?? (t.id === f.tab ? list.data?.total : undefined) }))} value={f.tab} onChange={(value) => set({ tab: value as Tab })} />
          <div className="payment-filters-desktop">{filterControls('desktop')}</div>
          <div className="payment-filters-mobile flex flex-wrap items-center gap-2">
            <Input className="min-w-0 flex-1" aria-label="Поиск платежа" placeholder="Найти платёж" value={f.q} onChange={(e) => set({ q: e.target.value })} />
            <Button variant="secondary" onClick={() => setFiltersOpen(true)} aria-haspopup="dialog" aria-expanded={filtersOpen}>
              <Icon name="filter" />
              Фильтры{activeFilters ? ` · ${activeFilters}` : ''}
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-ink-soft" role="status">{list.data ? `Найдено: ${list.data.total}` : 'Загрузка платежей…'}</p>
            <Select className="payments-sort w-auto max-w-full text-sm" aria-label="Сортировка платежей" value={f.sort} onChange={(e) => set({ sort: e.target.value as Sort })}>
              {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </Select>
          </div>
        </div>

        {list.error ? (
          <div className="p-4"><ErrorNote text={list.error} onRetry={list.reload} /></div>
        ) : !list.data ? (
          <div className="space-y-4 border-t border-rule p-5" aria-label="Загрузка платежей" role="status">
            {[0, 1, 2, 3].map((key) => <Skeleton key={key} className="h-14 w-full" />)}
          </div>
        ) : list.data.items.length === 0 ? (
          <EmptyState title={f.tab === 'overdue' ? 'Просрочек нет' : f.tab === 'topay' ? 'Всё оплачено' : 'Ничего не найдено'} hint={hasExtraFilters ? 'Попробуйте сбросить фильтры' : 'Здесь появятся периоды регулярных платежей'} icon={<Icon name={f.tab === 'overdue' || f.tab === 'topay' ? 'check' : 'search'} />} />
        ) : (
          <>
            <ul className={`payments-cards divide-y divide-rule border-t border-rule ${list.loading ? 'opacity-60' : ''}`} aria-busy={list.loading}>
              {list.data.items.map((o) => (
                <li key={o.id} className="space-y-3 p-4">
                  <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1">
                    <span className="min-w-0 font-medium">{o.title}</span>
                    <span className={`num shrink-0 text-right whitespace-nowrap ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</span>
                  </div>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <StatusCell o={o} />
                    <span className="num whitespace-nowrap text-xs text-ink-soft">Срок {formatDate(o.due_date)}</span>
                  </div>
                  {o.recurring_payment_deleted && <p className="text-xs text-ink-soft">Регулярный платёж прекращён</p>}
                  <PaymentRowActions occurrence={o} busy={busy} placement="slip" onPaidToday={() => startMarkPaid(o, today)} onPickDate={() => setPaying(o)} onReceipt={() => setReceiptFor(o)} onUnpay={() => setPending({ kind: 'unpay', occurrence: o })} />
                </li>
              ))}
            </ul>
            <Table className={`payments-table w-full ${list.loading ? 'opacity-60' : ''}`} aria-busy={list.loading}>
              <thead>
                <tr>
                  <th aria-sort={ariaSort('title')}><button onClick={() => toggleSort('title')} className="whitespace-nowrap">Название{sortMark('title')}</button></th>
                  <th className="text-right whitespace-nowrap" aria-sort={ariaSort('amount')}><button onClick={() => toggleSort('amount')}>Сумма{sortMark('amount')}</button></th>
                  <th className="whitespace-nowrap" aria-sort={ariaSort('due_date')}><button onClick={() => toggleSort('due_date')}>Срок{sortMark('due_date')}</button></th>
                  <th className="whitespace-nowrap">Статус и оплата</th>
                  <th className="w-px whitespace-nowrap text-right"><span className="sr-only">Действия</span></th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((o) => (
                  <tr key={o.id}>
                    <td className="min-w-0">
                      <span className="font-medium">{o.title}</span>
                      {o.has_receipt && <Button variant="ghost" size="sm" className="ml-1 align-middle" onClick={() => setReceiptFor(o)} aria-label={`Открыть чек для «${o.title}»`} title="Открыть чек"><Icon name="receipt" /></Button>}
                      {o.recurring_payment_deleted && <span className="mt-1 block text-xs text-ink-soft">Платёж прекращён</span>}
                    </td>
                    <td className={`num text-right whitespace-nowrap ${amountHot(o) ? 'text-overdue' : ''}`}>{formatMoney(o.amount, o.currency)}</td>
                    <td className="num whitespace-nowrap text-xs">{formatDate(o.due_date)}</td>
                    <td><StatusCell o={o} /></td>
                    <td className="w-px whitespace-nowrap text-right"><PaymentRowActions occurrence={o} busy={busy} placement="table" onPaidToday={() => startMarkPaid(o, today)} onPickDate={() => setPaying(o)} onReceipt={() => setReceiptFor(o)} onUnpay={() => setPending({ kind: 'unpay', occurrence: o })} /></td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}

        {list.data && list.data.total > PAGE_SIZE && (
          <nav className="flex flex-wrap items-center justify-between gap-3 border-t border-rule p-4 text-sm" aria-label="Страницы платежей">
            <span className="text-xs text-ink-soft">Всего: <span className="num">{list.data.total}</span></span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Предыдущая страница"><Icon name="chevron-left" /></Button>
              <span className="num whitespace-nowrap text-xs">{page} / {pages}</span>
              <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Следующая страница"><Icon name="chevron-right" /></Button>
            </div>
          </nav>
        )}
      </Card>

      <Dialog open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Фильтры платежей">
        {filterControls('mobile')}
        <div className="mt-6 flex justify-end"><Button variant="primary" onClick={() => setFiltersOpen(false)}>Показать платежи</Button></div>
      </Dialog>

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
