import type { Occurrence } from '../api/client'
import { OverdueCell, StatusCell, amountHot } from './Status'
import { formatDate, formatMoney } from '../i18n/format'

type Props = {
  occurrence: Occurrence
  busy: boolean
  onPayToday: () => void
  onPayWithDate: () => void
  onUnpay: () => void
  onChangeDate: () => void
  titleId?: string
}

export function CalendarOccurrenceDetail({
  occurrence,
  busy,
  onPayToday,
  onPayWithDate,
  onUnpay,
  onChangeDate,
  titleId = 'occ-title',
}: Props) {
  return (
    <div className="cal-occ-detail">
      <h2 id={titleId} className="font-sans text-xl font-semibold">
        {occurrence.title}
      </h2>
      <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-ink-soft">Сумма</dt>
        <dd className={`num ${amountHot(occurrence) ? 'text-overdue' : ''}`}>
          {formatMoney(occurrence.amount, occurrence.currency)}
        </dd>
        <dt className="text-ink-soft">Срок</dt>
        <dd className="num">{formatDate(occurrence.due_date)}</dd>
        <dt className="text-ink-soft">Статус</dt>
        <dd>
          <StatusCell o={occurrence} />
        </dd>
        <dt className="text-ink-soft">Дата оплаты</dt>
        <dd className="num">{formatDate(occurrence.paid_date)}</dd>
        <dt className="text-ink-soft">Просрочка</dt>
        <dd>
          <OverdueCell o={occurrence} />
        </dd>
      </dl>
      {occurrence.recurring_payment_deleted && (
        <p className="text-xs text-ink-soft mt-2">Регулярный платёж прекращён.</p>
      )}
      <div className="cal-actions">
        {occurrence.status === 'unpaid' ? (
          <>
            <button type="button" className="btn" onClick={onPayWithDate} disabled={busy}>
              Указать дату оплаты
            </button>
            <button type="button" className="btn btn-primary" onClick={onPayToday} disabled={busy}>
              Оплачено сегодня
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn" onClick={onChangeDate} disabled={busy}>
              Указать дату оплаты
            </button>
            <button type="button" className="btn" onClick={onUnpay} disabled={busy}>
              Отменить оплату
            </button>
          </>
        )}
      </div>
    </div>
  )
}
