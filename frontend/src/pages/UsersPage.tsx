import { useState, type FormEvent } from 'react'
import { api, unwrap, type User } from '../api/client'
import {
  Badge,
  Button,
  Card,
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
  const [formOpen, setFormOpen] = useState(false)

  const startEdit = (u: User) => {
    setEditing(u)
    setFormOpen(true)
    setError(null)
    setForm({
      login: u.login,
      password: '',
      email: u.email ?? '',
      telegram_user_id: u.telegram_user_id ? String(u.telegram_user_id) : '',
    })
  }
  const cancelEdit = () => {
    setEditing(null)
    setFormOpen(false)
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
        setFormOpen(false)
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

  const actions = (u: User) => (
    <Menu label={`Действия: ${u.login}`}>
      <MenuItem onClick={() => startEdit(u)}>
        <Icon name="edit" /> Изменить
      </MenuItem>
      <MenuItem danger onClick={() => setDeleting(u)}>
        <Icon name="trash" /> Удалить
      </MenuItem>
    </Menu>
  )

  return (
    <>
      <PageTitle
        aside={
          <Button
            variant="primary"
            onClick={() => {
              cancelEdit()
              setFormOpen(true)
            }}
          >
            <Icon name="plus" /> Новый пользователь
          </Button>
        }
      >
        Пользователи
      </PageTitle>
      <p className="mb-5 text-sm text-ink-soft">
        Доступ к платежам команды. Администратор из настроек сервера в списке не отображается.
      </p>
      <Card className="min-w-0">
        {list.error ? (
          <div className="p-4">
            <ErrorNote text={list.error} onRetry={list.reload} />
          </div>
        ) : !list.data ? (
          <Loading />
        ) : !list.data.length ? (
          <EmptyState
            title="Пользователей пока нет"
            hint="Создайте учётную запись для участника команды."
            icon={<Icon name="users" />}
          />
        ) : (
          <>
            <ul className="divide-y divide-rule min-[1100px]:hidden">
              {list.data.map((u) => (
                <li key={u.id} className="min-w-0 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="break-words font-semibold">{u.login}</p>
                      <div className="mt-2">
                        <Badge tone={u.role === 'admin' ? 'accent' : 'neutral'}>
                          {u.role === 'admin' ? 'Администратор' : 'Пользователь'}
                        </Badge>
                      </div>
                    </div>
                    {actions(u)}
                  </div>
                  <dl className="mt-4 space-y-2 text-sm">
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt className="text-ink-soft">Email</dt>
                      <dd className="min-w-0 break-all">{u.email ?? '—'}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt className="text-ink-soft">Telegram ID</dt>
                      <dd className="num whitespace-nowrap">{u.telegram_user_id ?? '—'}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt className="text-ink-soft">Создан</dt>
                      <dd className="num whitespace-nowrap">{formatDate(u.created_at.slice(0, 10))}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
            <Table className="hidden w-full min-[1100px]:table">
              <thead>
                <tr>
                  <th>Пользователь</th>
                  <th>Email</th>
                  <th>Telegram ID</th>
                  <th>Создан</th>
                  <th>
                    <span className="sr-only">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <p className="font-semibold [overflow-wrap:anywhere]">{u.login}</p>
                      <div className="mt-1.5">
                        <Badge tone={u.role === 'admin' ? 'accent' : 'neutral'}>
                          {u.role === 'admin' ? 'Администратор' : 'Пользователь'}
                        </Badge>
                      </div>
                    </td>
                    <td className="max-w-56 break-all text-sm">{u.email ?? '—'}</td>
                    <td className="num whitespace-nowrap text-sm">{u.telegram_user_id ?? '—'}</td>
                    <td className="num whitespace-nowrap text-sm">{formatDate(u.created_at.slice(0, 10))}</td>
                    <td className="text-right">{actions(u)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Card>
      <Dialog open={formOpen} onClose={cancelEdit} title={editing ? `Изменить ${editing.login}` : 'Новый пользователь'}>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label" htmlFor="u-login">
              Логин
            </label>
            <Input
              id="u-login"
              required
              minLength={3}
              maxLength={64}
              pattern="[A-Za-z0-9_.\-]+"
              title="Латиница, цифры, точка, дефис, подчёркивание"
              value={form.login}
              onChange={(e) => setForm({ ...form, login: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="u-pass">
              {editing ? 'Новый пароль (необязательно)' : 'Пароль'}
            </label>
            <Input
              id="u-pass"
              type="password"
              autoComplete="new-password"
              required={!editing}
              minLength={6}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            {editing && <p className="mt-2 text-xs text-ink-soft">Смена пароля завершит все сессии пользователя.</p>}
          </div>
          <div>
            <label className="label" htmlFor="u-email">
              Email (необязательно)
            </label>
            <Input
              id="u-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="u-tg">
              Telegram user ID (необязательно)
            </label>
            <Input
              id="u-tg"
              className="num"
              inputMode="numeric"
              pattern="\d*"
              value={form.telegram_user_id}
              onChange={(e) => setForm({ ...form, telegram_user_id: e.target.value })}
            />
            <p className="mt-2 text-xs leading-relaxed text-ink-soft">
              Для отметки оплаты в Telegram. Узнать ID можно у бота @userinfobot.
            </p>
          </div>
          {error && (
            <p className="text-sm text-overdue" role="alert">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={cancelEdit} disabled={busy}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" loading={busy}>
              {editing ? 'Сохранить' : 'Создать пользователя'}
            </Button>
          </div>
        </form>
      </Dialog>
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
