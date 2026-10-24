import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { api, ApiError, unwrap } from '../api/client'
import { Footer } from '../components/Footer'
import { Button, Input } from '../components/ui'
import { Icon } from '../components/Icon'
import { useAuth } from '../store/auth'

type Phase = 'form' | 'choices'

function WelcomeCopy() {
  return (
    <section
      aria-label="О сервисе"
      className="flex min-w-0 flex-col justify-between bg-[#182D48] p-6 text-white min-[900px]:p-10"
    >
      <div>
        <h2 className="max-w-md font-display text-3xl leading-tight font-semibold min-[1100px]:text-[2.5rem]">
          Команда знает,
          <br />
          что и когда оплатить
        </h2>
        <p className="mt-5 max-w-sm text-sm leading-relaxed text-white/75">
          Аренда, серверы и подписки в одном месте. История оплат сохраняется, а следующие сроки появляются
          автоматически.
        </p>
      </div>
      <div className="mt-8 divide-y divide-white/15 min-[900px]:mt-12">
        <article className="flex gap-4 py-5">
          <Icon name="calendar" className="mt-0.5 shrink-0 text-[#4CC6F1]" />
          <div>
            <h3 className="font-medium">Расходы на виду</h3>
            <p className="mt-1 text-sm leading-relaxed text-white/75">
              Календарь, бюджет и статусы платежей. Рубли, доллары и евро считаются отдельно.
            </p>
          </div>
        </article>
        <article className="flex gap-4 py-5">
          <Icon name="telegram" className="mt-0.5 shrink-0 text-[#4CC6F1]" />
          <div>
            <h3 className="font-medium">Напоминания за 3 дня</h3>
            <p className="mt-1 text-sm leading-relaxed text-white/75">
              Бот напишет в Telegram и даст отметить оплату прямо в чате.
            </p>
          </div>
        </article>
        <article className="flex gap-4 py-5">
          <Icon name="users" className="mt-0.5 shrink-0 text-[#4CC6F1]" />
          <div>
            <h3 className="font-medium">Одна картина для команды</h3>
            <p className="mt-1 text-sm leading-relaxed text-white/75">
              Создайте временную команду в Telegram, войдите по приглашению или привяжите свой аккаунт.
            </p>
          </div>
        </article>
      </div>
    </section>
  )
}

export function LoginPage() {
  const { me, login, adopt } = useAuth()
  const [phase, setPhase] = useState<Phase>('form')
  const [tgHref, setTgHref] = useState<string | null>(null)
  const [tgToken, setTgToken] = useState<boolean | null>(null)
  const [form, setForm] = useState({ login: '', password: '' })
  const [code, setCode] = useState('')
  const [link, setLink] = useState({ login: '', password: '' })
  const [panel, setPanel] = useState<'join' | 'link' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const pollGen = useRef(0)
  const polling = useRef(false)
  const timer = useRef<number | null>(null)
  const expiresAt = useRef(0)
  const tokenConfigured = useRef(false)

  const stopPoll = () => {
    pollGen.current += 1
    polling.current = false
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }

  const prepareLink = async (): Promise<string | null> => {
    if (!tokenConfigured.current) return null
    try {
      const link = unwrap(await api.POST('/api/v1/auth/telegram/deeplink'))
      expiresAt.current = new Date(link.expires_at).getTime()
      setTgHref(link.url)
      return link.url
    } catch {
      setTgHref(null)
      return null
    }
  }

  const startPoll = () => {
    if (polling.current) return
    polling.current = true
    const gen = ++pollGen.current
    setBusy('telegram')
    setError(null)
    const tick = async () => {
      if (pollGen.current !== gen) return
      try {
        const data = unwrap(await api.POST('/api/v1/auth/telegram/deeplink/status'))
        if (pollGen.current !== gen) return
        if (data.status === 'waiting') {
          timer.current = window.setTimeout(tick, 1500)
          return
        }
        polling.current = false
        setBusy(null)
        if (data.status === 'authenticated' && data.user) adopt(data.user)
        else {
          setPanel(null)
          setPhase('choices')
        }
      } catch (err) {
        if (pollGen.current !== gen) return
        polling.current = false
        setBusy(null)
        setError(err instanceof Error ? err.message : 'Не удалось войти через Telegram')
        void prepareLink()
      }
    }
    timer.current = window.setTimeout(tick, 1200)
  }

  useEffect(() => {
    let cancel = false
    api.GET('/api/v1/auth/telegram/config').then(async (r) => {
      const cfg = r.data
      const configured = Boolean(cfg?.token_configured)
      tokenConfigured.current = configured
      if (cancel) return
      setTgToken(configured)
      if (!cfg?.enabled) return
      try {
        const link = unwrap(await api.POST('/api/v1/auth/telegram/deeplink'))
        if (cancel) return
        expiresAt.current = new Date(link.expires_at).getTime()
        setTgHref(link.url)
      } catch {
        if (!cancel) setTgHref(null)
      }
    })
    api.GET('/api/v1/auth/telegram/pending').then((r) => {
      if (!cancel && r.data?.pending) setPhase('choices')
    })
    return () => {
      cancel = true
      stopPoll()
    }
  }, [])

  if (me) return <Navigate to="/" replace />

  const fail = (err: unknown) => {
    setError(err instanceof Error ? err.message : 'Не удалось войти')
    if (err instanceof ApiError && err.status === 401 && err.code !== 'invalid_credentials') setPhase('form')
  }

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault()
    stopPoll()
    setBusy('password')
    setError(null)
    try {
      await login(form.login.trim(), form.password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти')
    } finally {
      setBusy(null)
    }
  }

  const openTelegram = (e: MouseEvent<HTMLAnchorElement>) => {
    if (expiresAt.current && Date.now() > expiresAt.current - 3000) {
      e.preventDefault()
      void (async () => {
        const url = await prepareLink()
        if (!url) {
          setError('Не удалось подготовить вход через Telegram. Обновите страницу.')
          return
        }
        window.open(url, '_blank', 'noopener,noreferrer')
        startPoll()
      })()
      return
    }
    startPoll()
  }

  const telegramUnavailable = () => {
    if (tgToken === null) return
    if (!tgToken) setError('Вход через Telegram не настроен.')
    else setError('Не удалось подготовить вход через Telegram. Обновите страницу.')
  }

  const createTeam = async () => {
    setBusy('create')
    setError(null)
    try {
      adopt(unwrap(await api.POST('/api/v1/auth/telegram/sandbox')).user)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  const submitJoin = async (e: FormEvent) => {
    e.preventDefault()
    setBusy('join')
    setError(null)
    try {
      adopt(unwrap(await api.POST('/api/v1/auth/telegram/join', { body: { code: code.trim() } })).user)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  const submitLink = async (e: FormEvent) => {
    e.preventDefault()
    setBusy('link')
    setError(null)
    try {
      adopt(
        unwrap(
          await api.POST('/api/v1/auth/telegram/link', {
            body: { login: link.login.trim(), password: link.password },
          }),
        ).user,
      )
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  const cancelTelegram = async () => {
    setBusy('cancel')
    setError(null)
    try {
      await api.POST('/api/v1/auth/telegram/cancel')
      setPhase('form')
      setPanel(null)
      void prepareLink()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отменить вход')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex min-h-dvh min-w-0 flex-col bg-paper font-sans text-ink">
      <header className="mx-auto flex w-full max-w-[1160px] items-center justify-between px-5 py-6 min-[650px]:px-8">
        <span className="font-display text-xl font-semibold tracking-tight">Invoice Keeper</span>
        <span className="text-xs text-ink-soft">Aeza · 2026</span>
      </header>
      <main className="mx-auto flex w-full max-w-[1160px] flex-1 items-center px-4 pb-8 min-[650px]:px-8">
        <div className="grid w-full min-w-0 overflow-hidden rounded-xl border border-rule bg-paper-2 min-[900px]:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="min-w-0 px-5 py-7 min-[650px]:px-8 min-[650px]:py-10 min-[1100px]:px-10">
            {phase === 'choices' ? (
              <>
                <div className="mb-6 inline-flex items-center gap-2 text-sm text-ink-soft">
                  <Icon name="telegram" /> Telegram подключён
                </div>
                <h1 className="font-display text-2xl font-semibold leading-tight">Выберите команду</h1>
                <p className="mt-3 mb-6 text-sm leading-relaxed text-ink-soft">
                  Этот Telegram ещё не привязан. Создайте временную команду на <span className="num">24</span> часа,
                  войдите по приглашению или привяжите существующий аккаунт.
                </p>
                {error && (
                  <p
                    className="mb-4 rounded-lg border border-overdue/30 bg-overdue/5 p-3 text-sm text-overdue"
                    role="alert"
                  >
                    {error}
                  </p>
                )}
                {!panel && (
                  <div className="space-y-3">
                    <Button
                      type="button"
                      variant="primary"
                      className="w-full whitespace-normal"
                      disabled={busy !== null}
                      loading={busy === 'create'}
                      onClick={createTeam}
                    >
                      Создать временную команду
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      className="w-full whitespace-normal"
                      disabled={busy !== null}
                      onClick={() => {
                        setPanel('join')
                        setError(null)
                      }}
                    >
                      Войти по коду приглашения
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      className="w-full whitespace-normal"
                      disabled={busy !== null}
                      onClick={() => {
                        setPanel('link')
                        setError(null)
                      }}
                    >
                      Привязать существующий аккаунт
                    </Button>
                  </div>
                )}
                {panel === 'join' && (
                  <form onSubmit={submitJoin} noValidate>
                    <label className="label" htmlFor="invite">
                      Код приглашения
                    </label>
                    <Input
                      id="invite"
                      className="num"
                      autoComplete="off"
                      autoFocus
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      required
                    />
                    <div className="mt-5 flex gap-2">
                      <Button type="button" variant="secondary" disabled={busy !== null} onClick={() => setPanel(null)}>
                        Назад
                      </Button>
                      <Button
                        type="submit"
                        variant="primary"
                        className="flex-1"
                        disabled={busy !== null || !code.trim()}
                        loading={busy === 'join'}
                      >
                        Войти
                      </Button>
                    </div>
                  </form>
                )}
                {panel === 'link' && (
                  <form onSubmit={submitLink} noValidate>
                    <p className="mb-4 text-sm leading-relaxed text-ink-soft">
                      Введите логин и пароль существующей учётной записи. Новый администратор основной команды так не
                      создаётся.
                    </p>
                    <div className="mb-4">
                      <label className="label" htmlFor="link-login">
                        Логин
                      </label>
                      <Input
                        id="link-login"
                        autoComplete="username"
                        autoFocus
                        value={link.login}
                        onChange={(e) => setLink({ ...link, login: e.target.value })}
                        required
                      />
                    </div>
                    <div className="mb-5">
                      <label className="label" htmlFor="link-password">
                        Пароль
                      </label>
                      <Input
                        id="link-password"
                        type="password"
                        autoComplete="current-password"
                        value={link.password}
                        onChange={(e) => setLink({ ...link, password: e.target.value })}
                        required
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" variant="secondary" disabled={busy !== null} onClick={() => setPanel(null)}>
                        Назад
                      </Button>
                      <Button
                        type="submit"
                        variant="primary"
                        className="flex-1 whitespace-normal"
                        disabled={busy !== null || !link.login || !link.password}
                        loading={busy === 'link'}
                      >
                        Привязать и войти
                      </Button>
                    </div>
                  </form>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  className="mt-5 w-full whitespace-normal"
                  disabled={busy !== null}
                  loading={busy === 'cancel'}
                  onClick={cancelTelegram}
                >
                  Войти другим способом
                </Button>
              </>
            ) : (
              <>
                <h1 className="font-display text-3xl font-semibold">Вход в команду</h1>
                <p className="mt-3 mb-7 text-sm leading-relaxed text-ink-soft">
                  Введите данные аккаунта или продолжите через Telegram.
                </p>
                <form onSubmit={submitPassword} noValidate>
                  <div className="mb-4">
                    <label className="label" htmlFor="login">
                      Логин
                    </label>
                    <Input
                      id="login"
                      autoComplete="username"
                      autoFocus
                      placeholder="Ваш логин"
                      value={form.login}
                      onChange={(e) => setForm({ ...form, login: e.target.value })}
                      required
                    />
                  </div>
                  <div className="mb-5">
                    <label className="label" htmlFor="password">
                      Пароль
                    </label>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="current-password"
                      placeholder="Введите пароль"
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      required
                    />
                  </div>
                  {error && (
                    <p
                      className="mb-4 rounded-lg border border-overdue/30 bg-overdue/5 p-3 text-sm text-overdue"
                      role="alert"
                    >
                      {error}
                    </p>
                  )}
                  <Button
                    type="submit"
                    variant="primary"
                    className="w-full"
                    disabled={busy === 'password' || !form.login || !form.password}
                    loading={busy === 'password'}
                  >
                    Войти
                  </Button>
                </form>
                <div className="my-5 flex items-center gap-4 text-xs text-ink-soft">
                  <span className="h-px flex-1 bg-rule" />
                  <span>или</span>
                  <span className="h-px flex-1 bg-rule" />
                </div>
                {tgHref ? (
                  <a
                    className="btn btn-secondary w-full justify-center"
                    href={tgHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={openTelegram}
                  >
                    <Icon name="telegram" />
                    {busy === 'telegram' ? 'Ждём Telegram…' : 'Войти через Telegram'}
                  </a>
                ) : (
                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full"
                    disabled={tgToken === null || busy === 'password'}
                    onClick={telegramUnavailable}
                  >
                    <Icon name="telegram" /> Войти через Telegram
                  </Button>
                )}
                <p className="mt-3 text-xs leading-relaxed text-ink-soft">
                  {tgHref
                    ? 'Откроется Telegram: нажмите Start и вернитесь на эту страницу.'
                    : 'Регистрация и создание команды доступны через Telegram.'}
                </p>
              </>
            )}
          </div>
          <WelcomeCopy />
        </div>
      </main>
      <Footer />
    </div>
  )
}
