import { useEffect, useRef } from 'react'

export type TelegramWidgetUser = {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

declare global {
  interface Window {
    invoiceKeeperTelegramAuth?: (user: TelegramWidgetUser) => void
  }
}

const WIDGET_W = 238
const WIDGET_H = 40

/**
 * Официальный Telegram Login Widget.
 * cover: iframe лежит поверх своей кнопки и принимает клик.
 * Прячем его через filter, а не opacity: виджет считает opacity < 0.1
 * невидимым и не открывает окно входа.
 */
export function TelegramLoginWidget({
  botUsername,
  onAuth,
  cover = false,
}: {
  botUsername: string
  onAuth: (user: TelegramWidgetUser) => void
  cover?: boolean
}) {
  const host = useRef<HTMLDivElement>(null)
  const onAuthRef = useRef(onAuth)
  onAuthRef.current = onAuth

  useEffect(() => {
    const node = host.current
    if (!node) return
    window.invoiceKeeperTelegramAuth = (user) => onAuthRef.current(user)
    const script = document.createElement('script')
    script.async = true
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.setAttribute('data-telegram-login', botUsername)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-userpic', 'false')
    script.setAttribute('data-radius', '8')
    script.setAttribute('data-lang', 'ru')
    script.setAttribute('data-onauth', 'invoiceKeeperTelegramAuth(user)')
    node.replaceChildren(script)

    let naturalW = WIDGET_W
    let naturalH = WIDGET_H
    let applied = ''
    const fit = () => {
      if (!cover) return
      const iframe = node.querySelector('iframe')
      if (!iframe) return
      const attrW = Number(iframe.getAttribute('width'))
      const attrH = Number(iframe.getAttribute('height'))
      if (attrW > 20) naturalW = attrW
      if (attrH > 10) naturalH = attrH
      const styleW = parseFloat(iframe.style.width)
      const styleH = parseFloat(iframe.style.height)
      if (styleW > 20 && Math.abs(styleW - naturalW) > 1) naturalW = styleW
      if (styleH > 10 && Math.abs(styleH - naturalH) > 1) naturalH = styleH
      const rect = node.getBoundingClientRect()
      if (rect.width < 2 || rect.height < 2) return
      const key = `${Math.round(rect.width)}x${Math.round(rect.height)}:${naturalW}x${naturalH}`
      if (applied === key && node.style.pointerEvents === 'auto') return
      applied = key
      iframe.style.position = 'absolute'
      iframe.style.left = '0'
      iframe.style.top = '0'
      iframe.style.width = `${naturalW}px`
      iframe.style.height = `${naturalH}px`
      iframe.style.maxWidth = 'none'
      iframe.style.transformOrigin = '0 0'
      iframe.style.border = 'none'
      iframe.style.opacity = '1'
      iframe.style.transform = `scale(${rect.width / naturalW}, ${rect.height / naturalH})`
      node.style.pointerEvents = 'auto'
    }

    const observer = new MutationObserver(fit)
    observer.observe(node, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'width', 'height'] })
    const resize = new ResizeObserver(fit)
    resize.observe(node)
    fit()

    return () => {
      observer.disconnect()
      resize.disconnect()
      node.replaceChildren()
      if (window.invoiceKeeperTelegramAuth) delete window.invoiceKeeperTelegramAuth
    }
  }, [botUsername, cover])

  if (!cover) return <div ref={host} className="flex min-h-11 w-full items-center justify-start" />

  return (
    <div
      ref={host}
      className="absolute inset-0 z-10 overflow-hidden pointer-events-none"
      style={{ filter: 'opacity(0)' }}
    />
  )
}
