import { useEffect, useRef, useState } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'

type Status = Schemas['TelegramStatus']
type Code = Schemas['LinkCode']

function CopyLine({ text }: { text: string }) {
  const toast = useToast()
  return (
    <div className="flex gap-2 items-center mt-2">
      <code className="num text-sm border border-rule bg-paper px-2 py-1 rounded-sm flex-1 break-all select-all">{text}</code>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => {
          navigator.clipboard?.writeText(text).then(() => toast('ok', 'Скопировано'), () => toast('error', 'Не удалось скопировать'))
        }}
      >
        Копировать
      </button>
    </div>
  )
}

/** Привязка Telegram без ввода id: ссылка для пользователя и /bind для чата напоминаний. */
export function TelegramDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const { isAdmin, me } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState<Status | null>(null)
  const [myCode, setMyCode] = useState<Code | null>(null)
  const [chatCode, setChatCode] = useState<Code | null>(null)

  const load = () => api.GET('/api/v1/telegram/status').then((r) => r.data && setStatus(r.data))
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open) {
      if (!d.open) d.showModal()
      setMyCode(null)
      setChatCode(null)
      load()
    } else if (d.open) d.close()
  }, [open])

  const linkMe = async () => {
    try {
      const c = unwrap(await api.POST('/api/v1/telegram/link'))
      setMyCode(c)
      if (c.url) window.open(c.url, '_blank', 'noopener')
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    }
  }
  const unlink = async () => {
    await api.DELETE('/api/v1/telegram/link')
    toast('ok', 'Telegram отвязан')
    load()
  }
  const bindChat = async () => {
    try {
      setChatCode(unwrap(await api.POST('/api/v1/telegram/chat-link')))
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Ошибка')
    }
  }

  return (
    <dialog ref={ref} onClose={onClose} className="sheet m-auto w-[min(94vw,32rem)] p-0 text-ink backdrop:bg-black/40 shadow-[4px_4px_0_var(--ink)]" aria-labelledby="tg-title">
      <div className="p-5">
        <h2 id="tg-title" className="font-serif text-xl font-bold">Telegram</h2>
        {!status ? (
          <p className="text-sm text-ink-soft num mt-3">Загрузка…</p>
        ) : (
          <>
            <p className="text-sm text-ink-soft mt-1">
              {status.dry_run
                ? 'Бот не настроен (TELEGRAM_BOT_TOKEN пуст): сообщения пишутся в лог worker.'
                : <>Бот <span className="num">@{status.bot_username ?? '…'}</span> подключён.</>}
            </p>

            <section className="mt-4 border-t border-rule pt-3">
              <h3 className="font-semibold">Мой аккаунт</h3>
              {status.me_linked ? (
                <p className="text-sm mt-1">
                  Telegram привязан: можно нажимать «Оплачено» под напоминаниями и спрашивать бота.{' '}
                  <button className="underline text-ink-soft" onClick={unlink}>Отвязать</button>
                </p>
              ) : (
                <>
                  <p className="text-sm mt-1">Привяжите Telegram, чтобы отмечать оплату кнопкой и спрашивать бота в личке.</p>
                  {!myCode ? (
                    <button className="btn btn-primary btn-sm mt-2" onClick={linkMe}>Привязать Telegram</button>
                  ) : myCode.url ? (
                    <p className="text-sm mt-2">
                      Откройте <a className="underline" href={myCode.url} target="_blank" rel="noopener">{myCode.url}</a> и нажмите «Start».
                      Ссылка действует 15 минут. <button className="underline text-ink-soft" onClick={load}>Проверить</button>
                    </p>
                  ) : (
                    <>
                      <p className="text-sm mt-2">Отправьте боту в личку (код действует 15 минут):</p>
                      <CopyLine text={myCode.command} />
                    </>
                  )}
                </>
              )}
            </section>

            {isAdmin && (
              <section className="mt-4 border-t border-rule pt-3">
                <h3 className="font-semibold">Чат для напоминаний</h3>
                <p className="text-xs text-ink-soft">Сюда приходят напоминания и сводка по понедельникам в 9:00.</p>
                <p className="text-sm mt-1">
                  {status.chat_bound
                    ? <>Сейчас: <b>{status.chat_title ?? (status.chat_source === 'env' ? 'чат из .env' : 'группа')}</b>{status.chat_source === 'env' && ' (TELEGRAM_CHAT_ID)'}.</>
                    : me?.team?.kind === 'sandbox'
                      ? 'Группа не привязана — напоминания приходят администратору в личку.'
                      : 'Чат не подключён — напоминаниям некуда приходить.'}
                </p>
                {!chatCode ? (
                  <span className="flex flex-wrap gap-2 mt-2">
                    <button className="btn btn-sm" onClick={bindChat}>{status.chat_bound ? 'Подключить другой чат' : 'Подключить чат'}</button>
                    {status.chat_bound && (
                      <button
                        className="btn btn-sm btn-ghost"
                        onClick={async () => {
                          const r = await api.POST('/api/v1/admin/send-digest')
                          toast(r.data?.sent ? 'ok' : 'error', r.data?.sent ? 'Сводка отправлена в чат' : 'Сводку отправить не удалось')
                        }}
                      >
                        Отправить сводку сейчас
                      </button>
                    )}
                  </span>
                ) : (
                  <>
                    <p className="text-sm mt-2">Добавьте бота в группу и отправьте там (код действует 15 минут):</p>
                    <CopyLine text={chatCode.command} />
                    {chatCode.url && (
                      <p className="text-sm mt-2">
                        <a className="underline" href={chatCode.url} target="_blank" rel="noopener">Добавить бота в группу</a>
                      </p>
                    )}
                  </>
                )}
              </section>
            )}

            <section className="mt-4 border-t border-rule pt-3 text-sm">
              <h3 className="font-semibold">Что спросить у бота</h3>
              <ul className="num text-xs mt-1 space-y-0.5 text-ink-soft">
                <li>/topay — что и когда оплатить</li>
                <li>/overdue — что просрочено</li>
                <li>/week — ближайшие 7 дней</li>
                <li>/paid — что оплачено за 30 дней</li>
                <li>/summary — итоги по валютам</li>
                {isAdmin && <li>/add аренда 55000 руб каждое 5-е — добавить платёж</li>}
              </ul>
            </section>
          </>
        )}
        <div className="mt-5 flex justify-end">
          <button className="btn" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </dialog>
  )
}
