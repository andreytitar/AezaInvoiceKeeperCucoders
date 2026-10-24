import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'
import { applyTheme, loadTheme, type Theme } from '../theme/theme'
import { Footer } from './Footer'
import { MobileNav, type ShellLink } from './MobileNav'
import { TelegramDialog } from './TelegramDialog'
import { Icon } from './Icon'
import { Button, Menu, MenuItem } from './ui'

const sections: ShellLink[] = [
  { to: '/', label: 'Платежи', icon: 'wallet', end: true },
  { to: '/calendar', label: 'Календарь', icon: 'calendar' },
  { to: '/budget', label: 'Бюджет', icon: 'budget' },
]
const adminSections: ShellLink[] = [
  { to: '/recurring', label: 'Регулярные платежи', icon: 'repeat' },
  { to: '/users', label: 'Пользователи', icon: 'users' },
  { to: '/webhooks', label: 'Вебхуки', icon: 'webhook' },
  { to: '/audit', label: 'Журнал', icon: 'audit' },
]
export function Wordmark() {
  return (
    <NavLink to="/" className="shell-brand" aria-label="Invoice Keeper — платежи">
      <span className="brand-mark">
        <Icon name="receipt" />
      </span>
      <div>
        <p className="brand-name">Invoice Keeper</p>
        <p className="brand-caption">Регулярные платежи команды</p>
      </div>
    </NavLink>
  )
}
export function Layout() {
  const { me, logout, isAdmin, enterAsEmployee } = useAuth()
  const toast = useToast()
  const [theme, setTheme] = useState<Theme>(loadTheme)
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
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    applyTheme(next)
  }
  const themeLabel = theme === 'light' ? 'Тёмная тема' : 'Светлая тема'
  const renderLink = (link: ShellLink) => (
    <NavLink key={link.to} to={link.to} end={link.end} className="shell-link">
      <Icon name={link.icon} />
      {link.label}
    </NavLink>
  )
  return (
    <div className="shell-root">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:z-50 focus:bg-paper-2 focus:p-4">
        К содержимому
      </a>
      <aside className="shell-rail">
        <Wordmark />
        <nav className="shell-nav" aria-label="Разделы">
          {sections.map(renderLink)}
          {isAdmin && (
            <>
              <div className="shell-divider" />
              {adminSections.map(renderLink)}
            </>
          )}
        </nav>
        <div className="user-block">
          <span className="user-avatar" aria-hidden="true">
            {me?.login.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me?.login}</p>
            <p className="text-xs text-ink-soft">{isAdmin ? 'Администратор' : 'Сотрудник'}</p>
          </div>
          <Menu label="Меню пользователя">
            <MenuItem onClick={() => setTg(true)}>
              <Icon name="telegram" />
              Telegram
            </MenuItem>
            <MenuItem onClick={toggleTheme}>
              <Icon name={theme === 'light' ? 'moon' : 'sun'} />
              {themeLabel}
            </MenuItem>
            <MenuItem onClick={() => void logout()}>
              <Icon name="logout" />
              Выйти
            </MenuItem>
          </Menu>
        </div>
      </aside>
      <div className="shell-content">
        <header className="shell-mobile-head">
          <Wordmark />
          <span className="user-avatar" title={me?.login} aria-label={`Вошли как ${me?.login}`}>
            {me?.login.slice(0, 2).toUpperCase()}
          </span>
        </header>
        <main id="main" className="shell-canvas">
          {me?.team?.kind === 'sandbox' && (
            <div role="status" className="sheet mb-6 flex flex-wrap items-center gap-3 p-4 text-sm">
              <Icon name="clock" />
              <p className="flex-1 text-ink-soft">
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
                <Button onClick={asEmployee} loading={switching}>
                  Зайти как сотрудник
                </Button>
              )}
            </div>
          )}
          <Outlet />
        </main>
        <Footer />
      </div>
      <MobileNav
        moreLinks={isAdmin ? adminSections : []}
        themeLabel={themeLabel}
        theme={theme}
        login={me?.login ?? ''}
        isAdmin={isAdmin}
        onTheme={toggleTheme}
        onTelegram={() => setTg(true)}
        onLogout={() => void logout()}
      />
      <TelegramDialog open={tg} onClose={() => setTg(false)} />
    </div>
  )
}
