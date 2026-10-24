import { useEffect, useState } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { useAuth } from '../store/auth'
import { useToast } from '../store/toast'
import { Button, Dialog, Skeleton, dialogBtnCls } from './ui'

type Status = Schemas['TelegramStatus']
type Code = Schemas['LinkCode']

function CopyLine({ text }: { text: string }) {
  const toast = useToast()
  return (
    <div className="flex flex-col gap-2 mt-2 desk:flex-row desk:items-center">
      <code className="num whitespace-normal text-sm border border-rule bg-paper px-2 py-1 rounded-sm min-w-0 break-all select-all">
        {text}
      </code>
      <Button
        type="button"
        className={dialogBtnCls}
        onClick={() => {
          navigator.clipboard?.writeText(text).then(
            () => toast('ok', 'Скопировано'),
            () => toast('error', 'Не удалось скопировать'),
          )
        }}
      >
        Копировать
      </Button>
    </div>
  )
}

/** Привязка Telegram без ввода id: ссылка для пользователя и /bind для чата напоминаний. */
export function TelegramDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { isAdmin, me } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState<Status | null>(null)
  const [myCode, setMyCode] = useState<Code | null>(null)
  const [chatCode, setChatCode] = useState<Code | null>(null)

  const load = () => api.GET('/api/v1/telegram/status').then((r) => r.data && setStatus(r.data))
  useEffect(() => {
    if (open) {
      setMyCode(null)
      setChatCode(null)
      load()
    }
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
    <Dialog open={open} onClose={onClose} title="Telegram">
      <div>
        {!status ? (
          <Skeleton className="mt-3 h-40" />
        ) : (
          <>
            <p className="text-sm text-ink-soft mt-1">
              {status.dry_run ? (
                'Telegram не подключён. Обратитесь к администратору сервиса, чтобы включить напоминания.'
              ) : (
                <>
                  Бот <span className="num">@{status.bot_username ?? '…'}</span> подключён.
                </>
              )}
            </p>

            <section className="mt-4 border-t border-rule pt-3">
              <h3 className="font-semibold">Мой аккаунт</h3>
              {status.me_linked ? (
                <p className="text-sm mt-1">
                  Telegram привязан: можно нажимать «Оплачено» под напоминаниями и спрашивать бота.{' '}
                  <Button className="underline text-ink-soft" onClick={unlink}>
                    Отвязать
                  </Button>
                </p>
              ) : (
                <>
                  <p className="text-sm mt-1">
                    Привяжите Telegram, чтобы отмечать оплату кнопкой и спрашивать бота в личке.
                  </p>
                  {!myCode ? (
                    <Button className={`${dialogBtnCls} btn-primary mt-2`} onClick={linkMe}>
                      Привязать Telegram
                    </Button>
                  ) : myCode.url ? (
                    <p className="text-sm mt-2">
                      Откройте{' '}
                      <a className="underline break-all" href={myCode.url} target="_blank" rel="noopener">
                        {myCode.url}
                      </a>{' '}
                      и нажмите «Start». Ссылка действует 15 минут.{' '}
                      <Button className="underline text-ink-soft" onClick={load}>
                        Проверить
                      </Button>
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

            {isAdmin && me && me.team?.kind === 'sandbox' && me.invite_code && (
              <section className="mt-4 border-t border-rule pt-3">
                <h3 className="font-semibold">Пригласить коллегу</h3>
                <p className="text-sm mt-1">
                  На сайте коллега выбирает «Войти по коду приглашения». В боте отправляет команду ниже.
                </p>
                <CopyLine text={me.invite_code} />
                <CopyLine text={`/join ${me.invite_code}`} />
              </section>
            )}

            {isAdmin && (
              <section className="mt-4 border-t border-rule pt-3">
                <h3 className="font-semibold">Чат для напоминаний</h3>
                <p className="text-xs text-ink-soft">Сюда приходят напоминания и сводка по понедельникам в 9:00.</p>
                <p className="text-sm mt-1">
                  {status.chat_bound ? (
                    <>
                      Сейчас: <b>{status.chat_title ?? (status.chat_source === 'env' ? 'чат из .env' : 'группа')}</b>
                      {status.chat_source === 'env' && ' (TELEGRAM_CHAT_ID)'}.
                    </>
                  ) : me?.team?.kind === 'sandbox' ? (
                    'Группа не привязана — напоминания приходят администратору в личку.'
                  ) : (
                    'Чат не подключён — напоминаниям некуда приходить.'
                  )}
                </p>
                {!chatCode ? (
                  <span className="flex flex-wrap gap-2 mt-2">
                    <Button className={dialogBtnCls} onClick={bindChat}>
                      {status.chat_bound ? 'Подключить другой чат' : 'Подключить чат'}
                    </Button>
                    {status.chat_bound && (
                      <Button
                        className={`${dialogBtnCls} btn-ghost`}
                        onClick={async () => {
                          const r = await api.POST('/api/v1/admin/send-digest')
                          toast(
                            r.data?.sent ? 'ok' : 'error',
                            r.data?.sent ? 'Сводка отправлена в чат' : 'Сводку отправить не удалось',
                          )
                        }}
                      >
                        Отправить сводку сейчас
                      </Button>
                    )}
                  </span>
                ) : (
                  <>
                    <p className="text-sm mt-2">Добавьте бота в группу и отправьте там (код действует 15 минут):</p>
                    <CopyLine text={chatCode.command} />
                    {chatCode.url && (
                      <p className="text-sm mt-2">
                        <a className="underline" href={chatCode.url} target="_blank" rel="noopener">
                          Добавить бота в группу
                        </a>
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
          <Button className={dialogBtnCls} onClick={onClose}>
            Закрыть
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
