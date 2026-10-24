import { useState, type FormEvent } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorNote,
  Input,
  Loading,
  Menu,
  MenuItem,
  PageTitle,
  Table,
} from '../components/ui'
import { Icon } from '../components/Icon'
import { useLoad } from '../hooks/useLoad'
import { useToast } from '../store/toast'

type Hook = Schemas['WebhookOut']
type Ev = 'payment.reminder' | 'payment.paid' | 'payment.unpaid' | 'payment.overdue'
const EVENTS: { id: Ev; label: string }[] = [
  { id: 'payment.reminder', label: 'Напоминание' },
  { id: 'payment.paid', label: 'Оплачено' },
  { id: 'payment.unpaid', label: 'Оплата отменена' },
  { id: 'payment.overdue', label: 'Просрочено' },
]
const STATUS: Record<string, string> = {
  pending: 'в очереди',
  sending: 'отправляется',
  sent: 'доставлено',
  failed: 'ошибка, повтор',
  dead: 'не доставлено',
  cancelled: 'отменено',
}
const timeFmt = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function Deliveries({ hook }: { hook: Hook }) {
  const list = useLoad(
    async () =>
      unwrap(
        await api.GET('/api/v1/webhooks/{webhook_id}/deliveries', {
          params: { path: { webhook_id: hook.id }, query: { page_size: 20 } },
        }),
      ),
    [hook.id],
  )
  if (list.error) return <ErrorNote text={list.error} />
  if (!list.data) return <Loading />
  if (!list.data.items.length)
    return <EmptyState title="Доставок пока не было" hint="Отправьте тест, чтобы проверить подключение." />
  const tone = (status: string) =>
    status === 'sent' ? 'paid' : status === 'failed' || status === 'dead' ? 'overdue' : 'neutral'
  return (
    <>
      <ul className="divide-y divide-rule min-[1100px]:hidden">
        {list.data.items.map((d) => (
          <li key={d.id} className="min-w-0 py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone={tone(d.status)}>{STATUS[d.status] ?? d.status}</Badge>
              <span className="num whitespace-nowrap text-xs text-ink-soft">
                {timeFmt.format(new Date(d.created_at))}
              </span>
            </div>
            <p className="num mt-3 whitespace-normal break-all text-xs">{d.event}</p>
            <p className="mt-1 text-xs text-ink-soft">
              Попыток: <span className="num">{d.attempts}</span>
            </p>
            <p className="mt-2 break-all text-xs">{d.last_error ?? d.response ?? '—'}</p>
          </li>
        ))}
      </ul>
      <Table className="hidden w-full text-sm min-[1100px]:table">
        <thead>
          <tr>
            <th>Создано</th>
            <th>Событие</th>
            <th>Статус</th>
            <th>Попытки</th>
            <th>Ответ / ошибка</th>
          </tr>
        </thead>
        <tbody>
          {list.data.items.map((d) => (
            <tr key={d.id}>
              <td className="num whitespace-nowrap text-xs">{timeFmt.format(new Date(d.created_at))}</td>
              <td className="num whitespace-normal break-all text-xs">{d.event}</td>
              <td>
                <Badge tone={tone(d.status)}>{STATUS[d.status] ?? d.status}</Badge>
              </td>
              <td className="num text-center">{d.attempts}</td>
              <td className="max-w-64 break-all text-xs">{d.last_error ?? d.response ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  )
}

export function WebhooksPage() {
  const toast = useToast()
  const list = useLoad(async () => unwrap(await api.GET('/api/v1/webhooks')), [])
  const [form, setForm] = useState({ url: '', secret: '', description: '', events: EVENTS.map((e) => e.id) as Ev[] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<Hook | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [actionBusy, setActionBusy] = useState<string | null>(null)

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      unwrap(
        await api.POST('/api/v1/webhooks', {
          body: {
            url: form.url.trim(),
            events: form.events,
            secret: form.secret || null,
            description: form.description || null,
            is_active: true,
          },
        }),
      )
      toast('ok', 'Вебхук добавлен')
      setFormOpen(false)
      setForm({ ...form, url: '', secret: '', description: '' })
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }
  const toggle = async (h: Hook) => {
    setActionBusy(h.id)
    try {
      unwrap(
        await api.PATCH('/api/v1/webhooks/{webhook_id}', {
          params: { path: { webhook_id: h.id } },
          body: { is_active: !h.is_active },
        }),
      )
      toast('ok', h.is_active ? 'Вебхук выключен' : 'Вебхук включён')
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setActionBusy(null)
    }
  }
  const test = async (h: Hook) => {
    setActionBusy(h.id)
    try {
      const r = unwrap(await api.POST('/api/v1/webhooks/{webhook_id}/test', { params: { path: { webhook_id: h.id } } }))
      toast(r.ok ? 'ok' : 'error', r.ok ? `Тест доставлен: ${r.detail}` : `Тест не прошёл: ${r.detail}`)
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setActionBusy(null)
    }
  }
  const remove = async (h: Hook) => {
    setBusy(true)
    try {
      unwrap(await api.DELETE('/api/v1/webhooks/{webhook_id}', { params: { path: { webhook_id: h.id } } }))
      toast('ok', 'Вебхук удалён')
      setDeleting(null)
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageTitle
        aside={
          <Button
            variant="primary"
            onClick={() => {
              setError(null)
              setFormOpen(true)
            }}
          >
            <Icon name="plus" /> Новый вебхук
          </Button>
        }
      >
        Вебхуки
      </PageTitle>
      <p className="mb-5 max-w-2xl text-sm text-ink-soft">
        Отправляйте события об оплатах и напоминаниях в свои сервисы.
      </p>
      <div className="space-y-4">
        {list.error ? (
          <ErrorNote text={list.error} onRetry={list.reload} />
        ) : !list.data ? (
          <Loading />
        ) : !list.data.length ? (
          <Card>
            <EmptyState
              title="Вебхуков пока нет"
              hint="Добавьте адрес сервиса, который будет получать события."
              icon={<Icon name="webhook" />}
            />
          </Card>
        ) : (
          list.data.map((h) => (
            <Card key={h.id} className="min-w-0 p-4 min-[650px]:p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="num whitespace-normal break-all text-sm font-medium">{h.url}</p>
                  {h.description && <p className="mt-2 break-words text-sm text-ink-soft">{h.description}</p>}
                </div>
                <Menu label={`Действия с вебхуком ${h.url}`}>
                  <MenuItem onClick={() => test(h)} disabled={actionBusy === h.id}>
                    <Icon name="check" /> Отправить тест
                  </MenuItem>
                  <MenuItem onClick={() => toggle(h)} disabled={actionBusy === h.id}>
                    {h.is_active ? 'Выключить' : 'Включить'}
                  </MenuItem>
                  <MenuItem onClick={() => setOpen(open === h.id ? null : h.id)}>
                    <Icon name="audit" /> {open === h.id ? 'Скрыть журнал' : 'Журнал доставок'}
                  </MenuItem>
                  <MenuItem danger onClick={() => setDeleting(h)}>
                    <Icon name="trash" /> Удалить
                  </MenuItem>
                </Menu>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge tone={h.is_active ? 'paid' : 'neutral'}>{h.is_active ? 'Активен' : 'Выключен'}</Badge>
                <span className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
                  <Icon name="shield" />
                  {h.has_secret ? 'С подписью' : 'Без подписи'}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-ink-soft">
                {h.events.map((ev) => (
                  <span key={ev}>{EVENTS.find((item) => item.id === ev)?.label ?? ev}</span>
                ))}
              </div>
              <div className="mt-4 border-t border-rule pt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setOpen(open === h.id ? null : h.id)}
                  aria-expanded={open === h.id}
                >
                  <Icon name="audit" /> {open === h.id ? 'Скрыть журнал' : 'Журнал доставок'}
                </Button>
                {actionBusy === h.id && (
                  <span className="ml-3 text-xs text-ink-soft" role="status">
                    Отправляем запрос…
                  </span>
                )}
              </div>
              {open === h.id && (
                <div className="mt-3 min-w-0 border-t border-rule pt-2">
                  <Deliveries hook={h} />
                </div>
              )}
            </Card>
          ))
        )}
      </div>
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} title="Новый вебхук">
        <form onSubmit={create} className="space-y-4">
          <div>
            <label className="label" htmlFor="w-url">
              URL
            </label>
            <Input
              id="w-url"
              type="url"
              required
              placeholder="https://example.com/hook"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
          </div>
          <fieldset>
            <legend className="label">События</legend>
            <div className="space-y-1">
              {EVENTS.map((ev) => (
                <label key={ev.id} className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={form.events.includes(ev.id)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        events: e.target.checked ? [...form.events, ev.id] : form.events.filter((x) => x !== ev.id),
                      })
                    }
                  />
                  <span>{ev.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label className="label" htmlFor="w-secret">
              Секрет для подписи (необязательно)
            </label>
            <Input
              id="w-secret"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={form.secret}
              onChange={(e) => setForm({ ...form, secret: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="w-desc">
              Описание
            </label>
            <Input
              id="w-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <details className="text-xs text-ink-soft">
            <summary className="cursor-pointer py-2">Подпись и ограничения адреса</summary>
            <p className="mt-1 break-all leading-relaxed">
              Подпись:{' '}
              <span className="num whitespace-normal break-all">
                X-InvoiceKeeper-Signature: sha256=HMAC(secret, timestamp + "." + body)
              </span>
              . Внутренние адреса запрещены, пока WEBHOOK_ALLOW_PRIVATE=false.
            </p>
          </details>
          {error && (
            <p className="text-sm text-overdue" role="alert">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setFormOpen(false)} disabled={busy}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!form.events.length}>
              Добавить вебхук
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        title="Удалить вебхук?"
        body={deleting?.url}
        confirmText="Удалить"
        danger
        busy={busy}
        onConfirm={() => deleting && remove(deleting)}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}
