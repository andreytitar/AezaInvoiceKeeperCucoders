import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

export type ShellLink = { to: string; label: string; end?: boolean }

const PRIMARY: ShellLink[] = [
  { to: '/', label: 'Платежи', end: true },
  { to: '/calendar', label: 'Календ.' },
  { to: '/budget', label: 'Бюджет' },
]

function dialogOpen() {
  return Boolean(document.querySelector('dialog[open], [aria-modal="true"]'))
}

/** Открытый dialog или модальный лист прячет нижнюю панель. */
function useOverlayOpen() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const sync = () => {
      const next = dialogOpen()
      setOpen((prev) => (prev === next ? prev : next))
    }
    sync()
    const obs = new MutationObserver(sync)
    obs.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['open', 'aria-modal'],
    })
    document.addEventListener('toggle', sync, true)
    document.addEventListener('close', sync, true)
    return () => {
      obs.disconnect()
      document.removeEventListener('toggle', sync, true)
      document.removeEventListener('close', sync, true)
    }
  }, [])
  return open
}

export function MobileNav({
  moreLinks,
  themeLabel,
  onTheme,
  onTelegram,
  onLogout,
}: {
  moreLinks: ShellLink[]
  themeLabel: string
  onTheme: () => void
  onTelegram: () => void
  onLogout: () => void
}) {
  const { pathname } = useLocation()
  const barRef = useRef<HTMLElement>(null)
  const moreRef = useRef<HTMLDialogElement>(null)
  const [more, setMore] = useState(false)
  const overlay = useOverlayOpen()
  const hideBar = overlay || more
  const moreCurrent = more || moreLinks.some((l) => pathname === l.to)

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 720px)')
    const close = () => {
      if (mq.matches) setMore(false)
    }
    close()
    mq.addEventListener('change', close)
    return () => mq.removeEventListener('change', close)
  }, [])

  useEffect(() => {
    const d = moreRef.current
    if (!d) return
    if (more && !d.open) d.showModal()
    if (!more && d.open) d.close()
  }, [more])

  useLayoutEffect(() => {
    const el = barRef.current
    if (!el) return
    const publish = () => {
      const cs = getComputedStyle(el)
      if (cs.display === 'none') {
        document.documentElement.style.setProperty('--nav-h', '0px')
        return
      }
      document.documentElement.style.setProperty('--nav-h', `${el.offsetHeight}px`)
    }
    publish()
    const ro = new ResizeObserver(publish)
    ro.observe(el)
    const mq = window.matchMedia('(min-width: 720px)')
    mq.addEventListener('change', publish)
    window.addEventListener('resize', publish)
    return () => {
      ro.disconnect()
      mq.removeEventListener('change', publish)
      window.removeEventListener('resize', publish)
      document.documentElement.style.setProperty('--nav-h', '0px')
    }
  }, [hideBar])

  const closeMore = () => setMore(false)
  const itemCls = (active: boolean) =>
    [
      'shell-more-item flex min-h-[44px] w-full items-center rounded-sm bg-transparent px-4 text-left font-sans text-[0.95rem] text-ink whitespace-normal break-words',
      active ? 'font-semibold bg-paper' : 'font-normal',
    ].join(' ')

  return (
    <>
      <style>{`
        html[data-theme="dark"] nav.shell-tabs {
          background: #0a0a0a;
          border-top-color: rgba(244, 244, 244, 0.12);
        }
        html[data-theme="dark"] .shell-tab {
          color: rgba(244, 244, 244, 0.78);
          border-top-color: transparent;
          font-weight: 500;
        }
        html[data-theme="dark"] a.shell-tab[aria-current="page"],
        html[data-theme="dark"] button.shell-tab[data-current="true"] {
          color: #f4f4f4;
          border-top-color: #e97c35;
          border-top-style: solid;
          font-weight: 600;
        }
        html[data-theme="dark"] #more-sheet {
          background: #000000;
          color: #f4f4f4;
          border-color: rgba(244, 244, 244, 0.16);
        }
        html[data-theme="dark"] #more-sheet a.shell-more-item {
          color: #f4f4f4;
          border-bottom-color: rgba(244, 244, 244, 0.12);
        }
        html[data-theme="dark"] #more-sheet a.shell-more-item[aria-current="page"] {
          background: rgba(244, 244, 244, 0.1);
        }
      `}</style>
      <nav
        ref={barRef}
        aria-label="Разделы"
        className={hideBar ? 'hidden' : 'shell-tabs fixed inset-x-0 bottom-0 z-30 overflow-x-hidden border-t border-rule bg-paper desk:hidden'}
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      >
        <ul className="grid grid-cols-4">
          {PRIMARY.map((l) => (
            <li key={l.to} className="min-w-0">
              <NavLink
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `shell-tab flex min-h-[44px] items-center justify-center border-t-2 px-0.5 text-center font-sans text-xs leading-tight ${isActive ? 'border-ink font-semibold text-ink' : 'border-transparent font-normal text-ink-soft'}`
                }
              >
                {l.label}
              </NavLink>
            </li>
          ))}
          <li className="min-w-0">
            <button
              type="button"
              className={`shell-tab flex min-h-[44px] w-full items-center justify-center rounded-none border-x-0 border-b-0 border-t-2 bg-transparent px-0.5 text-center font-sans text-xs leading-tight ${moreCurrent ? 'border-ink font-semibold text-ink' : 'border-transparent font-normal text-ink-soft'}`}
              data-current={moreCurrent ? 'true' : 'false'}
              aria-expanded={more}
              aria-haspopup="dialog"
              aria-controls="more-sheet"
              onClick={() => setMore(true)}
            >
              Ещё
            </button>
          </li>
        </ul>
      </nav>

      <dialog
        id="more-sheet"
        ref={moreRef}
        aria-labelledby="more-title"
        onClose={closeMore}
        onClick={(e) => {
          if (e.target === moreRef.current) closeMore()
        }}
        className="border-rule bg-paper-2 p-0 text-ink shadow-none"
        style={{
          margin: 0,
          width: '100%',
          maxWidth: '100%',
          maxHeight: '85dvh',
          height: 'auto',
          position: 'fixed',
          inset: 'auto 0 0 0',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
          boxShadow: 'none',
          borderRadius: '2px 2px 0 0',
        }}
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <h2 id="more-title" className="font-sans text-base font-semibold text-ink">
            Меню
          </h2>
          <button type="button" className="btn btn-ghost win-btn min-h-[44px] px-3" onClick={closeMore}>
            Закрыть
          </button>
        </div>
        <ul className="flex flex-col gap-0.5 px-2 pb-3">
          {moreLinks.map((l) => (
            <li key={l.to}>
              <NavLink to={l.to} end={l.end} onClick={closeMore} className={({ isActive }) => itemCls(isActive)}>
                {l.label}
              </NavLink>
            </li>
          ))}
          <li>
            <button type="button" className={`${itemCls(false)} win-btn`} onClick={() => { closeMore(); onTelegram() }}>
              Telegram
            </button>
          </li>
          <li>
            <button type="button" className={`${itemCls(false)} win-btn`} onClick={onTheme} aria-label="Переключить тему">
              {themeLabel}
            </button>
          </li>
          <li>
            <button type="button" className={`${itemCls(false)} win-btn`} onClick={() => { closeMore(); onLogout() }}>
              Выйти
            </button>
          </li>
        </ul>
      </dialog>
    </>
  )
}
