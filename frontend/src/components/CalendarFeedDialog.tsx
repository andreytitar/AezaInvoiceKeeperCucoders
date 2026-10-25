import QRCode from 'qrcode'
import { useEffect, useState } from 'react'
import { Icon } from './Icon'
import { Button, Dialog, Skeleton } from './ui'

/** Google accepts an https ICS URL in cid, rather than webcal or /calendar/r. */
function googleSubscribeHref(icsUrl: string): string {
  return `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(icsUrl)}`
}

function FeedQr({ url }: { url: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void QRCode.toDataURL(url, {
      margin: 2,
      width: 256,
      errorCorrectionLevel: 'M',
      color: { dark: '#000000', light: '#ffffff' },
    }).then((data) => {
      if (!cancelled) setSrc(data)
    })
    return () => {
      cancelled = true
    }
  }, [url])
  if (!src) return <Skeleton className="mx-auto h-64 w-64 max-w-full rounded-xl" />
  return (
    <img
      src={src}
      alt="QR-код ссылки на календарь платежей"
      width={256}
      height={256}
      className="mx-auto block max-w-full rounded-xl border border-rule bg-white p-2"
    />
  )
}

type Feed = { url: string; webcal_url: string }

export function CalendarFeedDialog({
  feed,
  busy,
  onClose,
  onCopy,
  onRotate,
}: {
  feed: Feed | null
  busy: boolean
  onClose: () => void
  onCopy: () => void
  onRotate: () => void
}) {
  return (
    <Dialog open={!!feed} onClose={onClose} title="Календарь в телефоне" className="calendar-feed-dialog mobile-menu-dialog md:!m-auto md:max-w-lg">
      {feed && (
        <>
          <p className="text-sm text-ink-soft">
            Все сроки появятся в Google или Apple Календаре с напоминанием за 3 дня и в день оплаты. Календарь обновляется
            автоматически. Ссылка личная — не пересылайте её.
          </p>
          <div className="mt-5 flex flex-col items-center gap-3">
            <FeedQr url={feed.url} />
            <Button variant="ghost" size="sm" onClick={onRotate} loading={busy}>
              Получить новую ссылку
            </Button>
            <p className="max-w-xs text-center text-xs text-ink-soft">
              После обновления старая подписка перестанет работать. Отсканируйте QR камерой или откройте календарь ниже.
            </p>
          </div>
          <div className="mt-5 flex min-w-0 items-stretch gap-2">
            <a className="btn btn-secondary min-h-11 min-w-0 flex-1 justify-center px-2 text-center text-sm" href={feed.webcal_url}>
              Apple Календарь
            </a>
            <a
              className="btn btn-secondary min-h-11 min-w-0 flex-1 justify-center px-2 text-center text-sm"
              href={googleSubscribeHref(feed.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Google Календарь
            </a>
            <Button variant="secondary" className="shrink-0 whitespace-nowrap" onClick={onCopy}>
              <Icon name="link" />
              Скопировать
            </Button>
          </div>
          <code className="num mt-2 block whitespace-normal break-all text-xs text-ink-soft">{feed.url}</code>
        </>
      )}
    </Dialog>
  )
}
