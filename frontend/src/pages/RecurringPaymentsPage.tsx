import { useState, type FormEvent } from 'react'
import { api, unwrap, type RecurringPayment } from '../api/client'
import { ConfirmDialog, Empty, ErrorNote, Loading, PageTitle } from '../components/ui'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { CURRENCIES, RECURRENCE_NAMES, formatDate, formatMoney } from '../i18n/format'
import { useToast } from '../store/toast'

type Form = { title: string; amount: string; currency: string; first_due_date: string; recurrence: string }

export function RecurringPaymentsPage() {
  const toast = useToast()
  const { today } = useServerToday()
  const [showDeleted, setShowDeleted] = useState(false)
  const list = useLoad(
    async () =>
      unwrap(await api.GET('/api/v1/recurring-payments', { params: { query: { include_deleted: showDeleted } } })),
    [showDeleted],
  )
  const empty: Form = { title: '', amount: '', currency: 'RUB', first_due_date: '', recurrence: 'monthly' }
  const [form, setForm] = useState<Form>(empty)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<RecurringPayment | null>(null)
  const [editing, setEditing] = useState<RecurringPayment | null>(null)

  const startEdit = (p: RecurringPayment) => {
    setEditing(p)
    setError(null)
    setForm({ title: p.title, amount: p.amount, currency: p.currency, first_due_date: p.first_due_date, recurrence: p.recurrence })
  }
  const cancelEdit = () => {
    setEditing(null)
    setForm(empty)
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    if (editing) {
      try {
        const p = unwrap(
          await api.PATCH('/api/v1/recurring-payments/{payment_id}', {
            params: { path: { payment_id: editing.id } },
            body: { title: form.title.trim(), amount: form.amount.replace(',', '.').replace(/\s/g, ''), currency: form.currency as 'RUB' },
          }),
        )
        toast('ok', `«${p.title}» обновлён: новые значения действуют с ближайшего неоплаченного периода`)
        cancelEdit()
        list.reload()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Ошибка')
      } finally {
        setBusy(false)
      }
      return
    }
    try {
      const p = unwrap(
        await api.POST('/api/v1/recurring-payments', {
          body: {
            title: form.title.trim(),
            amount: form.amount.replace(',', '.').replace(/\s/g, ''),
            currency: form.currency as 'RUB',
            first_due_date: form.first_due_date || today,
            recurrence: form.recurrence as 'monthly',
          },
        }),
      )
      toast('ok', `Платёж «${p.title}» добавлен, ближайший срок ${formatDate(p.next_due_date)}`)
      setForm(empty)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (p: RecurringPayment) => {
    setBusy(true)
    try {
      unwrap(await api.DELETE('/api/v1/recurring-payments/{payment_id}', { params: { path: { payment_id: p.id } } }))
      toast('ok', `Платёж «${p.title}» прекращён, история сохранена`)
      setDeleting(null)
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageTitle>Регулярные платежи</PageTitle>
      <div className="grid lg:grid-cols-[22rem_1fr] gap-6 items-start">
        <form onSubmit={submit} className="sheet p-5" aria-labelledby="new-payment">
          <h2 id="new-payment" className="font-serif text-lg font-bold mb-3">
            {editing ? `Изменить «${editing.title}»` : 'Новый платёж'}
          </h2>
          {editing && (
            <p className="text-xs text-ink-soft mb-3">
              Оплаченные и прошедшие периоды сохранят прежнюю сумму. Срок и периодичность не меняются.
            </p>
          )}
          <label className="label" htmlFor="p-title">
            Название
          </label>
          <input
            id="p-title"
            className="field mb-3"
            required
            maxLength={200}
            placeholder="Аренда офиса"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <div className="grid grid-cols-[1fr_6rem] gap-2 mb-3">
            <div>
              <label className="label" htmlFor="p-amount">
                Сумма
              </label>
              <input
                id="p-amount"
                className="field num"
                inputMode="decimal"
                required
                placeholder="55000.00"
                pattern="^\s*\d[\d\s]*([.,]\d{1,2})?\s*$"
                title="Число, не больше двух знаков после запятой"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="p-cur">
                Валюта
              </label>
              <select id="p-cur" className="field" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                {CURRENCIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <label className="label" htmlFor="p-date">
            Дата ближайшей оплаты
          </label>
          <input
            id="p-date"
            type="date"
            className="field num mb-1"
            required
            disabled={!!editing}
            value={form.first_due_date}
            onChange={(e) => setForm({ ...form, first_due_date: e.target.value })}
          />
          <p className="text-xs text-ink-soft mb-3">
            Следующие сроки считаются от этого числа; если его нет в месяце — последний день месяца.
          </p>
          <label className="label" htmlFor="p-rec">
            Периодичность
          </label>
          <select id="p-rec" className="field mb-4" disabled={!!editing} value={form.recurrence} onChange={(e) => setForm({ ...form, recurrence: e.target.value })}>
            {Object.entries(RECURRENCE_NAMES).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          {error && (
            <p className="text-sm text-red mb-3" role="alert">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <button className="btn btn-primary flex-1 justify-center" disabled={busy}>
              {editing ? 'Сохранить' : 'Добавить'}
            </button>
            {editing && (
              <button type="button" className="btn" onClick={cancelEdit}>
                Отмена
              </button>
            )}
          </div>
        </form>

        <div>
          <label className="inline-flex items-center gap-2 text-sm mb-2">
            <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
            Показать прекращённые
          </label>
          <div className="sheet overflow-x-auto">
            {list.error ? (
              <div className="p-4">
                <ErrorNote text={list.error} onRetry={list.reload} />
              </div>
            ) : !list.data ? (
              <Loading />
            ) : list.data.length === 0 ? (
              <Empty title="Платежей пока нет" hint="Добавьте первый платёж в форме слева" />
            ) : (
              <table className="ledger w-full min-w-[620px]">
                <thead>
                  <tr>
                    <th>Название</th>
                    <th className="text-right">Сумма</th>
                    <th>Периодичность</th>
                    <th>Ближайший срок</th>
                    <th className="text-right">
                      <span className="sr-only">Действия</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((p) => (
                    <tr key={p.id} className={p.is_deleted ? 'text-ink-soft' : ''}>
                      <td className="font-semibold">
                        {p.title}
                        {p.is_deleted && <span className="block text-xs font-normal">прекращён {formatDate(p.deleted_at?.slice(0, 10))}</span>}
                      </td>
                      <td className="num text-right whitespace-nowrap">{formatMoney(p.amount, p.currency)}</td>
                      <td className="text-sm">
                        {RECURRENCE_NAMES[p.recurrence]}
                        <span className="text-ink-soft">, {p.anchor_day}-го</span>
                      </td>
                      <td className="num text-sm">{p.is_deleted ? '—' : formatDate(p.next_due_date)}</td>
                      <td className="text-right">
                        {!p.is_deleted && (
                          <span className="inline-flex gap-1">
                            <button className="btn btn-sm" onClick={() => startEdit(p)}>
                              Изменить
                            </button>
                            <button className="btn btn-sm btn-danger" onClick={() => setDeleting(p)}>
                              Удалить
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={!!deleting}
        title="Удалить регулярный платёж?"
        body={
          deleting && (
            <>
              «{deleting.title}» перестанет создавать новые периоды и напоминания. Оплаченные и прошедшие периоды
              останутся в истории, будущие неоплаченные будут удалены.
            </>
          )
        }
        confirmText="Удалить"
        danger
        busy={busy}
        onConfirm={() => deleting && remove(deleting)}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}
