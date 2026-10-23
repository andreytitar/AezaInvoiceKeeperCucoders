import { useMemo, useState } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { Empty, ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'

type Entry = Schemas['AuditLogOut']

const ACTIONS: Record<string, string> = {
  'auth.login': 'Вход',
  'auth.login_failed': 'Неудачный вход',
  'auth.login_blocked': 'Вход заблокирован (лимит)',
  'auth.logout': 'Выход',
  'payment.create': 'Платёж создан',
  'payment.delete': 'Платёж прекращён',
  'occurrence.paid': 'Отмечена оплата',
  'occurrence.unpaid': 'Оплата отменена',
  'occurrence.paid_date_changed': 'Исправлена дата оплаты',
  'user.create': 'Пользователь создан',
  'user.update': 'Пользователь изменён',
  'user.delete': 'Пользователь удалён',
  'notification.sent': 'Уведомление отправлено',
  'notification.dead': 'Уведомление не доставлено',
}
const GROUPS = [
  { value: '', label: 'Все действия' },
  { value: 'auth.', label: 'Вход и выход' },
  { value: 'payment.', label: 'Регулярные платежи' },
  { value: 'occurrence.', label: 'Оплаты' },
  { value: 'user.', label: 'Пользователи' },
  { value: 'notification.', label: 'Уведомления' },
  { value: 'receipt.', label: 'Чеки' },
  { value: 'budget.', label: 'Бюджеты' },
  { value: 'webhook.', label: 'Вебхуки' },
]
const PAGE_SIZE = 50
const timeFmt = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function Changes({ e }: { e: Entry }) {
  const before = e.before ?? {}
  const after = e.after ?? {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  const rows = keys.filter((k) => fmtVal(before[k]) !== fmtVal(after[k]) || !e.before)
  if (!rows.length) return <span className="text-ink-soft">—</span>
  return (
    <dl className="text-xs num grid grid-cols-[auto_1fr] gap-x-2">
      {rows.slice(0, 6).map((k) => (
        <div key={k} className="contents">
          <dt className="text-ink-soft">{k}</dt>
          <dd className="break-all">
            {e.before && k in before && <span className="line-through text-ink-soft mr-1">{fmtVal(before[k])}</span>}
            {k in after ? fmtVal(after[k]) : ''}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function AuditPage() {
  const [f, setF] = useState({ action: '', actor_login: '', from: '', to: '' })
  const [page, setPage] = useState(1)
  const query = useMemo(() => {
    const q: Record<string, string | number> = { page, page_size: PAGE_SIZE }
    Object.entries(f).forEach(([k, v]) => v && (q[k] = v))
    return q
  }, [f, page])
  const list = useLoad(async () => unwrap(await api.GET('/api/v1/audit-logs', { params: { query: query as never } })), [JSON.stringify(query)])
  const set = (patch: Partial<typeof f>) => {
    setF((x) => ({ ...x, ...patch }))
    setPage(1)
  }
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageTitle>Журнал действий</PageTitle>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 items-end">
        <div>
          <label className="label" htmlFor="a-act">Действие</label>
          <select id="a-act" className="field" value={f.action} onChange={(e) => set({ action: e.target.value })}>
            {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="a-who">Кто (логин)</label>
          <input id="a-who" className="field" value={f.actor_login} onChange={(e) => set({ actor_login: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="a-from">С</label>
          <input id="a-from" type="date" className="field num" value={f.from} onChange={(e) => set({ from: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="a-to">По</label>
          <input id="a-to" type="date" className="field num" value={f.to} onChange={(e) => set({ to: e.target.value })} />
        </div>
      </div>
      <div className="sheet overflow-x-auto">
        {list.error ? (
          <div className="p-4"><ErrorNote text={list.error} onRetry={list.reload} /></div>
        ) : !list.data ? (
          <Loading />
        ) : list.data.items.length === 0 ? (
          <Empty title="Записей нет" />
        ) : (
          <table className={`ledger w-full min-w-[820px] ${list.loading ? 'opacity-60' : ''}`}>
            <thead>
              <tr>
                <th>Время</th>
                <th>Кто</th>
                <th>Действие</th>
                <th>Изменения</th>
                <th>IP / клиент</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="num text-xs whitespace-nowrap">{timeFmt.format(new Date(e.at))}</td>
                  <td className="text-sm">{e.actor_login ?? '—'}</td>
                  <td className="text-sm">
                    <span className={e.action.includes('failed') || e.action.includes('dead') || e.action.includes('blocked') ? 'text-red font-semibold' : ''}>
                      {ACTIONS[e.action] ?? e.action}
                    </span>
                    <span className="block text-xs text-ink-soft num">{e.action}</span>
                  </td>
                  <td className="max-w-[22rem]"><Changes e={e} /></td>
                  <td className="text-xs text-ink-soft">
                    <span className="num">{e.ip ?? '—'}</span>
                    {e.user_agent && <span className="block truncate max-w-[12rem]" title={e.user_agent}>{e.user_agent}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {list.data && list.data.total > PAGE_SIZE && (
        <nav className="flex justify-end items-center gap-2 mt-3 text-sm" aria-label="Страницы">
          <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Назад</button>
          <span className="num">{page} / {pages}</span>
          <button className="btn btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Вперёд →</button>
        </nav>
      )}
    </>
  )
}
