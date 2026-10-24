import { useState, type FormEvent } from 'react'
import { api, unwrap, type RecurringPayment } from '../api/client'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  DateInput,
  Dialog,
  EmptyState,
  ErrorNote,
  Input,
  Loading,
  Menu,
  MenuItem,
  PageTitle,
  Select,
  Table,
} from '../components/ui'
import { Icon } from '../components/Icon'
import { useLoad } from '../hooks/useLoad'
import { useServerToday } from '../hooks/useServerToday'
import { CURRENCIES, RECURRENCE_NAMES, formatDate, formatMoney } from '../i18n/format'
import { useToast } from '../store/toast'

type Form = { title: string; amount: string; currency: string; first_due_date: string; recurrence: string }

export function RecurringPaymentsPage() {
  const toast = useToast()
  const { today } = useServerToday()
  const [showDeleted, setShowDeleted] = useState(false)
  const list = useLoad(
    async () =>
      unwrap(await api.GET('/api/v1/recurring-payments', { params: { query: { include_deleted: showDeleted } } })),
    [showDeleted],
  )
  const empty: Form = { title: '', amount: '', currency: 'RUB', first_due_date: '', recurrence: 'monthly' }
  const [form, setForm] = useState<Form>(empty)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<RecurringPayment | null>(null)
  const [editing, setEditing] = useState<RecurringPayment | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const startEdit = (p: RecurringPayment) => {
    setEditing(p)
    setFormOpen(true)
    setError(null)
    setForm({
      title: p.title,
      amount: p.amount,
      currency: p.currency,
      first_due_date: p.first_due_date,
      recurrence: p.recurrence,
    })
  }
  const cancelEdit = () => {
    setEditing(null)
    setFormOpen(false)
    setForm(empty)
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    if (editing) {
      try {
        const p = unwrap(
          await api.PATCH('/api/v1/recurring-payments/{payment_id}', {
            params: { path: { payment_id: editing.id } },
            body: {
              title: form.title.trim(),
              amount: form.amount.replace(',', '.').replace(/\s/g, ''),
              currency: form.currency as 'RUB',
            },
          }),
        )
        toast('ok', `«${p.title}» обновлён: новые значения действуют с ближайшего неоплаченного периода`)
        cancelEdit()
        list.reload()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Ошибка')
      } finally {
        setBusy(false)
      }
      return
    }
    try {
      const p = unwrap(
        await api.POST('/api/v1/recurring-payments', {
          body: {
            title: form.title.trim(),
            amount: form.amount.replace(',', '.').replace(/\s/g, ''),
            currency: form.currency as 'RUB',
            first_due_date: form.first_due_date || today,
            recurrence: form.recurrence as 'monthly',
          },
        }),
      )
      toast('ok', `Платёж «${p.title}» добавлен, ближайший срок ${formatDate(p.next_due_date)}`)
      setForm(empty)
      setFormOpen(false)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (p: RecurringPayment) => {
    setBusy(true)
    try {
      unwrap(await api.DELETE('/api/v1/recurring-payments/{payment_id}', { params: { path: { payment_id: p.id } } }))
      toast('ok', `Платёж «${p.title}» прекращён, история сохранена`)
      setDeleting(null)
      list.reload()
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const actions = (p: RecurringPayment) =>
    !p.is_deleted && (
      <Menu label={`Действия: ${p.title}`}>
        <MenuItem onClick={() => startEdit(p)}>
          <Icon name="edit" /> Изменить
        </MenuItem>
        <MenuItem danger onClick={() => setDeleting(p)}>
          <Icon name="trash" /> Удалить
        </MenuItem>
      </Menu>
    )

  return (
    <>
      <PageTitle
        aside={
          <Button
            variant="primary"
            onClick={() => {
              cancelEdit()
              setFormOpen(true)
            }}
          >
            <Icon name="plus" /> Новый платёж
          </Button>
        }
      >
        Регулярные платежи
      </PageTitle>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">Шаблоны расходов и даты следующих оплат</p>
        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-sm">
          <Checkbox checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
          Показать прекращённые
        </label>
      </div>
      <Card className="min-w-0">
        {list.error ? (
          <div className="p-4">
            <ErrorNote text={list.error} onRetry={list.reload} />
          </div>
        ) : !list.data ? (
          <Loading />
        ) : !list.data.length ? (
          <EmptyState
            title="Платежей пока нет"
            hint="Добавьте регулярный платёж, чтобы команда видела ближайшие сроки."
            icon={<Icon name="repeat" />}
          />
        ) : (
          <>
            <ul className="divide-y divide-rule min-[1100px]:hidden">
              {list.data.map((p) => (
                <li key={p.id} className={`min-w-0 p-4 ${p.is_deleted ? 'text-ink-soft' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold break-words">{p.title}</p>
                      <p className="num mt-1 whitespace-nowrap text-base">{formatMoney(p.amount, p.currency)}</p>
                    </div>
                    {actions(p)}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="text-ink-soft">
                      {RECURRENCE_NAMES[p.recurrence]}, {p.anchor_day}-го
                    </span>
                    {p.is_deleted ? (
                      <Badge tone="neutral">Прекращён</Badge>
                    ) : (
                      <span className="num whitespace-nowrap">{formatDate(p.next_due_date)}</span>
                    )}
                  </div>
                  {p.is_deleted && <p className="mt-2 text-xs">Прекращён {formatDate(p.deleted_at?.slice(0, 10))}</p>}
                </li>
              ))}
            </ul>
            <Table className="hidden w-full min-[1100px]:table">
              <thead>
                <tr>
                  <th className="w-full">Название</th>
                  <th className="text-right">Сумма</th>
                  <th>Периодичность</th>
                  <th>Ближайший срок</th>
                  <th>
                    <span className="sr-only">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.map((p) => (
                  <tr key={p.id} className={p.is_deleted ? 'text-ink-soft' : ''}>
                    <td className="font-semibold [overflow-wrap:anywhere]">
                      {p.title}
                      {p.is_deleted && (
                        <span className="mt-1 block text-xs font-normal">
                          Прекращён {formatDate(p.deleted_at?.slice(0, 10))}
                        </span>
                      )}
                    </td>
                    <td className="num whitespace-nowrap text-right">{formatMoney(p.amount, p.currency)}</td>
                    <td className="whitespace-nowrap text-sm">
                      {RECURRENCE_NAMES[p.recurrence]}
                      <span className="text-ink-soft">, {p.anchor_day}-го</span>
                    </td>
                    <td className="num whitespace-nowrap text-sm">
                      {p.is_deleted ? <Badge tone="neutral">Прекращён</Badge> : formatDate(p.next_due_date)}
                    </td>
                    <td className="text-right">{actions(p)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Card>
      <Dialog open={formOpen} onClose={cancelEdit} title={editing ? 'Изменить платёж' : 'Новый регулярный платёж'}>
        <form onSubmit={submit} className="space-y-4">
          {editing && (
            <p className="text-sm text-ink-soft">
              Оплаченные и прошедшие периоды сохранят прежнюю сумму. Срок и периодичность не меняются.
            </p>
          )}
          <div>
            <label className="label" htmlFor="p-title">
              Название
            </label>
            <Input
              id="p-title"
              required
              maxLength={200}
              placeholder="Аренда офиса"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_6.5rem] gap-3">
            <div>
              <label className="label" htmlFor="p-amount">
                Сумма
              </label>
              <Input
                id="p-amount"
                className="num"
                inputMode="decimal"
                required
                placeholder="55 000,00"
                pattern="^\s*\d[\d\s]*([.,]\d{1,2})?\s*$"
                title="Число, не больше двух знаков после запятой"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="p-cur">
                Валюта
              </label>
              <Select id="p-cur" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                {CURRENCIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </div>
          </div>
          <div>
            <label className="label" htmlFor="p-date">
              Дата ближайшей оплаты
            </label>
            <DateInput
              key={`${formOpen}:${editing?.id ?? 'new'}`}
              id="p-date"
              required
              disabled={!!editing}
              value={form.first_due_date}
              onChange={(value) => setForm({ ...form, first_due_date: value })}
            />
            <p className="mt-2 text-xs text-ink-soft">
              Следующие сроки считаются от этого числа; если его нет в месяце — последний день месяца.
            </p>
          </div>
          <div>
            <label className="label" htmlFor="p-rec">
              Периодичность
            </label>
            <Select
              id="p-rec"
              disabled={!!editing}
              value={form.recurrence}
              onChange={(e) => setForm({ ...form, recurrence: e.target.value })}
            >
              {Object.entries(RECURRENCE_NAMES).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </div>
          {error && (
            <p className="text-sm text-overdue" role="alert">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={cancelEdit} disabled={busy}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" loading={busy}>
              {editing ? 'Сохранить' : 'Добавить платёж'}
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        title="Удалить регулярный платёж?"
        body={
          deleting && (
            <>
              «{deleting.title}» перестанет создавать новые периоды и напоминания. Оплаченные и прошедшие периоды
              останутся в истории, будущие неоплаченные будут удалены.
            </>
          )
        }
        confirmText="Удалить"
        danger
        busy={busy}
        onConfirm={() => deleting && remove(deleting)}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}
