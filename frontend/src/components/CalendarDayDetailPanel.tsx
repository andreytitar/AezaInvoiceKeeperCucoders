import type { Occurrence } from '../api/client'
import { formatDate, formatMoney } from '../i18n/format'
import { CalendarOccurrenceDetail } from './CalendarOccurrenceDetail'
import { Icon } from './Icon'
import { EmptyState } from './ui'

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
    <div className="min-w-0 p-4" aria-label="Платежи выбранного дня">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-rule pb-3">
        <h2 className="text-base font-semibold">{selectedDay ? formatDate(selectedDay) : 'Платежи дня'}</h2>
        <span className="num text-xs text-ink-soft">{day?.occurrences.length ?? 0}</span>
      </div>
      {!day?.occurrences.length ? (
        <EmptyState title="Платежей нет" hint="На этот день ничего не запланировано." icon={<Icon name="calendar" />} />
      ) : (
        <>
          {day.occurrences.length > 1 && (
            <ul className="mb-4 space-y-1.5" aria-label="Выберите платёж">
              {day.occurrences.map((o) => (
                <li key={o.id}>
                  <button
                    type="button"
                    className={`flex min-h-11 w-full min-w-0 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                      occ?.id === o.id ? 'border-accent bg-accent/10' : 'border-rule bg-paper-2 hover:bg-paper'
                    }`}
                    onClick={() => onSelectOccurrence(o)}
                    aria-pressed={occ?.id === o.id}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${o.status === 'paid' ? 'bg-paid' : o.is_overdue ? 'bg-overdue' : 'bg-accent'}`} />
                      <span className="min-w-0 break-words font-medium">{o.title}</span>
                    </span>
                    <span className="num shrink-0 whitespace-nowrap">{formatMoney(o.amount, o.currency)}</span>
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
    </div>
  )
}
