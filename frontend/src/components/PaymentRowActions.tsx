import type { Occurrence } from '../api/client'

type Placement = 'slip' | 'table'

type Props = {
  occurrence: Occurrence
  busy: boolean
  placement: Placement
  onPaidToday: () => void
  onPickDate: () => void
  onReceipt: () => void
  onUnpay: () => void
}

/** Кнопки строки: одна высота (.btn), на широком экране «Чек / Оплачено / Указать дату оплаты» в одну линию. */
export function PaymentRowActions({ occurrence, busy, placement, onPaidToday, onPickDate, onReceipt, onUnpay }: Props) {
  const btn = (primary = false) =>
    `btn ${placement === 'slip' ? 'max-w-full flex-1' : 'shrink-0'} ${primary ? 'btn-primary' : ''}`

  const dateLabel = placement === 'slip' ? 'Дата оплаты' : 'Указать дату оплаты'
  const dateAria =
    occurrence.status === 'unpaid'
      ? `Указать дату оплаты для «${occurrence.title}»`
      : `Изменить дату оплаты для «${occurrence.title}»`

  const receipt = (
    <button type="button" className={btn()} onClick={onReceipt} aria-label={`Чек для «${occurrence.title}»`}>
      {placement === 'slip' && occurrence.has_receipt ? 'Чек есть' : 'Чек'}
    </button>
  )
  const actions =
    occurrence.status === 'unpaid' ? (
      <>
        <button
          type="button"
          className={btn(true)}
          onClick={onPaidToday}
          disabled={busy}
          title={placement === 'table' ? 'Отметить оплату сегодняшней датой' : undefined}
        >
          Оплачено
        </button>
        <button type="button" className={btn()} onClick={onPickDate} disabled={busy} aria-label={dateAria}>
          {dateLabel}
        </button>
      </>
    ) : (
      <>
        <button type="button" className={btn()} onClick={onPickDate} disabled={busy} aria-label={dateAria}>
          {dateLabel}
        </button>
        <button type="button" className={btn()} onClick={onUnpay} disabled={busy}>
          Отменить оплату
        </button>
      </>
    )

  return (
    <div
      className={
        placement === 'slip'
          ? 'flex w-full flex-wrap items-stretch gap-1'
          : 'inline-flex max-w-full flex-nowrap items-stretch justify-end gap-1'
      }
      role="group"
      aria-label={`Действия для «${occurrence.title}»`}
    >
      {placement === 'table' ? (
        <>
          {receipt}
          {actions}
        </>
      ) : (
        <>
          {actions}
          {receipt}
        </>
      )}
    </div>
  )
}
