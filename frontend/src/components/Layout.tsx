import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'
import { applyTheme, loadTheme, type Theme } from '../theme/theme'
import { Footer } from './Footer'
import { MobileNav, type ShellLink } from './MobileNav'
import { TelegramDialog } from './TelegramDialog'

const sections: ShellLink[] = [
  { to: '/', label: 'Платежи', end: true },
  { to: '/calendar', label: 'Календарь' },
  { to: '/budget', label: 'Бюджет' },
]

const adminSections: ShellLink[] = [
  { to: '/recurring', label: 'Регулярные платежи' },
  { to: '/users', label: 'Пользователи' },
  { to: '/webhooks', label: 'Вебхуки' },
  { to: '/audit', label: 'Журнал' },
]

function Wordmark() {
  return (
    <NavLink to="/" className="font-serif text-[1.5rem] font-medium leading-none tracking-tight text-ink">
      Invoice Keeper
    </NavLink>
  )
}

export function Layout() {
  const { me, logout, isAdmin, enterAsEmployee } = useAuth()
  const toast = useToast()
  const [theme, setTheme] = useState<Theme>(loadTheme())
  const [tg, setTg] = useState(false)
  const [switching, setSwitching] = useState(false)
  const asEmployee = async () => {
    setSwitching(true)
    try {
      await enterAsEmployee()
      toast('ok', 'Открыт кабинет сотрудника')
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Не удалось войти как сотрудник')
    } finally {
      setSwitching(false)
    }
  }
  const toggleTheme = () => {
    const t = theme === 'light' ? 'dark' : 'light'
    setTheme(t)
    applyTheme(t)
  }
  const railLinks = [...sections, ...(isAdmin ? adminSections : [])]
  const themeLabel = theme === 'light' ? 'Тёмная' : 'Светлая'
  return (
    <div
      className="shell-root fixed inset-0 flex max-w-full flex-col overflow-hidden bg-paper text-ink"
      style={{
        paddingTop: 'env(safe-area-inset-top, 0px)',
        paddingLeft: 'env(safe-area-inset-left, 0px)',
        paddingRight: 'env(safe-area-inset-right, 0px)',
      }}
    >
      <style>{`
        :root { --nav-h: 0px; }
        @media (min-width: 720px) {
          :root { --nav-h: 0px !important; }
        }
        @media (max-width: 719px) {
          div.fixed[role="status"][aria-live="polite"] {
            bottom: calc(var(--nav-h, 0px) + 1rem);
          }
        }

        /* Тёмный кабинет. Светлая тема эти селекторы не получает. */
        html[data-theme="dark"] .shell-root,
        html[data-theme="dark"] .shell-frame {
          background: #0a0a0a;
          box-shadow: none;
        }
        html[data-theme="dark"] .shell-rail {
          background: #000000;
          border-right-color: rgba(244, 244, 244, 0.08);
          color: #f4f4f4;
        }
        html[data-theme="dark"] .shell-rail > .shell-brand {
          padding: 1rem 1rem 0.15rem;
        }
        html[data-theme="dark"] .shell-brand a {
          color: #f4f4f4;
          font-size: 1.125rem;
          font-weight: 600;
          letter-spacing: -0.02em;
        }
        html[data-theme="dark"] .shell-id {
          border-bottom-color: transparent;
          padding: 0.35rem 1rem 0.7rem;
        }
        html[data-theme="dark"] .shell-meta {
          color: rgba(244, 244, 244, 0.62);
        }
        html[data-theme="dark"] .shell-nav {
          padding: 0.25rem 0 0.35rem;
        }
        html[data-theme="dark"] .shell-rail .shell-link {
          min-height: 36px;
          margin: 1px 8px;
          padding: 0.35rem 0.55rem;
          border: 0;
          border-radius: 8px;
          background: transparent;
          color: #f4f4f4;
          font-size: 13px;
          font-weight: 500;
          line-height: 1.25;
        }
        html[data-theme="dark"] .shell-rail .shell-link:hover {
          background: rgba(244, 244, 244, 0.05);
        }
        html[data-theme="dark"] .shell-rail .shell-link[aria-current="page"] {
          background: rgba(244, 244, 244, 0.1);
          color: #f4f4f4;
          font-weight: 600;
        }
        html[data-theme="dark"] .shell-rail .shell-link:focus-visible,
        html[data-theme="dark"] .shell-rail .shell-quiet:focus-visible,
        html[data-theme="dark"] .shell-rail .shell-cta:focus-visible {
          outline: 2px solid #e97c35;
          outline-offset: 2px;
        }
        html[data-theme="dark"] .shell-actions {
          gap: 0.2rem;
          border-top-color: transparent;
          padding-top: 0.35rem;
          padding-left: 0.5rem;
          padding-right: 0.5rem;
        }
        html[data-theme="dark"] .shell-rail .shell-quiet {
          justify-content: flex-start;
          min-height: 36px;
          padding: 0.3rem 0.55rem;
          border: 0;
          border-radius: 8px;
          background: transparent;
          background-image: none;
          box-shadow: none;
          text-shadow: none;
          color: #f4f4f4;
          font-size: 13px;
          font-weight: 500;
        }
        html[data-theme="dark"] .shell-rail .shell-quiet:hover,
        html[data-theme="dark"] .shell-rail .shell-quiet:active {
          border-color: transparent;
          background: rgba(244, 244, 244, 0.06);
          color: #f4f4f4;
          box-shadow: none;
        }
        html[data-theme="dark"] .shell-rail .shell-cta {
          border: 0;
          border-radius: 10px;
          background: #e97c35;
          background-image: none;
          box-shadow: none;
          text-shadow: none;
          color: #000000;
          font-size: 13px;
          font-weight: 600;
        }
        html[data-theme="dark"] .shell-rail .shell-cta:hover,
        html[data-theme="dark"] .shell-rail .shell-cta:active {
          border-color: transparent;
          background: #e97c35;
          color: #000000;
          box-shadow: none;
          filter: brightness(1.08);
        }
        html[data-theme="dark"] .shell-mobile-head {
          background: #000000;
          border-bottom-color: rgba(244, 244, 244, 0.08);
        }
        html[data-theme="dark"] .shell-foot > footer {
          background: #0a0a0a;
          border-top-color: rgba(244, 244, 244, 0.08);
        }
      `}</style>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-paper-2 focus:p-2 focus:text-ink">
        К содержимому
      </a>
      <div className={`shell-frame flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden${theme === 'dark' ? '' : ' win-window'}`}>
        {theme !== 'dark' && (
          <div className="win-titlebar hidden shrink-0 desk:flex">
            <Wordmark />
          </div>
        )}
        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <aside
        className="shell-rail hidden min-h-0 w-[12rem] shrink-0 flex-col overflow-hidden border-r border-rule bg-paper desk:flex"
      >
        {theme === 'dark' && (
          <div className="shell-brand">
            <Wordmark />
          </div>
        )}
        <div className="shell-id border-b border-rule px-3 py-2">
          <p className="truncate font-sans text-sm text-ink">
            {me?.login}
            {isAdmin && <span className="ml-1.5 text-xs text-ink-soft">· админ</span>}
          </p>
        </div>
        <nav aria-label="Разделы" className="shell-nav min-h-0 flex-1 overflow-y-auto">
          {railLinks.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `shell-link mx-2 flex min-h-[40px] items-center rounded-sm px-2.5 py-1.5 font-sans text-[0.9rem] leading-snug whitespace-normal break-words text-ink ${isActive ? 'bg-paper-2 font-semibold' : 'font-normal'}`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="shell-actions flex shrink-0 flex-col gap-1.5 border-t border-rule p-2.5" style={{ paddingBottom: 'calc(0.65rem + env(safe-area-inset-bottom, 0px))' }}>
          <button type="button" className="btn win-btn shell-quiet w-full" onClick={() => setTg(true)}>
            Telegram
          </button>
          <button type="button" className="btn btn-ghost win-btn shell-quiet w-full" onClick={toggleTheme} aria-label="Переключить тему">
            {themeLabel}
          </button>
          <button type="button" className="btn win-btn shell-cta w-full" onClick={logout}>
            Выйти
          </button>
        </div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="shell-mobile-head flex min-h-[40px] items-center justify-between gap-2 border-b border-rule bg-paper px-4 py-1.5 desk:hidden">
          <div className="shell-brand min-w-0 shrink [&_a]:text-lg">
            <Wordmark />
          </div>
          <p className="min-w-0 truncate text-right font-sans text-xs text-ink-soft">
            <span className="sr-only">Вошли как </span>
            {me?.login}
            {isAdmin && (
              <span className="text-ink-soft" aria-label="администратор">
                {' '}
                · админ
              </span>
            )}
          </p>
        </header>
        <main
          id="main"
          className="shell-canvas flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto bg-paper"
          style={{ paddingBottom: 'var(--nav-h, 0px)' }}
        >
          <div className="px-4 py-3 desk:px-6 desk:py-5">
            {me?.team?.kind === 'sandbox' && (
              <div role="status" className="mb-3 rounded-sm border border-rule bg-paper-2 px-3 py-2.5 text-sm text-ink">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <p className="text-ink-soft">
                    Песочница до{' '}
                    <b className="num text-ink">
                      {me.team.expires_at
                        ? new Date(me.team.expires_at).toLocaleString('ru-RU', {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '24 ч'}
                    </b>
                    . Приглашение — в Telegram.
                  </p>
                  {isAdmin && (
                    <button type="button" className="btn win-btn" onClick={asEmployee} disabled={switching}>
                      {switching ? 'Входим…' : 'Зайти как сотрудник'}
                    </button>
                  )}
                </div>
              </div>
            )}
            <Outlet />
          </div>
          <div className="shell-foot mt-auto">
            <Footer />
          </div>
        </main>
      </div>
        </div>
      </div>
      <MobileNav
        moreLinks={isAdmin ? adminSections : []}
        themeLabel={themeLabel}
        onTheme={toggleTheme}
        onTelegram={() => setTg(true)}
        onLogout={() => {
          void logout()
        }}
      />
      <TelegramDialog open={tg} onClose={() => setTg(false)} />
    </div>
  )
}
