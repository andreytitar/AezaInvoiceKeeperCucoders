import { useState, type FormEvent } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { ConfirmDialog, Empty, ErrorNote, Loading, PageTitle } from '../components/ui'
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
const STATUS: Record<string, string> = { pending: 'в очереди', sending: 'отправляется', sent: 'доставлено', failed: 'ошибка, повтор', dead: 'не доставлено', cancelled: 'отменено' }
const timeFmt = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })

function Deliveries({ hook }: { hook: Hook }) {
  const list = useLoad(async () => unwrap(await api.GET('/api/v1/webhooks/{webhook_id}/deliveries', { params: { path: { webhook_id: hook.id }, query: { page_size: 20 } } })), [hook.id])
  if (list.error) return <ErrorNote text={list.error} />
  if (!list.data) return <Loading />
  if (!list.data.items.length) return <p className="text-sm text-ink-soft py-3">Доставок пока не было.</p>
  return (
    <table className="ledger w-full text-sm">
      <thead>
        <tr><th>Создано</th><th>Событие</th><th>Статус</th><th>Попытки</th><th>Ответ / ошибка</th></tr>
      </thead>
      <tbody>
        {list.data.items.map((d) => (
          <tr key={d.id}>
            <td className="num text-xs">{timeFmt.format(new Date(d.created_at))}</td>
            <td className="num text-xs">{d.event}</td>
            <td className={d.status === 'dead' || d.status === 'failed' ? 'text-red' : d.status === 'sent' ? 'text-green' : ''}>{STATUS[d.status] ?? d.status}</td>
            <td className="num">{d.attempts}</td>
            <td className="text-xs break-all">{d.last_error ?? d.response ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
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

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      unwrap(await api.POST('/api/v1/webhooks', { body: { url: form.url.trim(), events: form.events, secret: form.secret || null, description: form.description || null, is_active: true } }))
      toast('ok', 'Вебхук добавлен')
      setForm({ ...form, url: '', secret: '', description: '' })
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }
  const toggle = async (h: Hook) => {
    try {
      unwrap(await api.PATCH('/api/v1/webhooks/{webhook_id}', { params: { path: { webhook_id: h.id } }, body: { is_active: !h.is_active } }))
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    }
  }
  const test = async (h: Hook) => {
    try {
      const r = unwrap(await api.POST('/api/v1/webhooks/{webhook_id}/test', { params: { path: { webhook_id: h.id } } }))
      toast(r.ok ? 'ok' : 'error', r.ok ? `Тест доставлен: ${r.detail}` : `Тест не прошёл: ${r.detail}`)
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
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
      <PageTitle>Вебхуки</PageTitle>
      <div className="grid lg:grid-cols-[22rem_1fr] gap-6 items-start">
        <form onSubmit={create} className="sheet p-5">
          <h2 className="font-serif text-lg font-bold mb-3">Новый адрес</h2>
          <label className="label" htmlFor="w-url">URL</label>
          <input id="w-url" type="url" required className="field mb-3" placeholder="https://example.com/hook" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
          <fieldset className="mb-3">
            <legend className="label">События</legend>
            {EVENTS.map((ev) => (
              <label key={ev.id} className="flex items-center gap-2 text-sm py-0.5">
                <input
                  type="checkbox"
                  checked={form.events.includes(ev.id)}
                  onChange={(e) => setForm({ ...form, events: e.target.checked ? [...form.events, ev.id] : form.events.filter((x) => x !== ev.id) })}
                />
                {ev.label} <span className="num text-xs text-ink-soft">{ev.id}</span>
              </label>
            ))}
          </fieldset>
          <label className="label" htmlFor="w-secret">Секрет для подписи (необязательно)</label>
          <input id="w-secret" type="password" autoComplete="new-password" minLength={8} className="field mb-3" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} />
          <label className="label" htmlFor="w-desc">Описание</label>
          <input id="w-desc" className="field mb-4" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          {error && <p className="text-sm text-red mb-3" role="alert">{error}</p>}
          <button className="btn btn-primary w-full justify-center" disabled={busy || !form.events.length}>Добавить</button>
          <p className="text-xs text-ink-soft mt-3">
            Подпись: <span className="num">X-InvoiceKeeper-Signature: sha256=HMAC(secret, timestamp + "." + body)</span>. Внутренние адреса запрещены, пока WEBHOOK_ALLOW_PRIVATE=false.
          </p>
        </form>

        <div className="space-y-3">
          {list.error ? (
            <ErrorNote text={list.error} onRetry={list.reload} />
          ) : !list.data ? (
            <Loading />
          ) : !list.data.length ? (
            <div className="sheet"><Empty title="Вебхуков нет" hint="Добавьте адрес слева" /></div>
          ) : (
            list.data.map((h) => (
              <section key={h.id} className="sheet p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="num text-sm break-all font-semibold">{h.url}</p>
                    {h.description && <p className="text-sm text-ink-soft">{h.description}</p>}
                    <p className="text-xs text-ink-soft mt-1 num">
                      {h.events.join(' · ')} · {h.has_secret ? 'подписывается' : 'без подписи'} · {h.is_active ? 'активен' : 'выключен'}
                    </p>
                  </div>
                  <div className="flex gap-1 flex-wrap">
                    <button className="btn btn-sm" onClick={() => test(h)}>Тест</button>
                    <button className="btn btn-sm" onClick={() => toggle(h)}>{h.is_active ? 'Выключить' : 'Включить'}</button>
                    <button className="btn btn-sm" onClick={() => setOpen(open === h.id ? null : h.id)} aria-expanded={open === h.id}>Журнал</button>
                    <button className="btn btn-sm btn-danger" onClick={() => setDeleting(h)}>Удалить</button>
                  </div>
                </div>
                {open === h.id && <div className="mt-3 overflow-x-auto"><Deliveries hook={h} /></div>}
              </section>
            ))
          )}
        </div>
      </div>
      <ConfirmDialog open={!!deleting} title="Удалить вебхук?" body={deleting?.url} confirmText="Удалить" danger busy={busy} onConfirm={() => deleting && remove(deleting)} onClose={() => setDeleting(null)} />
    </>
  )
}
