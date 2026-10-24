import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { TelegramDialog } from './TelegramDialog'
import { applyTheme, loadTheme, type Theme } from '../theme/theme'

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `px-1 py-1 text-sm border-b-2 ${isActive ? 'border-ink font-semibold' : 'border-transparent text-ink-soft hover:text-ink'}`

export function Layout() {
  const { me, logout, isAdmin } = useAuth()
  const [theme, setTheme] = useState<Theme>(loadTheme())
  const [menu, setMenu] = useState(false)
  const [tg, setTg] = useState(false)
  const toggleTheme = () => {
    const t = theme === 'light' ? 'dark' : 'light'
    setTheme(t)
    applyTheme(t)
  }
  const links = [
    { to: '/', label: 'Платежи', end: true },
    { to: '/calendar', label: 'Календарь', end: false },
    { to: '/budget', label: 'Бюджет', end: false },
    ...(isAdmin
      ? [
          { to: '/recurring', label: 'Регулярные платежи', end: false },
          { to: '/users', label: 'Пользователи', end: false },
          { to: '/webhooks', label: 'Вебхуки', end: false },
          { to: '/audit', label: 'Журнал', end: false },
        ]
      : []),
  ]
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2 focus:bg-sheet">
        К содержимому
      </a>
      <header className="border-b border-rule relative">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-6">
          <NavLink to="/" className="font-serif text-xl font-bold tracking-tight whitespace-nowrap">
            Invoice<span className="text-red">·</span>Keeper
          </NavLink>
          <nav className={`${menu ? 'flex' : 'hidden'} lg:flex absolute lg:static top-14 left-0 right-0 bg-paper lg:bg-transparent border-b lg:border-0 border-rule px-4 lg:px-0 py-2 lg:py-0 flex-col lg:flex-row gap-2 lg:gap-5 z-20`} aria-label="Разделы">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={linkCls} onClick={() => setMenu(false)}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden xl:inline text-sm text-ink-soft">
              {me?.login}
              {isAdmin && <span className="ml-1 num text-xs uppercase">[admin]</span>}
            </span>
            <button className="btn btn-sm" onClick={() => setTg(true)}>
              Telegram
            </button>
            <button className="btn btn-sm btn-ghost" onClick={toggleTheme} aria-label="Переключить тему">
              {theme === 'light' ? 'Тёмная' : 'Светлая'}
            </button>
            <button className="btn btn-sm" onClick={logout}>
              Выйти
            </button>
            <button className="btn btn-sm lg:hidden" onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-label="Меню">
              ☰
            </button>
          </div>
        </div>
      </header>
      <TelegramDialog open={tg} onClose={() => setTg(false)} />
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
