/** Telegram Mini App (полная панель в WebView бота). */

export type TelegramWebApp = {
  initData: string
  initDataUnsafe: { user?: { id: number } }
  colorScheme: 'light' | 'dark'
  ready: () => void
  expand: () => void
  onEvent: (event: string, handler: () => void) => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  const webApp = window.Telegram?.WebApp
  if (!webApp?.initData) return null
  return webApp
}

/** Вызывать как можно раньше: разворот WebView и опционально тема из Telegram. */
export function bootstrapTelegramWebApp(): boolean {
  const webApp = getTelegramWebApp()
  if (!webApp) return false
  webApp.ready()
  webApp.expand()
  const scheme = webApp.colorScheme
  if (scheme === 'light' || scheme === 'dark') {
    document.documentElement.dataset.theme = scheme
    webApp.onEvent('themeChanged', () => {
      const next = webApp.colorScheme
      if (next === 'light' || next === 'dark') {
        document.documentElement.dataset.theme = next
      }
    })
  }
  return true
}
