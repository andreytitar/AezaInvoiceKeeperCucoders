import { useEffect, useRef, useState } from 'react'
import type { Occurrence } from '../api/client'
import { formatDate, formatMoney } from '../i18n/format'
import { needsPayConfirm } from './largePayment'
import { dialogActionsCls, dialogBtnCls, dialogCls } from './ui'

type Props = {
  occurrence: Occurrence | null
  today: string
  busy: boolean
  onSubmit: (paidDate: string) => void
  onClose: () => void
}

/** Отметка оплаты с выбором фактической даты. Крупная сумма спрашивает подтверждение до запроса. */
export function MarkPaidDialog({ occurrence, today, busy, onSubmit, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [date, setDate] = useState(today)
  const [step, setStep] = useState<'date' | 'confirm'>('date')
  useEffect(() => {
    setStep('date')
  }, [occurrence?.id])
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (occurrence) {
      setDate(occurrence.paid_date ?? today)
      if (!d.open) d.showModal()
    } else if (d.open) d.close()
  }, [occurrence, today])
  const invalid = !date || date > today
  const amountClass = occurrence && occurrence.status === 'unpaid' && occurrence.is_overdue ? 'num text-overdue' : 'num'
  return (
    <dialog ref={ref} onClose={onClose} className={`${dialogCls} win-window`} aria-labelledby="pay-title">
      {occurrence && (
        <form
          className="p-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (invalid) return
            if (step === 'date' && needsPayConfirm(occurrence.status, occurrence.amount, occurrence.currency)) {
              setStep('confirm')
              return
            }
            onSubmit(date)
          }}
        >
          {step === 'confirm' ? (
            <>
              <h2 id="pay-title" className="font-sans text-xl font-semibold">
                Отметить оплату?
              </h2>
              <p className="text-sm text-ink mt-2">
                «{occurrence.title}» · <span className={amountClass}>{formatMoney(occurrence.amount, occurrence.currency)}</span>
              </p>
              <div className={dialogActionsCls}>
                <button type="button" className={dialogBtnCls} onClick={onClose} disabled={busy}>
                  Отмена
                </button>
                <button className={`${dialogBtnCls} btn-primary`} disabled={busy || invalid} autoFocus>
                  {busy ? '…' : 'Отметить'}
                </button>
              </div>
            </>
          ) : (
            <>
              <h2 id="pay-title" className="font-sans text-xl font-semibold">
                {occurrence.status === 'paid' ? 'Исправить дату оплаты' : 'Отметить оплату'}
              </h2>
              <p className="text-sm text-ink-soft mt-1">
                {occurrence.title} · <span className={amountClass}>{formatMoney(occurrence.amount, occurrence.currency)}</span> · срок{' '}
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
              {date > today && <p className="text-xs text-ink mt-1">Дата не может быть в будущем</p>}
              {date && date <= today && date > occurrence.due_date && (
                <p className="text-xs text-ink mt-1">Позже срока — будет отмечено как оплата с опозданием</p>
              )}
              <div className={dialogActionsCls}>
                <button type="button" className={dialogBtnCls} onClick={onClose} disabled={busy}>
                  Отмена
                </button>
                <button className={`${dialogBtnCls} btn-primary`} disabled={busy || invalid}>
                  {busy ? '…' : 'Сохранить'}
                </button>
              </div>
            </>
          )}
        </form>
      )}
    </dialog>
  )
}
