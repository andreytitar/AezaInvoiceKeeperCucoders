import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { api, ApiError, unwrap } from '../api/client'
import { Footer } from '../components/Footer'
import { useAuth } from '../store/auth'

type Phase = 'form' | 'choices'

const winBtn =
  'win-btn inline-flex min-h-11 w-full cursor-pointer items-center justify-center whitespace-normal px-3 text-center disabled:cursor-not-allowed disabled:opacity-45'
const winBtnHalf =
  'win-btn inline-flex min-h-11 min-w-0 flex-1 cursor-pointer items-center justify-center whitespace-normal px-3 text-center disabled:cursor-not-allowed disabled:opacity-45'

function WelcomeCopy() {
  return (
    <section
      aria-label="О сервисе"
      className="login-copy flex min-w-0 flex-1 flex-col px-4 py-8 text-ink min-[720px]:h-full min-[720px]:px-10 min-[720px]:pt-10 min-[720px]:pb-8"
    >
      <p className="font-sans text-[0.7rem] font-semibold tracking-[0.18em] uppercase">Что внутри</p>
      <h2 className="mt-3 max-w-[40rem] font-sans text-[1.45rem] leading-snug font-semibold break-words text-ink min-[720px]:text-[1.75rem]">
        Хранит регулярные платежи команды и показывает, что оплатить, что уже оплачено и что просрочено.
      </h2>
      <div className="sum-line mt-8 flex flex-1 flex-col border-t border-ink">
        <article className="flex flex-1 flex-col justify-center gap-2 border-b border-rule py-5">
          <h3 className="flex items-baseline gap-2 font-sans text-lg font-semibold">
            <span className="num text-[2.5rem] leading-none font-medium">3</span>
            дня
          </h3>
          <p className="max-w-[40rem] font-sans text-base leading-snug break-words">
            Напоминание уходит в Telegram-чат, когда до срока осталось не больше трёх дней. В сообщении — название, сумма, валюта и дата. Оплаченный период не напоминает.
          </p>
        </article>
        <article className="flex flex-1 flex-col justify-center gap-3 border-b border-rule py-5">
          <h3 className="sr-only">Три валюты</h3>
          <p className="num flex justify-between gap-3 text-lg tracking-[0.14em] break-words">
            <span>RUB</span>
            <span>USD</span>
            <span>EUR</span>
          </p>
          <p className="max-w-[40rem] font-sans text-base leading-snug break-words">
            Три валюты считаются отдельно. Конвертации и общего итога нет.
          </p>
        </article>
        <article className="flex flex-1 flex-col justify-center gap-2 py-5">
          <h3 className="font-sans text-lg font-semibold">Команда из Telegram</h3>
          <p className="max-w-[40rem] font-sans text-base leading-snug break-words">
            Команду можно создать из Telegram: временную, по коду приглашения или с привязкой уже существующего аккаунта.
          </p>
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
    <div className="box-border flex h-dvh w-full min-w-0 flex-col overflow-x-hidden overflow-y-auto bg-paper px-2 py-2 font-sans text-ink min-[720px]:px-6 min-[720px]:py-6">
      <div className="win-window flex w-full min-w-0 max-w-full flex-col min-[720px]:mx-auto min-[720px]:max-w-6xl">
        <div className="win-titlebar font-serif" role="heading" aria-level={1}>
          Invoice Keeper
        </div>
        <div className="flex w-full min-w-0 flex-col min-[720px]:grid min-[720px]:grid-cols-[minmax(0,26.25rem)_minmax(0,1fr)]">
          <div className="w-full min-w-0 px-4 pt-6 pb-8 min-[720px]:border-r min-[720px]:border-rule min-[720px]:px-6">
            <p className="font-sans text-[0.7rem] font-semibold tracking-[0.18em] text-ink uppercase">
              Книга регулярных платежей
            </p>
            {phase === 'choices' ? (
              <div className="mt-4">
                <h2 className="font-sans text-2xl font-semibold text-ink">Этот Telegram ещё не привязан</h2>
                <p className="mt-2 mb-5 font-sans text-sm text-ink">
                  Можно открыть временную команду на <span className="num">24</span> часа, войти по коду приглашения или привязать уже существующий аккаунт.
                </p>
                {error && (
                  <p className="mb-4 font-sans text-sm font-semibold text-ink" role="alert">
                    {error}
                  </p>
                )}
                {!panel && (
                  <div className="flex flex-col gap-2">
                    <button type="button" className={winBtn} disabled={busy !== null} onClick={createTeam}>
                      {busy === 'create' ? 'Создаём…' : 'Создать временную команду'}
                    </button>
                    <button type="button" className={winBtn} disabled={busy !== null} onClick={() => { setPanel('join'); setError(null) }}>
                      Войти по коду приглашения
                    </button>
                    <button type="button" className={winBtn} disabled={busy !== null} onClick={() => { setPanel('link'); setError(null) }}>
                      Привязать уже существующий аккаунт
                    </button>
                  </div>
                )}
                {panel === 'join' && (
                  <form onSubmit={submitJoin} noValidate>
                    <label className="label" htmlFor="invite">
                      Код приглашения
                    </label>
                    <input
                      id="invite"
                      className="field num"
                      autoComplete="off"
                      autoFocus
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      required
                    />
                    <div className="mt-4 flex gap-2">
                      <button type="button" className={winBtnHalf} disabled={busy !== null} onClick={() => setPanel(null)}>
                        Назад
                      </button>
                      <button className={winBtnHalf} disabled={busy !== null || !code.trim()}>
                        {busy === 'join' ? 'Входим…' : 'Войти'}
                      </button>
                    </div>
                  </form>
                )}
                {panel === 'link' && (
                  <form onSubmit={submitLink} noValidate>
                    <p className="mb-3 font-sans text-sm text-ink">
                      Нужны логин и пароль уже существующей учётной записи. Новый администратор основной команды так не создаётся.
                    </p>
                    <div className="mb-4">
                      <label className="label" htmlFor="link-login">
                        Логин
                      </label>
                      <input
                        id="link-login"
                        className="field"
                        autoComplete="username"
                        autoFocus
                        value={link.login}
                        onChange={(e) => setLink({ ...link, login: e.target.value })}
                        required
                      />
                    </div>
                    <div className="mb-4">
                      <label className="label" htmlFor="link-password">
                        Пароль
                      </label>
                      <input
                        id="link-password"
                        type="password"
                        className="field"
                        autoComplete="current-password"
                        value={link.password}
                        onChange={(e) => setLink({ ...link, password: e.target.value })}
                        required
                      />
                    </div>
                    <div className="flex gap-2">
                      <button type="button" className={winBtnHalf} disabled={busy !== null} onClick={() => setPanel(null)}>
                        Назад
                      </button>
                      <button className={winBtnHalf} disabled={busy !== null || !link.login || !link.password}>
                        {busy === 'link' ? 'Привязываем…' : 'Привязать и войти'}
                      </button>
                    </div>
                  </form>
                )}
                <button type="button" className={`${winBtn} mt-4`} disabled={busy !== null} onClick={cancelTelegram}>
                  Войти другим способом
                </button>
              </div>
            ) : (
              <div className="mt-4">
                <p className="mb-4 font-sans text-sm text-ink">Регистрация — через Telegram.</p>
                <form onSubmit={submitPassword} noValidate>
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
                    <p className="mb-4 font-sans text-sm font-semibold text-ink" role="alert">
                      {error}
                    </p>
                  )}
                  <button className={winBtn} disabled={busy === 'password' || !form.login || !form.password}>
                    {busy === 'password' ? 'Входим…' : 'Войти'}
                  </button>
                </form>
                <div className="mt-3">
                  {tgHref ? (
                    <a
                      className={winBtn}
                      href={tgHref}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={openTelegram}
                    >
                      {busy === 'telegram' ? 'Ждём Telegram…' : 'Зайти через Telegram'}
                    </a>
                  ) : (
                    <button
                      type="button"
                      className={winBtn}
                      disabled={tgToken === null || busy === 'password'}
                      onClick={telegramUnavailable}
                    >
                      Зайти через Telegram
                    </button>
                  )}
                  {tgHref && (
                    <p className="mt-2 font-sans text-xs text-ink">
                      Откроется Telegram: нажмите Start и вернитесь на эту страницу.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
          <WelcomeCopy />
        </div>
        <Footer />
      </div>
    </div>
  )
}
