export type Theme = 'light' | 'dark'

const KEY = 'ik-theme'

export function loadTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* хранилище недоступно */
  }
  return 'light'
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
  try {
    localStorage.setItem(KEY, t)
  } catch {
    /* ignore */
  }
}
