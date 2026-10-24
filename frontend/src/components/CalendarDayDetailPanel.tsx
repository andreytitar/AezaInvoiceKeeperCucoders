import type { Occurrence } from '../api/client'
import { formatDate, formatMoney } from '../i18n/format'
import { CalendarOccurrenceDetail } from './CalendarOccurrenceDetail'

type DayData = {
  date: string
  occurrences: Occurrence[]
}

type Props = {
  selectedDay: string | null
  day: DayData | undefined
  selectedOccurrence: Occurrence | null
  busy: boolean
  onSelectOccurrence: (o: Occurrence) => void
  onPayToday: (o: Occurrence) => void
  onPayWithDate: (o: Occurrence) => void
  onUnpay: (o: Occurrence) => void
  onChangeDate: (o: Occurrence) => void
}

export function CalendarDayDetailPanel({
  selectedDay,
  day,
  selectedOccurrence,
  busy,
  onSelectOccurrence,
  onPayToday,
  onPayWithDate,
  onUnpay,
  onChangeDate,
}: Props) {
  const occ = selectedOccurrence

  return (
    <div className="cal-detail-panel min-w-0 p-4 pb-3" aria-label="Платежи выбранного дня">
      {!selectedDay ? (
        <p className="text-sm text-ink-soft py-6 text-center">Выберите день</p>
      ) : (
        <>
          <h2 className="font-sans text-lg font-semibold border-b border-rule pb-2 mb-3">
            {formatDate(selectedDay)}
          </h2>
          {!day?.occurrences.length ? (
            <p className="text-sm text-ink-soft">В этот день платежей нет.</p>
          ) : (
            <>
              {day.occurrences.length > 1 && (
                <ul className="mb-4 flex flex-col gap-1" role="list">
                  {day.occurrences.map((o) => (
                    <li key={o.id}>
                      <button
                        type="button"
                        className={`w-full text-left border border-rule px-2 py-1.5 text-sm min-h-[44px] ${
                          occ?.id === o.id ? 'bg-paper border-ink' : 'bg-paper-2 hover:bg-paper'
                        }`}
                        onClick={() => onSelectOccurrence(o)}
                        aria-current={occ?.id === o.id ? 'true' : undefined}
                      >
                        <span className="font-medium">{o.title}</span>
                        <span className="num text-ink-soft ml-2">{formatMoney(o.amount, o.currency)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {occ && (
                <CalendarOccurrenceDetail
                  occurrence={occ}
                  busy={busy}
                  onPayToday={() => onPayToday(occ)}
                  onPayWithDate={() => onPayWithDate(occ)}
                  onUnpay={() => onUnpay(occ)}
                  onChangeDate={() => onChangeDate(occ)}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
