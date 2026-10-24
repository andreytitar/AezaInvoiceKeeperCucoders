import { useState, type FormEvent } from 'react'
import type { Occurrence } from '../api/client'
import { formatDate, formatMoney } from '../i18n/format'
import { needsPayConfirm } from './largePayment'
import { Button, DateInput, Dialog, dialogActionsCls } from './ui'

type Props = {
  occurrence: Occurrence | null
  today: string
  busy: boolean
  onSubmit: (paidDate: string) => void
  onClose: () => void
}
export function MarkPaidDialog(props: Props) {
  return (
    <Dialog
      open={!!props.occurrence}
      onClose={props.onClose}
      title={props.occurrence?.status === 'paid' ? 'Исправить дату оплаты' : 'Отметить оплату'}
    >
      {props.occurrence && <PaidForm key={props.occurrence.id} {...props} occurrence={props.occurrence} />}
    </Dialog>
  )
}
function PaidForm({ occurrence, today, busy, onSubmit, onClose }: Props & { occurrence: Occurrence }) {
  const [date, setDate] = useState(occurrence.paid_date ?? today)
  const [confirm, setConfirm] = useState(false)
  const invalid = !date || date > today
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (invalid) return
    if (!confirm && needsPayConfirm(occurrence.status, occurrence.amount, occurrence.currency)) {
      setConfirm(true)
      return
    }
    onSubmit(date)
  }
  return (
    <form onSubmit={submit}>
      <p className="text-sm text-ink-soft">
        {occurrence.title} · <span className="num text-ink">{formatMoney(occurrence.amount, occurrence.currency)}</span>{' '}
        · срок <span className="num">{formatDate(occurrence.due_date)}</span>
      </p>
      {confirm ? (
        <p className="mt-5 text-sm font-medium">Подтвердите оплату крупной суммы за {formatDate(date)}.</p>
      ) : (
        <>
          <label className="label mt-5" htmlFor="paid-date">
            Фактическая дата оплаты
          </label>
          <DateInput id="paid-date" value={date} max={today} onChange={setDate} required />
          {date > today && <p className="mt-2 text-xs text-overdue">Дата не может быть в будущем</p>}
          {date && date <= today && date > occurrence.due_date && (
            <p className="mt-2 text-xs text-ink-soft">Позже срока — будет отмечено как оплата с опозданием</p>
          )}
        </>
      )}
      <div className={dialogActionsCls}>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button type="submit" variant="primary" loading={busy} disabled={invalid}>
          {confirm ? 'Отметить' : 'Сохранить'}
        </Button>
      </div>
    </form>
  )
}
