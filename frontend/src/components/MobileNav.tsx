import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Icon, type IconName } from './Icon'
import { Dialog } from './ui'
import type { Theme } from '../theme/theme'

export type ShellLink = { to: string; label: string; icon: IconName; end?: boolean }
const PRIMARY: ShellLink[] = [
  { to: '/', label: 'Платежи', icon: 'wallet', end: true },
  { to: '/calendar', label: 'Календарь', icon: 'calendar' },
  { to: '/budget', label: 'Бюджет', icon: 'budget' },
]
export function MobileNav({
  moreLinks,
  themeLabel,
  theme,
  login,
  isAdmin,
  onTheme,
  onTelegram,
  onLogout,
}: {
  moreLinks: ShellLink[]
  themeLabel: string
  theme: Theme
  login: string
  isAdmin: boolean
  onTheme: () => void
  onTelegram: () => void
  onLogout: () => void
}) {
  const { pathname } = useLocation()
  const [more, setMore] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 719px)')
    const sync = () => {
      document.documentElement.style.setProperty(
        '--nav-h',
        mq.matches ? 'calc(64px + env(safe-area-inset-bottom, 0px))' : '0px',
      )
      if (!mq.matches) setMore(false)
    }
    sync()
    mq.addEventListener('change', sync)
    return () => {
      mq.removeEventListener('change', sync)
      document.documentElement.style.removeProperty('--nav-h')
    }
  }, [])
  return (
    <>
      <nav aria-label="Мобильная навигация" className="shell-tabs">
        <ul>
          {PRIMARY.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end={link.end} className="shell-tab">
                <Icon name={link.icon} />
                {link.label}
              </NavLink>
            </li>
          ))}
          <li>
            <button
              type="button"
              className="shell-tab"
              data-current={moreLinks.some((link) => pathname === link.to)}
              aria-expanded={more}
              aria-haspopup="dialog"
              onClick={() => setMore(true)}
            >
              <Icon name="more" />
              Ещё
            </button>
          </li>
        </ul>
      </nav>
      <Dialog open={more} onClose={() => setMore(false)} title="Меню" className="mobile-menu-dialog">
        <div className="mb-4 flex items-center gap-3 border-b border-rule pb-4">
          <span className="user-avatar">{login.slice(0, 2).toUpperCase()}</span>
          <div>
            <p className="font-medium">{login}</p>
            <p className="text-xs text-ink-soft">{isAdmin ? 'Администратор' : 'Сотрудник'}</p>
          </div>
        </div>
        <nav aria-label="Другие разделы">
          {moreLinks.map((link) => (
            <NavLink key={link.to} to={link.to} onClick={() => setMore(false)} className="shell-more-item">
              <Icon name={link.icon} />
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-3 border-t border-rule pt-3">
          <button
            type="button"
            className="shell-more-item"
            onClick={() => {
              setMore(false)
              onTelegram()
            }}
          >
            <Icon name="telegram" />
            Telegram
          </button>
          <button type="button" className="shell-more-item" onClick={onTheme} aria-label="Переключить тему">
            <Icon name={theme === 'light' ? 'moon' : 'sun'} />
            {themeLabel}
          </button>
          <button
            type="button"
            className="shell-more-item"
            onClick={() => {
              setMore(false)
              onLogout()
            }}
          >
            <Icon name="logout" />
            Выйти
          </button>
        </div>
      </Dialog>
    </>
  )
}
