import type { Occurrence } from '../api/client'
import { OverdueCell, StatusCell, amountHot } from './Status'
import { formatDate, formatMoney } from '../i18n/format'
import { Icon } from './Icon'
import { Button, Menu, MenuItem } from './ui'

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
    <div className="min-w-0" aria-labelledby={titleId}>
      <h3 id={titleId} className="break-words text-base font-semibold leading-snug">{occurrence.title}</h3>
      <p className={`num mt-2 whitespace-nowrap text-xl font-semibold ${amountHot(occurrence) ? 'text-overdue' : ''}`}>
        {formatMoney(occurrence.amount, occurrence.currency)}
      </p>
      <div className="my-3"><StatusCell o={occurrence} /></div>
      <dl className="space-y-2 text-sm">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ink-soft">Срок оплаты</dt>
          <dd className="num whitespace-nowrap text-right">{formatDate(occurrence.due_date)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ink-soft">Дата оплаты</dt>
          <dd className="num whitespace-nowrap text-right">{formatDate(occurrence.paid_date)}</dd>
        </div>
        {occurrence.is_overdue && (
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-ink-soft">Просрочка</dt>
            <dd className="text-right"><OverdueCell o={occurrence} /></dd>
          </div>
        )}
      </dl>
      {occurrence.recurring_payment_deleted && <p className="mt-3 text-xs text-ink-soft">Регулярный платёж прекращён.</p>}
      <div className="mt-4 flex items-center gap-2 border-t border-rule pt-4">
        {occurrence.status === 'unpaid' ? (
          <Button variant="primary" className="min-w-0 flex-1" onClick={onPayToday} disabled={busy}>
            <Icon name="check" />Оплачено сегодня
          </Button>
        ) : (
          <Button variant="secondary" className="min-w-0 flex-1" onClick={onChangeDate} disabled={busy}>
            <Icon name="edit" />Изменить дату
          </Button>
        )}
        <Menu label={`Действия с платежом «${occurrence.title}»`}>
          <MenuItem onClick={occurrence.status === 'unpaid' ? onPayWithDate : onChangeDate} disabled={busy}>
            Указать дату оплаты
          </MenuItem>
          {occurrence.status === 'paid' && <MenuItem onClick={onUnpay} disabled={busy} danger>Отменить оплату</MenuItem>}
        </Menu>
      </div>
    </div>
  )
}
