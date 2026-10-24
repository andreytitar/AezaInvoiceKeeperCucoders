import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, unwrap, type Occurrence, type Schemas } from '../api/client'
import { formatDate } from '../i18n/format'
import { useToast } from '../store/toast'
import { Button, Dialog, EmptyState, Input, Skeleton, dialogActionsCls } from './ui'
import { Icon } from './Icon'

type Receipt = Schemas['ReceiptOut']
const MAX = 5 * 1024 * 1024
export function ReceiptDialog({
  occurrence,
  onClose,
  onChanged,
}: {
  occurrence: Occurrence | null
  onClose: () => void
  onChanged: () => void
}) {
  return (
    <Dialog open={!!occurrence} onClose={onClose} title="Чек к оплате">
      {occurrence && (
        <ReceiptForm key={occurrence.id} occurrence={occurrence} onClose={onClose} onChanged={onChanged} />
      )}
    </Dialog>
  )
}
function ReceiptForm({
  occurrence,
  onClose,
  onChanged,
}: {
  occurrence: Occurrence
  onClose: () => void
  onChanged: () => void
}) {
  const toast = useToast()
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [loading, setLoading] = useState(occurrence.has_receipt)
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!occurrence.has_receipt) return
    let cancelled = false
    api
      .GET('/api/v1/payment-occurrences/{occurrence_id}/receipt', {
        params: { path: { occurrence_id: occurrence.id } },
      })
      .then((result) => {
        if (cancelled) return
        if (result.error) {
          setError('Не удалось загрузить чек')
          return
        }
        setReceipt(result.data ?? null)
        setUrl(result.data?.url ?? '')
      })
      .catch(() => {
        if (!cancelled) setError('Не удалось загрузить чек')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [occurrence.id, occurrence.has_receipt])
  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (file && file.size > MAX) {
      setError('Файл больше 5 МБ')
      return
    }
    const form = new FormData()
    if (url.trim() && url.trim() !== receipt?.url) form.append('url', url.trim())
    if (file) form.append('file', file)
    if (!form.has('url') && !form.has('file')) {
      setError('Укажите ссылку или выберите файл')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await fetch(`/api/v1/payment-occurrences/${occurrence.id}/receipt`, {
        method: 'PUT',
        body: form,
        credentials: 'same-origin',
      })
      const body = await result.json().catch(() => ({}))
      if (!result.ok)
        throw new ApiError(
          result.status,
          body?.error?.code ?? 'error',
          body?.error?.message ?? `Ошибка ${result.status}`,
        )
      setReceipt(body)
      setFile(null)
      toast('ok', 'Чек сохранён')
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    setBusy(true)
    try {
      unwrap(
        await api.DELETE('/api/v1/payment-occurrences/{occurrence_id}/receipt', {
          params: { path: { occurrence_id: occurrence.id } },
        }),
      )
      setReceipt(null)
      setUrl('')
      toast('ok', 'Чек удалён')
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={save}>
      <p className="text-sm text-ink-soft">
        {occurrence.title} · срок <span className="num">{formatDate(occurrence.due_date)}</span>
      </p>
      {loading ? (
        <Skeleton className="my-5 h-20" />
      ) : receipt ? (
        <div className="my-5 space-y-3 rounded-lg border border-rule bg-paper p-3 text-sm">
          {receipt.url && (
            <a
              href={receipt.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="flex items-start gap-2 underline [overflow-wrap:anywhere]"
            >
              <Icon name="link" />
              {receipt.url}
            </a>
          )}
          {receipt.file_url && (
            <p>
              <a href={receipt.file_url} target="_blank" rel="noopener" className="underline [overflow-wrap:anywhere]">
                {receipt.file_name}
              </a>{' '}
              <span className="num text-xs text-ink-soft">({Math.ceil((receipt.size ?? 0) / 1024)} КБ)</span>
            </p>
          )}
        </div>
      ) : (
        <EmptyState title="Чек не прикреплён" icon={<Icon name="receipt" />} />
      )}
      <label className="label" htmlFor="r-url">
        Ссылка на чек
      </label>
      <Input
        id="r-url"
        type="url"
        className="mb-4"
        placeholder="https://…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={loading}
      />
      <label className="label" htmlFor="r-file">
        Файл (PNG, JPG, PDF до 5 МБ)
      </label>
      <Input
        id="r-file"
        type="file"
        accept="image/png,image/jpeg,application/pdf"
        className="mb-3 max-w-full text-xs"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        disabled={loading}
      />
      {error && (
        <p className="mt-3 text-sm text-overdue" role="alert">
          {error}
        </p>
      )}
      <div className={dialogActionsCls}>
        {receipt && (
          <Button variant="danger" onClick={remove} disabled={busy}>
            Удалить чек
          </Button>
        )}
        <Button onClick={onClose} disabled={busy}>
          Закрыть
        </Button>
        <Button type="submit" variant="primary" loading={busy} disabled={loading}>
          Сохранить
        </Button>
      </div>
    </form>
  )
}
