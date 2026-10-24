import { useMemo, useState } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import {
  Badge,
  Button,
  Card,
  DateInput,
  EmptyState,
  ErrorNote,
  Input,
  Loading,
  PageTitle,
  Select,
  Table,
} from '../components/ui'
import { Icon } from '../components/Icon'
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
const timeFmt = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

const FIELDS: Record<string, string> = {
  title: 'Название',
  amount: 'Сумма',
  currency: 'Валюта',
  due_date: 'Срок',
  paid_date: 'Дата оплаты',
  status: 'Статус',
  login: 'Логин',
  email: 'Email',
  telegram_user_id: 'Telegram ID',
  is_deleted: 'Прекращён',
  is_active: 'Активен',
  planned_amount: 'Бюджет',
  url: 'URL',
  recurrence: 'Периодичность',
}

function AuditValue({ value }: { value: unknown }) {
  if (value !== null && typeof value === 'object')
    return (
      <details>
        <summary className="cursor-pointer text-ink-soft">
          {Array.isArray(value) ? `Список (${value.length})` : 'Объект'}
        </summary>
        <pre className="mt-2 max-w-full whitespace-pre-wrap break-all rounded-lg bg-paper p-2 text-xs">
          {JSON.stringify(value, null, 2)}
        </pre>
      </details>
    )
  return <span className="break-all">{typeof value === 'boolean' ? (value ? 'Да' : 'Нет') : fmtVal(value)}</span>
}

function Changes({ e }: { e: Entry }) {
  const before = e.before ?? {}
  const after = e.after ?? {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  const rows = keys.filter((k) => k in before !== k in after || fmtVal(before[k]) !== fmtVal(after[k]) || !e.before)
  if (!rows.length && !e.before && !e.after) return <span className="text-ink-soft">—</span>
  const render = (k: string) => (
    <div key={k} className="border-l-2 border-accent pl-2.5">
      <dt className="mb-1 text-xs font-medium">{FIELDS[k] ?? k}</dt>
      <dd className="min-w-0 text-xs leading-relaxed">
        {e.before && k in before && (
          <div className="mb-1 text-ink-soft">
            <span className="mr-1.5">Было:</span>
            <AuditValue value={before[k]} />
          </div>
        )}
        <div>
          <span className="mr-1.5 text-ink-soft">{k in after ? 'Стало:' : 'Удалено'}</span>
          {k in after && <AuditValue value={after[k]} />}
        </div>
      </dd>
    </div>
  )
  return (
    <div className="min-w-0">
      <dl className="space-y-3">{rows.slice(0, 3).map(render)}</dl>
      {rows.length > 3 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer py-1 text-ink-soft">Ещё изменений: {rows.length - 3}</summary>
          <dl className="mt-3 space-y-3">{rows.slice(3).map(render)}</dl>
        </details>
      )}
      <details className="mt-3 text-xs text-ink-soft">
        <summary className="cursor-pointer py-1">Исходные данные JSON</summary>
        <div className="mt-2 space-y-3 rounded-lg bg-paper p-3">
          <div>
            <p className="mb-1 font-medium">До</p>
            <pre className="num max-w-full whitespace-pre-wrap break-all">{JSON.stringify(e.before, null, 2)}</pre>
          </div>
          <div>
            <p className="mb-1 font-medium">После</p>
            <pre className="num max-w-full whitespace-pre-wrap break-all">{JSON.stringify(e.after, null, 2)}</pre>
          </div>
        </div>
      </details>
    </div>
  )
}

function Action({ entry }: { entry: Entry }) {
  const failed = ['failed', 'dead', 'blocked'].some((word) => entry.action.includes(word))
  return (
    <div>
      <span className="text-sm font-medium">{ACTIONS[entry.action] ?? entry.action}</span>
      {failed && (
        <div className="mt-1.5">
          <Badge tone="overdue">Требует внимания</Badge>
        </div>
      )}
      <p className="num mt-1 whitespace-normal break-all text-xs text-ink-soft">{entry.action}</p>
    </div>
  )
}

export function AuditPage() {
  const [f, setF] = useState({ action: '', actor_login: '', from: '', to: '' })
  const [page, setPage] = useState(1)
  const [filterVersion, setFilterVersion] = useState(0)
  const query = useMemo(() => {
    const q: Record<string, string | number> = { page, page_size: PAGE_SIZE }
    Object.entries(f).forEach(([k, v]) => v && (q[k] = v))
    return q
  }, [f, page])
  const list = useLoad(
    async () => unwrap(await api.GET('/api/v1/audit-logs', { params: { query: query as never } })),
    [JSON.stringify(query)],
  )
  const set = (patch: Partial<typeof f>) => {
    setF((x) => ({ ...x, ...patch }))
    setPage(1)
  }
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageTitle>Журнал действий</PageTitle>
      <Card className="mb-5 p-4">
        <div className="grid grid-cols-1 items-end gap-3 min-[650px]:grid-cols-2 min-[1280px]:grid-cols-4">
          <div>
            <label className="label" htmlFor="a-act">
              Действие
            </label>
            <Select id="a-act" value={f.action} onChange={(e) => set({ action: e.target.value })}>
              {GROUPS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="label" htmlFor="a-who">
              Кто (логин)
            </label>
            <Input
              id="a-who"
              placeholder="Все пользователи"
              value={f.actor_login}
              onChange={(e) => set({ actor_login: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="a-from">
              С даты
            </label>
            <DateInput
              key={`from-${filterVersion}`}
              id="a-from"
              value={f.from}
              max={f.to || undefined}
              onChange={(value) => set({ from: value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="a-to">
              По дату
            </label>
            <DateInput
              key={`to-${filterVersion}`}
              id="a-to"
              value={f.to}
              min={f.from || undefined}
              onChange={(value) => set({ to: value })}
            />
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3"
          onClick={() => {
            set({ action: '', actor_login: '', from: '', to: '' })
            setFilterVersion((version) => version + 1)
          }}
        >
          <Icon name="close" /> Сбросить фильтры
        </Button>
      </Card>
      <Card className="min-w-0">
        {list.error ? (
          <div className="p-4">
            <ErrorNote text={list.error} onRetry={list.reload} />
          </div>
        ) : !list.data ? (
          <Loading />
        ) : !list.data.items.length ? (
          <EmptyState
            title="Записей нет"
            hint="Действия команды появятся здесь. Если выбраны фильтры, попробуйте их сбросить."
            icon={<Icon name="audit" />}
          />
        ) : (
          <>
            <ul className={`divide-y divide-rule min-[1280px]:hidden ${list.loading ? 'opacity-60' : ''}`}>
              {list.data.items.map((e) => (
                <li key={e.id} className="min-w-0 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <Action entry={e} />
                    <span className="num whitespace-nowrap text-xs text-ink-soft">
                      {timeFmt.format(new Date(e.at))}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm">
                    <span className="min-w-0 break-all">{e.actor_login ?? 'Система'}</span>
                    <span className="num whitespace-normal break-all text-xs text-ink-soft">{e.ip ?? '—'}</span>
                  </div>
                  <div className="mt-4">
                    <Changes e={e} />
                  </div>
                  {e.user_agent && (
                    <details className="mt-3 text-xs text-ink-soft">
                      <summary className="cursor-pointer py-1">Клиент</summary>
                      <p className="mt-2 break-all">{e.user_agent}</p>
                    </details>
                  )}
                </li>
              ))}
            </ul>
            <Table className={`hidden w-full table-fixed min-[1280px]:table ${list.loading ? 'opacity-60' : ''}`}>
              <colgroup>
                <col className="w-[17%]" />
                <col className="w-[12%]" />
                <col className="w-[21%]" />
                <col className="w-[36%]" />
                <col className="w-[14%]" />
              </colgroup>
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
                    <td className="num whitespace-nowrap text-[11px]">{timeFmt.format(new Date(e.at))}</td>
                    <td className="break-words text-sm">{e.actor_login ?? 'Система'}</td>
                    <td>
                      <Action entry={e} />
                    </td>
                    <td className="min-w-0">
                      <Changes e={e} />
                    </td>
                    <td className="text-xs text-ink-soft">
                      <span className="num whitespace-normal break-all">{e.ip ?? '—'}</span>
                      {e.user_agent && (
                        <details className="mt-2">
                          <summary className="cursor-pointer">Клиент</summary>
                          <p className="mt-2 break-all">{e.user_agent}</p>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Card>
      {list.data && list.data.total > PAGE_SIZE && (
        <nav className="mt-4 flex flex-wrap items-center justify-end gap-2 text-sm" aria-label="Страницы журнала">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <Icon name="chevron-left" /> Назад
          </Button>
          <span className="num px-2">
            {page} / {pages}
          </span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Вперёд <Icon name="chevron-right" />
          </Button>
        </nav>
      )}
    </>
  )
}
