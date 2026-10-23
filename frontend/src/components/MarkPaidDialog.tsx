import { useEffect, useRef, useState } from 'react'
import type { Occurrence } from '../api/client'
import { formatDate, formatMoney } from '../i18n/format'

type Props = {
  occurrence: Occurrence | null
  today: string
  busy: boolean
  onSubmit: (paidDate: string) => void
  onClose: () => void
}

/** Отметка оплаты с выбором фактической даты (по умолчанию — сегодня, не позже сегодня). */
export function MarkPaidDialog({ occurrence, today, busy, onSubmit, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [date, setDate] = useState(today)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (occurrence) {
      setDate(occurrence.paid_date ?? today)
      if (!d.open) d.showModal()
    } else if (d.open) d.close()
  }, [occurrence, today])
  const invalid = !date || date > today
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="sheet m-auto w-[min(92vw,24rem)] p-0 text-ink backdrop:bg-black/40 shadow-[4px_4px_0_var(--ink)]"
      aria-labelledby="pay-title"
    >
      {occurrence && (
        <form
          className="p-5"
          onSubmit={(e) => {
            e.preventDefault()
            if (!invalid) onSubmit(date)
          }}
        >
          <h2 id="pay-title" className="font-serif text-xl font-bold">
            {occurrence.status === 'paid' ? 'Исправить дату оплаты' : 'Отметить оплату'}
          </h2>
          <p className="text-sm text-ink-soft mt-1">
            {occurrence.title} · <span className="num">{formatMoney(occurrence.amount, occurrence.currency)}</span> · срок{' '}
            {formatDate(occurrence.due_date)}
          </p>
          <label className="label mt-4" htmlFor="paid-date">
            Фактическая дата оплаты
          </label>
          <input
            id="paid-date"
            type="date"
            className="field num"
            value={date}
            max={today}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          {date > today && <p className="text-xs text-red mt-1">Дата не может быть в будущем</p>}
          {date && date <= today && date > occurrence.due_date && (
            <p className="text-xs text-red mt-1">Позже срока — будет отмечено как оплата с опозданием</p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn" onClick={onClose} disabled={busy}>
              Отмена
            </button>
            <button className="btn btn-primary" disabled={busy || invalid}>
              {busy ? '…' : 'Сохранить'}
            </button>
          </div>
        </form>
      )}
    </dialog>
  )
}
