import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, unwrap, type Occurrence, type Schemas } from '../api/client'
import { formatDate } from '../i18n/format'
import { useToast } from '../store/toast'
import { dialogActionsCls, dialogBtnCls, dialogCls } from './ui'

type Receipt = Schemas['ReceiptOut']
const MAX = 5 * 1024 * 1024

/** Чек к периоду: ссылка и/или файл (PNG, JPG, PDF до 5 МБ). */
export function ReceiptDialog({ occurrence, onClose, onChanged }: { occurrence: Occurrence | null; onClose: () => void; onChanged: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const toast = useToast()
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [loading, setLoading] = useState(false)
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (!occurrence) {
      if (d.open) d.close()
      return
    }
    if (!d.open) d.showModal()
    setReceipt(null)
    setUrl('')
    setFile(null)
    setError(null)
    setLoading(true)
    api
      .GET('/api/v1/payment-occurrences/{occurrence_id}/receipt', { params: { path: { occurrence_id: occurrence.id } } })
      .then((r) => {
        if (r.data) {
          setReceipt(r.data)
          setUrl(r.data.url ?? '')
        }
      })
      .finally(() => setLoading(false))
  }, [occurrence])

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!occurrence) return
    if (file && file.size > MAX) {
      setError('Файл больше 5 МБ')
      return
    }
    const form = new FormData()
    if (url.trim() && url.trim() !== receipt?.url) form.append('url', url.trim())
    if (file) form.append('file', file)
    if (!form.has("url") && !form.has("file")) {
      setError('Укажите ссылку или выберите файл')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/payment-occurrences/${occurrence.id}/receipt`, { method: 'PUT', body: form, credentials: 'same-origin' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new ApiError(res.status, body?.error?.code ?? 'error', body?.error?.message ?? `Ошибка ${res.status}`)
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
    if (!occurrence) return
    setBusy(true)
    try {
      unwrap(await api.DELETE('/api/v1/payment-occurrences/{occurrence_id}/receipt', { params: { path: { occurrence_id: occurrence.id } } }))
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
    <dialog ref={ref} onClose={onClose} className={`${dialogCls} win-window`} aria-labelledby="receipt-title">
      {occurrence && (
        <form className="p-4" onSubmit={save}>
          <h2 id="receipt-title" className="font-sans text-xl font-semibold">Чек к оплате</h2>
          <p className="text-sm text-ink-soft mt-1">
            {occurrence.title} · срок {formatDate(occurrence.due_date)}
          </p>
          {loading ? (
            <p className="text-sm text-ink-soft my-4 num">Загрузка…</p>
          ) : receipt ? (
            <div className="my-4 border-y border-rule py-3 text-sm space-y-1">
              {receipt.url && (
                <p>
                  Ссылка:{' '}
                  <a href={receipt.url} target="_blank" rel="noopener noreferrer nofollow" className="underline break-all">
                    {receipt.url}
                  </a>
                </p>
              )}
              {receipt.file_url && (
                <p>
                  Файл:{' '}
                  <a href={receipt.file_url} target="_blank" rel="noopener" className="underline">
                    {receipt.file_name}
                  </a>{' '}
                  <span className="text-ink-soft num">({Math.ceil((receipt.size ?? 0) / 1024)} КБ)</span>
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-ink-soft my-4">Чек не прикреплён.</p>
          )}
          <label className="label" htmlFor="r-url">Ссылка на чек</label>
          <input id="r-url" type="url" className="field mb-3" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <label className="label" htmlFor="r-file">Файл (PNG, JPG, PDF до 5 МБ)</label>
          <input id="r-file" type="file" accept="image/png,image/jpeg,application/pdf" className="text-sm mb-3 block" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {error && <p className="text-sm text-ink mb-3" role="alert">{error}</p>}
          <div className={dialogActionsCls}>
            {receipt ? (
              <button type="button" className={dialogBtnCls} onClick={remove} disabled={busy}>Удалить чек</button>
            ) : null}
            <button type="button" className={dialogBtnCls} onClick={onClose} disabled={busy}>Закрыть</button>
            <button className={`${dialogBtnCls} btn-primary`} disabled={busy}>{busy ? '…' : 'Сохранить'}</button>
          </div>
        </form>
      )}
    </dialog>
  )
}
