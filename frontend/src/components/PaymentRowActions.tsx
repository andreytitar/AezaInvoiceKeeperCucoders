import type { Occurrence } from '../api/client'
import { Icon } from './Icon'
import { Button, Menu, MenuItem } from './ui'

type Props = {
  occurrence: Occurrence
  busy: boolean
  placement: 'slip' | 'table'
  onPaidToday: () => void
  onPickDate: () => void
  onReceipt: () => void
  onUnpay: () => void
}

/** Одно основное действие, остальные — в доступном с клавиатуры меню. */
export function PaymentRowActions({ occurrence, busy, placement, onPaidToday, onPickDate, onReceipt, onUnpay }: Props) {
  const unpaid = occurrence.status === 'unpaid'
  return (
    <div
      className={`flex items-center gap-2 ${placement === 'table' ? 'justify-end' : 'justify-between'}`}
      role="group"
      aria-label={`Действия для «${occurrence.title}»`}
    >
      {unpaid ? (
        <Button
          size="sm"
          variant="primary"
          disabled={busy}
          onClick={onPaidToday}
          aria-label={`Отметить «${occurrence.title}» оплаченным сегодня`}
          title="Отметить оплату сегодняшней датой"
        >
          <Icon name="check" />
          Оплачено
        </Button>
      ) : placement === 'slip' ? (
        <span className="text-xs text-ink-soft">{occurrence.has_receipt ? 'Чек прикреплён' : 'Платёж оплачен'}</span>
      ) : null}
      <Menu label={`Действия для «${occurrence.title}»`}>
        <MenuItem onClick={onPickDate} disabled={busy}>
          <Icon name="calendar" />
          {unpaid ? 'Указать дату оплаты' : 'Изменить дату оплаты'}
        </MenuItem>
        <MenuItem onClick={onReceipt} disabled={busy}>
          <Icon name="receipt" />
          {occurrence.has_receipt ? 'Открыть чек' : 'Прикрепить чек'}
        </MenuItem>
        {!unpaid && (
          <MenuItem onClick={onUnpay} disabled={busy} danger>
            <Icon name="close" />
            Отменить оплату
          </MenuItem>
        )}
      </Menu>
    </div>
  )
}
