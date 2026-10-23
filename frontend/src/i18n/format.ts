const moneyFormatters = new Map<string, Intl.NumberFormat>()

export function formatMoney(amount: string | number, currency: string): string {
  let f = moneyFormatters.get(currency)
  if (!f) {
    f = new Intl.NumberFormat('ru-RU', { style: 'currency', currency, minimumFractionDigits: 2 })
    moneyFormatters.set(currency, f)
  }
  return f.format(Number(amount))
}

const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
const dateFmtShort = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' })
const monthFmt = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' })

/** 'YYYY-MM-DD' → Date в локальной зоне без сдвига. */
export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toISODate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export const formatDate = (iso: string | null | undefined) => (iso ? dateFmt.format(parseISODate(iso)).replace(' г.', '') : '—')
export const formatDateShort = (iso: string) => dateFmtShort.format(parseISODate(iso))
export const formatMonth = (d: Date) => {
  const s = monthFmt.format(d).replace(' г.', '')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function plural(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 100
  const b = a % 10
  if (a > 10 && a < 20) return many
  if (b > 1 && b < 5) return few
  if (b === 1) return one
  return many
}

export const days = (n: number) => `${n} ${plural(n, 'день', 'дня', 'дней')}`

export function dueHint(daysUntil: number): string {
  if (daysUntil > 1) return `через ${days(daysUntil)}`
  if (daysUntil === 1) return 'завтра'
  if (daysUntil === 0) return 'сегодня'
  return `${days(-daysUntil)} назад`
}

export const CURRENCIES = ['RUB', 'USD', 'EUR'] as const
export const CURRENCY_NAMES: Record<string, string> = { RUB: 'Рубли', USD: 'Доллары', EUR: 'Евро' }
export const RECURRENCE_NAMES: Record<string, string> = {
  monthly: 'Ежемесячно',
  weekly: 'Еженедельно',
  quarterly: 'Ежеквартально',
  yearly: 'Ежегодно',
}
