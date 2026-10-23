import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type Occurrence = Schemas['OccurrenceOut']
export type RecurringPayment = Schemas['RecurringPaymentOut']
export type User = Schemas['UserOut']
export type Me = Schemas['MeOut']
export type Summary = Schemas['SummaryOut']
export type Currency = Schemas['Currency']

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()
export function onUnauthorized(fn: Listener) {
  unauthorizedListeners.add(fn)
  return () => unauthorizedListeners.delete(fn)
}

const authMiddleware: Middleware = {
  async onResponse({ response, request }) {
    if (response.status === 401 && !request.url.includes('/auth/login')) {
      unauthorizedListeners.forEach((fn) => fn())
    }
    return response
  },
}

export const api = createClient<paths>({ baseUrl: '/', credentials: 'same-origin' })
api.use(authMiddleware)

const FIELD_NAMES: Record<string, string> = {
  login: 'Логин',
  password: 'Пароль',
  title: 'Название',
  amount: 'Сумма',
  currency: 'Валюта',
  first_due_date: 'Дата оплаты',
  paid_date: 'Дата оплаты',
  email: 'Email',
  telegram_user_id: 'Telegram ID',
}

/** Достаёт данные из ответа openapi-fetch или бросает ApiError с понятным текстом. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || !res.response.ok) {
    const body = (res.error ?? {}) as { error?: { code?: string; message?: string; details?: unknown } }
    const err = body.error ?? {}
    let message = err.message ?? `Ошибка ${res.response.status}`
    if (err.code === 'validation_error' && Array.isArray(err.details) && err.details.length) {
      const first = err.details[0] as { loc?: string[]; msg?: string }
      const field = first.loc?.[first.loc.length - 1]
      message = `${FIELD_NAMES[field ?? ''] ?? field ?? 'Поле'}: ${first.msg ?? 'некорректное значение'}`
    }
    throw new ApiError(res.response.status, err.code ?? 'error', message, err.details)
  }
  return res.data as T
}
