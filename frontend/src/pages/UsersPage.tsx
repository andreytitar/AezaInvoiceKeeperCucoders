import { useState, type FormEvent } from 'react'
import { api, unwrap, type User } from '../api/client'
import { ConfirmDialog, Empty, ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { formatDate } from '../i18n/format'
import { useToast } from '../store/toast'

type Form = { login: string; password: string; email: string; telegram_user_id: string }
const EMPTY: Form = { login: '', password: '', email: '', telegram_user_id: '' }

export function UsersPage() {
  const toast = useToast()
  const list = useLoad(async () => unwrap(await api.GET('/api/v1/users')), [])
  const [editing, setEditing] = useState<User | null>(null)
  const [form, setForm] = useState<Form>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<User | null>(null)

  const startEdit = (u: User) => {
    setEditing(u)
    setError(null)
    setForm({ login: u.login, password: '', email: u.email ?? '', telegram_user_id: u.telegram_user_id ? String(u.telegram_user_id) : '' })
  }
  const cancelEdit = () => {
    setEditing(null)
    setForm(EMPTY)
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const tg = form.telegram_user_id.trim() ? Number(form.telegram_user_id.trim()) : null
    const email = form.email.trim() || null
    try {
      if (editing) {
        const body: Record<string, unknown> = { email, telegram_user_id: tg }
        if (form.login.trim() !== editing.login) body.login = form.login.trim()
        if (form.password) body.password = form.password
        unwrap(await api.PATCH('/api/v1/users/{user_id}', { params: { path: { user_id: editing.id } }, body }))
        toast('ok', form.password ? 'Сохранено, сессии пользователя завершены' : 'Сохранено')
        cancelEdit()
      } else {
        unwrap(
          await api.POST('/api/v1/users', {
            body: { login: form.login.trim(), password: form.password, email, telegram_user_id: tg },
          }),
        )
        toast('ok', `Пользователь ${form.login} создан`)
        setForm(EMPTY)
      }
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (u: User) => {
    setBusy(true)
    try {
      unwrap(await api.DELETE('/api/v1/users/{user_id}', { params: { path: { user_id: u.id } } }))
      toast('ok', `Пользователь ${u.login} удалён`)
      setDeleting(null)
      if (editing?.id === u.id) cancelEdit()
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageTitle>Пользователи</PageTitle>
      <div className="grid lg:grid-cols-[22rem_1fr] gap-6 items-start">
        <form onSubmit={submit} className="sheet p-5">
          <h2 className="font-serif text-lg font-bold mb-3">{editing ? `Изменить ${editing.login}` : 'Новый пользователь'}</h2>
          <label className="label" htmlFor="u-login">
            Логин
          </label>
          <input
            id="u-login"
            className="field mb-3"
            required
            minLength={3}
            maxLength={64}
            pattern="[A-Za-z0-9_.\-]+"
            title="Латиница, цифры, точка, дефис, подчёркивание"
            value={form.login}
            onChange={(e) => setForm({ ...form, login: e.target.value })}
          />
          <label className="label" htmlFor="u-pass">
            {editing ? 'Новый пароль (необязательно)' : 'Пароль'}
          </label>
          <input
            id="u-pass"
            type="password"
            className="field mb-3"
            autoComplete="new-password"
            required={!editing}
            minLength={6}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <label className="label" htmlFor="u-email">
            Email (необязательно)
          </label>
          <input id="u-email" type="email" className="field mb-3" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <label className="label" htmlFor="u-tg">
            Telegram user ID (необязательно)
          </label>
          <input
            id="u-tg"
            className="field num mb-1"
            inputMode="numeric"
            pattern="\d*"
            value={form.telegram_user_id}
            onChange={(e) => setForm({ ...form, telegram_user_id: e.target.value })}
          />
          <p className="text-xs text-ink-soft mb-4">Нужен, чтобы отмечать оплату кнопкой в Telegram. Узнать id: бот @userinfobot.</p>
          {error && (
            <p className="text-sm text-red mb-3" role="alert">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <button className="btn btn-primary flex-1 justify-center" disabled={busy}>
              {editing ? 'Сохранить' : 'Создать'}
            </button>
            {editing && (
              <button type="button" className="btn" onClick={cancelEdit}>
                Отмена
              </button>
            )}
          </div>
        </form>

        <div className="sheet overflow-x-auto">
          {list.error ? (
            <div className="p-4">
              <ErrorNote text={list.error} onRetry={list.reload} />
            </div>
          ) : !list.data ? (
            <Loading />
          ) : list.data.length === 0 ? (
            <Empty title="Пользователей нет" hint="Администратор из .env здесь не показывается" />
          ) : (
            <table className="ledger w-full min-w-[560px]">
              <thead>
                <tr>
                  <th>Логин</th>
                  <th>Email</th>
                  <th>Telegram</th>
                  <th>Создан</th>
                  <th className="text-right">
                    <span className="sr-only">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.map((u) => (
                  <tr key={u.id}>
                    <td className="font-semibold">{u.login}</td>
                    <td className="text-sm">{u.email ?? '—'}</td>
                    <td className="num text-sm">{u.telegram_user_id ?? '—'}</td>
                    <td className="num text-sm">{formatDate(u.created_at.slice(0, 10))}</td>
                    <td className="text-right whitespace-nowrap">
                      <span className="inline-flex gap-1">
                        <button className="btn btn-sm" onClick={() => startEdit(u)}>
                          Изменить
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => setDeleting(u)}>
                          Удалить
                        </button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={!!deleting}
        title="Удалить пользователя?"
        body={deleting && `${deleting.login} потеряет доступ, все его сессии будут завершены.`}
        confirmText="Удалить"
        danger
        busy={busy}
        onConfirm={() => deleting && remove(deleting)}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}
