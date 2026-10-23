import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../store/auth'

export function LoginPage() {
  const { me, login } = useAuth()
  const [form, setForm] = useState({ login: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (me) return <Navigate to="/" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(form.login.trim(), form.password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-sm">
        <p className="num text-xs uppercase tracking-[0.2em] text-ink-soft mb-1">Книга регулярных платежей</p>
        <h1 className="font-serif text-4xl font-bold mb-6">
          Invoice<span className="text-red">·</span>Keeper
        </h1>
        <form onSubmit={submit} className="sheet p-6 shadow-[4px_4px_0_var(--ink)]" noValidate>
          <div className="mb-4">
            <label className="label" htmlFor="login">
              Логин
            </label>
            <input
              id="login"
              className="field"
              autoComplete="username"
              autoFocus
              value={form.login}
              onChange={(e) => setForm({ ...form, login: e.target.value })}
              required
            />
          </div>
          <div className="mb-5">
            <label className="label" htmlFor="password">
              Пароль
            </label>
            <input
              id="password"
              type="password"
              className="field"
              autoComplete="current-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </div>
          {error && (
            <p className="text-sm text-red mb-4" role="alert">
              {error}
            </p>
          )}
          <button className="btn btn-primary w-full justify-center" disabled={busy || !form.login || !form.password}>
            {busy ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  )
}
