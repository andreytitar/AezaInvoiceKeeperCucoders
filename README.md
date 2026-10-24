# Invoice Keeper — напоминания о регулярных платежах

Система не даёт забыть об аренде, подписках и оплате серверов. Администратор вносит регулярные
платежи, за 3 дня до срока бот пишет в Telegram-чат, пользователи видят общий список, отмечают
оплату и следят за просрочками. Итоги считаются отдельно по каждой валюте (RUB, USD, EUR).

Хакатон Aeza, уровень Middle.

---

## Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Демо-доступы и данные](#демо-доступы-и-данные)
3. [Настройка Telegram-бота](#настройка-telegram-бота)
4. [Сценарий демонстрации](#сценарий-демонстрации)
5. [Тесты](#тесты)
6. [API](#api)
7. [Архитектура](#архитектура)
8. [Правила предметной области](#правила-предметной-области)
9. [Допущения и принятые решения](#допущения-и-принятые-решения)
10. [Реализованные возможности](#реализованные-возможности)
11. [Переменные окружения](#переменные-окружения)

---

## Быстрый старт

Требования: **Docker 24+ с Docker Compose v2**. Больше ничего ставить не нужно — фронтенд
собирается внутри образа, миграции и демо-данные применяются при старте.

```bash
git clone git@github.com:andreytitar/AezaInvoiceKeeperCucoders.git
cd AezaInvoiceKeeperCucoders
cp .env.example .env
docker compose up --build
```

Через ~1–2 минуты (первая сборка):

| Что | Адрес |
|---|---|
| Веб-панель | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/v1/docs |
| OpenAPI JSON | http://localhost:8000/api/v1/openapi.json |
| Состояние | http://localhost:8000/api/v1/health |

Без `TELEGRAM_BOT_TOKEN` приложение работает в режиме **«лог вместо отправки»**: напоминания
пишутся в лог worker (`docker compose logs -f worker`, строки `[DRY-RUN Telegram]`). Для реальной
отправки — см. [Настройка Telegram-бота](#настройка-telegram-бота).

Полезные команды (`make` необязателен, всё работает и через `docker compose`):

| Команда | Что делает |
|---|---|
| `make up` | собрать и запустить в фоне |
| `make down` | остановить (данные сохраняются в volume `pgdata`) |
| `make logs` | логи api и worker |
| `make test` | все тесты на реальном PostgreSQL в контейнере |
| `make seed` | повторно применить сид (идемпотентно) |
| `make openapi` | перегенерировать `openapi/openapi.yml` |
| `make clean` | остановить и **удалить** данные |

Порт меняется переменной `APP_PORT` в `.env`.

## Демо-доступы и данные

| Роль | Логин | Пароль |
|---|---|---|
| Администратор (из `.env`) | `admin` | `change-me-admin` |
| Пользователь | `ivan` | `user12345` |
| Пользователь | `maria` | `user12345` |

Пароли задаются в `.env` (`ADMIN_PASSWORD`, `SEED_USER_PASSWORD`). Смените их перед реальным использованием.

Сид (`SEED_ON_START=true`) создаётся один раз, даты считаются от «сегодня»:

| Платёж | Сумма | Что показывает |
|---|---|---|
| Аренда офиса | 55 000 RUB | период оплачен в срок, период оплачен с опозданием на 3 дня, ближайший — через 12 дней |
| Сервер Aeza | 25 USD | срок через 2 дня — напоминание уходит сразу |
| Подписка JetBrains | 9.99 EUR | просрочено на 5 дней |
| Облачное хранилище | 12.50 USD | якорь 31-го числа: 31 окт → 30 ноя → 31 дек |

## Настройка Telegram-бота

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → получите токен вида `123456:ABC…`.
2. Добавьте бота в нужный групповой чат (или напишите ему в личку `/start`).
3. Узнайте `chat_id`: напишите что-нибудь в чат и откройте
   `https://api.telegram.org/bot<ТОКЕН>/getUpdates` — значение `message.chat.id`
   (у групп отрицательное, например `-1001234567890`). Либо перешлите сообщение боту [@userinfobot](https://t.me/userinfobot).
4. Пропишите в `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=-1001234567890
   ```
5. `docker compose up -d` (контейнеры пересоздадутся с новыми переменными).

Сообщение содержит название, сумму, валюту и дату оплаты:

```
Напоминание об оплате

Сервер Aeza
Сумма: 25,00 $ (USD)
Дата оплаты: 26.10.2026 — через 2 дн.
```

### Подключение без ввода id

- **Чат для напоминаний.** Панель → «Telegram» → «Подключить чат» → добавьте бота в группу и отправьте там
  `/bind <код>`. Напоминания пойдут в эту группу (перекрывает `TELEGRAM_CHAT_ID`, который теперь необязателен).
- **Свой аккаунт.** Панель → «Telegram» → «Привязать Telegram» → откроется `t.me/<бот>?start=<код>`, нажмите Start.
  Коды одноразовые, живут 15 минут, привязки пишутся в журнал.

### Бот отвечает на вопросы

| Команда | Ответ |
|---|---|
| `/topay` | что и когда оплатить (с кнопками «Оплачено») и итог по валютам |
| `/overdue` | что просрочено |
| `/week` | платежи на ближайшие 7 дней |
| `/paid` | что оплачено за 30 дней |
| `/summary` | итоги по каждой валюте |
| `/add <фраза>` | добавить платёж (админ): `/add аренда 55000 руб каждое 5-е`, `/add сервер $25 28 числа`, `/add домен 12 usd ежегодно 01.12` — под ответом кнопка «Удалить этот платёж» |
| `/help` | справка |

В личке можно спрашивать словами: «что просрочено?», «покажи итоги». Отвечает участникам чата напоминаний
и привязанным пользователям, остальным — «нет доступа». Команды регистрируются в меню бота автоматически.

### Сводка на неделю

По понедельникам в 9:00 (`DIGEST_WEEKDAY`, `DIGEST_HOUR`) бот присылает в чат: что просрочено и что оплатить
на этой неделе, с кнопками «Оплачено». Одна сводка в неделю (ключ недели в БД); если Telegram недоступен —
повтор на следующем тике. Кнопка «Отправить сводку сейчас» в окне «Telegram» — для демо.

### Кнопка «Оплачено» в Telegram

Под каждым напоминанием есть inline-кнопка **«Оплачено»**. Нажатие отмечает период оплаченным
сегодняшней датой (в `APP_TIMEZONE`) по тем же правилам, что и панель, и редактирует сообщение:
«Оплачено …, отметил(а) ivan». Повторное нажатие ничего не ломает.

Нажимать могут только привязанные аккаунты: администратор указывает **Telegram user ID** в профиле
пользователя («Пользователи» → «Изменить»). Узнать свой id — написать [@userinfobot](https://t.me/userinfobot).
Нажатие от непривязанного аккаунта отклоняется всплывающим сообщением, данные не меняются.
Нажатия принимает worker через long polling (`TELEGRAM_POLLING_ENABLED=true`), смещение хранится в БД.
У бота не должно быть установленного webhook (`deleteWebhook`), иначе long polling не работает.

### Email-оповещения

Напоминание дублируется письмом с тем же содержимым (название, сумма, валюта, дата) — тем же механизмом
доставки (без дублей, с ретраями). Получатели: общий список `EMAIL_RECIPIENTS` и (при `EMAIL_TO_USERS=true`)
email из профилей пользователей. Для демо есть Mailpit:

```bash
# в .env
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_SECURITY=none
EMAIL_RECIPIENTS=team@example.com

docker compose --profile demo-mail up -d     # или make up-mail
open http://localhost:8025                   # входящие письма
```

Для настоящего SMTP задайте `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY=starttls|ssl`.

### Вебхуки

Администратор добавляет адреса в разделе «Вебхуки» (или `POST /api/v1/webhooks`) и выбирает события:
`payment.reminder`, `payment.paid`, `payment.unpaid`, `payment.overdue`. Пример тела:

```json
{
  "schema_version": "1",
  "event": "payment.paid",
  "event_id": "5b0c…",
  "occurred_at": "2026-10-24T09:12:00+00:00",
  "data": {"occurrence_id": "…", "recurring_payment_id": "…", "title": "Аренда офиса", "amount": "55000.00",
           "currency": "RUB", "due_date": "2026-11-05", "status": "paid", "paid_date": "2026-10-24", "days_until_due": 12}
}
```

Заголовки: `X-InvoiceKeeper-Event`, `Idempotency-Key` (= `event_id`, одинаковый при повторах одной доставки),
`X-InvoiceKeeper-Timestamp`, `X-InvoiceKeeper-Signature: sha256=<hex>` — HMAC-SHA256 от `timestamp + "." + body`
секретом вебхука (секрет хранится зашифрованным и не возвращается в API). Проверка на стороне получателя:

```python
expected = "sha256=" + hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
hmac.compare_digest(expected, signature)
```

Таймаут 10 с, без редиректов, повторы 1/5/15/60 мин, потом `dead`; журнал доставок — кнопка «Журнал».
`payment.overdue` приходит один раз на период, `payment.paid/unpaid` — на каждое изменение статуса.
Адреса loopback/private/link-local (в т. ч. `169.254.169.254`) запрещены — проверка при сохранении и перед
каждой отправкой. Для локального демо: `WEBHOOK_ALLOW_PRIVATE=true`.

### Slack / Discord / Mattermost

Напоминания можно дублировать в рабочий чат через incoming webhook — достаточно `.env`:

```env
CHAT_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX   # или https://discord.com/api/webhooks/…
CHAT_WEBHOOK_FORMAT=auto                                            # auto | slack | discord | mattermost
```

Формат определяется по хосту (Discord — `content` с `**жирным**`, Slack/Mattermost — `text` с `*жирным*`).
В БД вместо URL (в нём секретный токен) хранится только его отпечаток.

### Как добавить свой канал уведомлений

Ядро рассылки (очередь, дедупликация, ретраи, отмена при оплате) от канала не зависит. Новый канал — это:

1. Класс в `backend/app/infrastructure/channels/` с интерфейсом `NotificationChannel`:
   ```python
   class SmsChannel:
       name = "sms"                                   # попадёт в notification_deliveries.channel
       def recipients(self) -> list[str]: ...         # кому слать (телефоны, chat_id, id адресов)
       async def send(self, message: Notification, recipient: str) -> SendResult: ...
   ```
   `Notification` содержит название, сумму (`Decimal`), валюту, дату, `days_until_due`, `kind`;
   `SendResult(ok, error, external_id, retryable)`. Исключения из `send` ловятся диспетчером.
2. Регистрация в `build_channels()` (`channels/registry.py`) по настройке из `.env`.
3. Тест с `httpx.MockTransport` или фейком по образцу `tests/worker/test_chat_webhook.py`.

## Сценарий демонстрации

Проходит вживую на чистой установке:

1. **Войти администратором** — `admin` / `change-me-admin`.
2. **Добавить регулярный платёж** — «Регулярные платежи» → форма: название, сумма, валюта, дата
   ближайшей оплаты (например, послезавтра), периодичность → «Добавить».
3. **Получить напоминание в Telegram** — срок ≤ 3 дней, поэтому напоминание уходит сразу после
   создания (без бота — смотрите `docker compose logs -f worker app`, строку `[DRY-RUN Telegram]`).
4. **Войти пользователем и отметить оплату** — «Выйти» → `ivan` / `user12345` → вкладка
   «Что оплатить» → «Оплачено» (сегодня) или «Дата…» (выбрать дату).
5. **Показать просроченный платёж** — вкладка «Просрочено»: «Подписка JetBrains», красная пометка
   «! 5 дней», в карточке EUR — строка «Просрочено».
6. **Исправить фактическую дату оплаты** — отметьте «Подписку» оплаченной сегодня: в колонке
   «Просрочка» появится «опоздание 5 дней». Нажмите «Изменить дату» и поставьте дату не позже срока —
   просрочка пропадёт, срок не изменится.
7. **Показать следующий период с отдельным статусом** — вкладка «Все периоды»: у «Подписки»
   оплаченный период и следующий — «Не оплачено», со своим сроком.

### Автоматическая проверка приёмки

Скрипт проходит чек-лист критериев и демо-сценарий против запущенного стека (только стандартная
библиотека Python, создаёт и в конце удаляет тестовый платёж «Приёмка …»):

```bash
python3 scripts/acceptance.py            # --base http://localhost:8000 --admin admin:pass --user ivan:pass
```

Пункты, которые проверяются руками: сохранность после `docker compose down` / `up` (без `-v`),
доставка в настоящий Telegram (нужен токен бота).

### Машина времени: `APP_FAKE_TODAY`

Демо-инструмент, по умолчанию выключен. Подменяет «сегодня» для всего приложения (генерация
периодов, просрочки, напоминания, проверка «дата оплаты не в будущем»):

```bash
# в .env
APP_FAKE_TODAY=2026-12-01
docker compose up -d
```

В шапке панели рядом с датой появится пометка `[APP_FAKE_TODAY]`, в `/api/v1/health` — `"fake_today": true`.
Уберите значение, чтобы вернуться к реальной дате.

## Тесты

```bash
make test
# или
docker compose --profile test run --rm tests
```

Тесты запускаются на реальном PostgreSQL (отдельная база `invoice_keeper_test` в том же контейнере
`db`; SQLite не подходит из-за `SKIP LOCKED` и ограничений). Время подменяется `FixedClock`,
Telegram — `FakeChannel` и `httpx.MockTransport`.

| Набор | Что проверяет |
|---|---|
| `tests/unit` | даты от якоря (31 → 28/29 фев → 31, високосный год), просрочка, правила статусов, политика напоминаний, запрет `datetime.now()` вне `Clock`, отсутствие FastAPI/SQLAlchemy в `domain`, актуальность `openapi.yml` |
| `tests/integration` | вход/выход/сессии, rate limit, CSRF, матрица прав 401/403 **для каждого эндпоинта и роли**, CRUD пользователей, системный админ, платежи, PATCH периода, удаление, фильтры, итоги, сид |
| `tests/worker` | окно 3 дня, немедленное напоминание, отсутствие дублей при повторной проверке / рестарте / 4 параллельных worker'ах, сбой и ретрай с backoff, `dead`, зависшие доставки, оплаченные и удалённые не напоминают, Telegram-клиент |

Локально без Docker: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`,
поднять PostgreSQL и задать `TEST_DATABASE_URL`, затем `.venv/bin/pytest`.

## API

Все эндпоинты под префиксом `/api/v1`. Спецификация — [`openapi/openapi.yml`](openapi/openapi.yml)
(генерируется `make openapi`, тест падает, если файл устарел).

**Авторизация в Swagger:** кнопка **Authorize** → логин/пароль (OAuth2 password flow через
`POST /auth/token`) → «Try it out» работает для всех методов. Веб-панель использует HttpOnly-cookie.

| Метод и путь | Аноним | user | admin |
|---|---|---|---|
| `POST /auth/login`, `POST /auth/token` | ✔ | ✔ | ✔ |
| `GET /auth/me`, `POST /auth/logout` | 401 | ✔ | ✔ |
| `GET /recurring-payments` | 401 | ✔ | ✔ |
| `POST /recurring-payments`, `DELETE /recurring-payments/{id}` | 401 | 403 | ✔ |
| `GET /payment-occurrences`, `GET /payment-occurrences/{id}` | 401 | ✔ | ✔ |
| `PATCH /payment-occurrences/{id}` (только `status`, `paid_date`) | 401 | ✔ | ✔ |
| `GET /payments/summary` | 401 | ✔ | ✔ |
| `GET/POST/PATCH/DELETE /users` | 401 | 403 | ✔ (системный админ: 403) |
| `GET/PUT/DELETE /payment-occurrences/{id}/receipt`, `GET …/receipt/file` | 401 | ✔ | ✔ |
| `GET /payments/calendar`, `GET /payments/summary?as_of=` | 401 | ✔ | ✔ |
| `GET /budgets`, `GET /budgets/report` | 401 | ✔ | ✔ |
| `PUT /budgets`, `DELETE /budgets/{id}` | 401 | 403 | ✔ |
| `GET/POST /webhooks`, `PATCH/DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries`, `POST /webhooks/{id}/test` | 401 | 403 | ✔ |
| `GET /audit-logs` | 401 | 403 | ✔ |
| `GET /health`, `/docs`, `/openapi.json` | ✔ | ✔ | ✔ |

Документация и health открыты без авторизации: в них нет данных, а жюри удобнее смотреть схему сразу.

Ошибки всегда в одном формате, без стектрейсов:

```json
{"error": {"code": "validation_error", "message": "Некорректные данные запроса", "details": [...]}}
```

Коды: 401 (нет сессии), 403 (нет прав / CSRF / системный админ), 404, 409 (логин занят),
422 (валидация, дата в будущем, лишние поля), 429 (слишком много попыток входа).

Примеры:

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"login":"admin","password":"change-me-admin"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# что оплатить
curl -s "localhost:8000/api/v1/payment-occurrences?status=unpaid&sort=due_date" -H "Authorization: Bearer $TOKEN"
# что просрочено
curl -s "localhost:8000/api/v1/payment-occurrences?status=unpaid&overdue=true" -H "Authorization: Bearer $TOKEN"
# что оплачено
curl -s "localhost:8000/api/v1/payment-occurrences?status=paid" -H "Authorization: Bearer $TOKEN"
# отметить оплату задним числом
curl -s -X PATCH localhost:8000/api/v1/payment-occurrences/<id> -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"status":"paid","paid_date":"2026-10-20"}'
# итоги по валютам
curl -s localhost:8000/api/v1/payments/summary -H "Authorization: Bearer $TOKEN"
```

## Архитектура

Модульный монолит с отдельным процессом worker: один образ, два режима запуска.

```
                    ┌──────────────────────────────────────────────┐
  Браузер ───────►  │  app (api)  FastAPI + раздача статики SPA    │
  Swagger ───────►  │  /api/v1/*   /api/v1/docs   /  (React build) │
                    └───────────────┬──────────────────────────────┘
                                    │ SQLAlchemy
                                    ▼
                    ┌──────────────────────────────┐
                    │  db  PostgreSQL 16 (volume)  │◄──────────────┐
                    └──────────────────────────────┘               │
                                    ▲                              │
                    ┌───────────────┴──────────────┐               │
                    │  worker (тот же образ)       │───────────────┘
                    │  • тик раз в 60 с            │
                    │  • генерация периодов        │───► Telegram Bot API
                    │  • постановка напоминаний    │
                    │  • доставка + ретраи         │───► SMTP (Mailpit в демо)
                    │                              │───► Webhook (HMAC)
                    │                              │───► Slack/Discord/Mattermost
                    │  • long polling Telegram     │◄── нажатия «Оплачено»
                    └──────────────────────────────┘
```

- **app**: `alembic upgrade head` → синхронизация админа из `.env` → сид → `uvicorn app.main:app`.
  Миграции запускает только api; worker стартует после healthcheck api.
- **worker**: `python -m app.worker`, собственный asyncio-цикл. По SIGTERM дорабатывает текущую
  итерацию. Каждый тик пишет heartbeat в БД, его видно в `/api/v1/health`.

Слои (`backend/app`):

```
api/          роутеры (тонкие), схемы, зависимости авторизации, единый формат ошибок
services/     сценарии: AuthService, UserService, PaymentService, OccurrenceService,
              OccurrenceGenerator, SummaryService, ReminderService, DeliveryDispatcher
domain/       чистая логика без I/O: schedule (даты), status (просрочка), reminder_policy, clock, money
repositories/ запросы SQLAlchemy (не коммитят — транзакцию закрывает сервис)
infrastructure/ security (argon2, токены), channels (Telegram, лог), logging (JSON, маскирование), rate_limit
models/       SQLAlchemy-модели;  migrations/ — Alembic
```

Правила: `domain` не импортирует FastAPI/SQLAlchemy/httpx; время только из `Clock`
(`datetime.now()`/`date.today()` в коде запрещены — проверяет тест); внешние сервисы — через
Protocol (`NotificationChannel`), в тестах подменяются фейками.

### Модель данных

```
users                 login (уникален среди живых), password_hash (argon2), role, is_system, email, telegram_user_id, deleted_at
sessions              token_hash (HMAC-SHA256, сам токен не хранится), expires_at, revoked_at
recurring_payments    title, amount NUMERIC(18,2), currency, recurrence, first_due_date DATE, anchor_day, deleted_at
payment_occurrences   снимок title/amount/currency, due_date DATE, is_paid, paid_date DATE
                      UNIQUE(recurring_payment_id, due_date), CHECK(is_paid OR paid_date IS NULL), CHECK(NOT is_paid OR paid_date IS NOT NULL)
notification_deliveries  occurrence_id, channel, recipient, kind, status, attempts, next_attempt_at, last_error, sent_at, locked_at
                      UNIQUE(occurrence_id, channel, recipient, kind)
audit_logs            at, seq, actor_user_id, actor_login, action, entity_type, entity_id, before/after JSONB, ip, user_agent
webhook_endpoints     url, events[], secret_enc (Fernet от SECRET_KEY), is_active; доставки — в notification_deliveries (channel='webhook')
budgets               period_type month|year, year, month, currency, planned_amount; UNIQUE(тип, год, месяц, валюта)
receipts              occurrence_id UNIQUE, url, file_path (случайное имя), file_name, mime, size, uploaded_by
telegram_updates_offset  last_update_id (long polling)
worker_heartbeat, app_meta
```

### Как напоминание не дублируется

1. Тик worker (и создание платежа) находит неоплаченные периоды живых платежей со сроком
   `≤ сегодня + REMINDER_DAYS_BEFORE` и делает `INSERT ... ON CONFLICT DO NOTHING` в
   `notification_deliveries` — повторная проверка и рестарт не создают вторую запись.
2. Диспетчер атомарно захватывает пачку: `UPDATE ... SET status='sending' WHERE id IN
   (SELECT ... FOR UPDATE SKIP LOCKED)` — параллельные worker'ы берут разные записи.
3. Перед отправкой ещё раз проверяется, что период не оплачен и платёж не удалён (иначе `cancelled`).
4. `sent` ставится только после успешного ответа Telegram. Ошибка → `failed` и повтор через
   1, 5, 15, 60 мин; после `DELIVERY_MAX_ATTEMPTS` → `dead` и запись `АЛЕРТ` в лог.
   Зависшие в `sending` дольше 5 минут (worker упал) возвращаются в очередь.
5. Сбой одного канала не мешает остальным.

## Правила предметной области

- **Период (occurrence)** — конкретный срок регулярного платежа со своей отметкой оплаты. Хранит
  снимок названия, суммы и валюты: если шаблон изменится, прошлые периоды не меняются.
- **Генерация** идемпотентна: всегда существуют все периоды со сроком до сегодня (история и
  просрочки), ближайший неоплаченный и следующий за ним. Просрочка не останавливает генерацию.
- **Даты** считаются от якоря `anchor_day`, а не от предыдущей даты: 31 янв → 28 фев (29 в
  високосный) → 31 мар. «Сегодня» — в `APP_TIMEZONE` (по умолчанию `Europe/Moscow`).
- **Просрочка** вычисляется, а не хранится: не оплачено и сегодня > срока → просрочено на N дней;
  оплачено позже срока → «оплачено с опозданием» (`is_overdue=true`, `overdue_days` = на сколько);
  оплата в день срока — вовремя.
- **Отметка оплаты**: `{"status":"paid"}` — дата по умолчанию сегодня; дата не в будущем (422);
  дату можно передать только со статусом `paid`; `{"status":"unpaid"}` очищает дату. Исправление
  даты пересчитывает просрочку и не трогает срок.
- **Удаление платежа** — soft delete: новые периоды и напоминания больше не появляются, будущие
  неоплаченные периоды удаляются, оплаченные и прошедшие остаются с `recurring_payment_deleted=true`.
- **Валюты** — только RUB/USD/EUR, суммы `NUMERIC(18,2)`/`Decimal`, без конвертации; итоги по каждой валюте отдельно.

## Допущения и принятые решения

| Вопрос | Решение |
|---|---|
| Стек | Предложенный: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16, React + Vite + TypeScript + Tailwind |
| Повторный `DELETE /recurring-payments/{id}` | 404: прекращённый платёж для удаления уже не существует |
| Просроченные неоплаченные периоды удалённого платежа | остаются в истории и в итогах «просрочено» (долг реальный), но напоминаний по ним нет никогда |
| `role` в `POST /users` | 422 (`extra=forbid`); через API создаётся только `user` |
| Системный админ | при старте создаётся/обновляется из `.env`; `PATCH/DELETE` → 403; логин занят → 409; в `/users` не виден. Если сменить `ADMIN_LOGIN`, прежний системный админ отключается. Если обычный пользователь занимал этот логин, он отключается (с предупреждением в логе) |
| Повторная отметка «Оплачено» без даты | сохраняет ранее указанную дату (идемпотентно) |
| Отмена оплаты после отправленного напоминания | повторного напоминания нет (по периоду уже было успешное). Если отменили до отправки — напоминание снова в очереди |
| Повторы о просрочке | основное напоминание — одно на период. Если период просрочен, приходят отдельные напоминания «просрочено на N дн.» на 1-й, 4-й, 7-й… день (`OVERDUE_REMIND_EVERY_DAYS`, не больше `OVERDUE_REMIND_MAX`). Каждый повтор — своя доставка `overdue:N`, без дублей; первый повтор не приходит в тот же день, что основное напоминание; оплата отменяет повторы |
| Окно напоминаний | `REMINDER_DAYS_BEFORE` (по умолчанию и минимум 3) — включая день срока и просроченные; по одному периоду — одно напоминание |
| «Сразу» при позднем добавлении | после `POST /recurring-payments` рассылка запускается фоновой задачей api в тот же момент; если не вышло — дошлёт ближайший тик worker |
| `first_due_date` | не раньше года назад и не позже 5 лет вперёд (защита от тысяч периодов); прошлые даты разрешены — создаётся история с просрочкой |
| Удаление пользователя | soft delete, сессии ревокуются; логин можно занять заново |
| Итоги без фильтров | по всем материализованным периодам (история + ближайший и следующий); фильтры `from`/`to` сужают диапазон сроков |
| Ограничение попыток входа | 5 неудачных за 5 минут на пару IP+логин, в памяти процесса api (одного экземпляра достаточно; для нескольких — вынести в Redis/БД) |
| CSRF | cookie `SameSite=Lax` + для изменяющих запросов по cookie сверка `Origin`/`Referer` с хостом. Запросы с `Authorization: Bearer` CSRF не подвержены |
| Доставка «ровно один раз» | гарантия «не больше одного успешного `sent` на период/канал/получателя». Если worker упадёт между ответом Telegram и записью `sent`, после таймаута возможен один повтор — при внешнем API без идемпотентных ключей это неизбежно |
| `kind` доставки | `TEXT`, а не ENUM: новые виды уведомлений добавляются без миграции типа. Для `payment.paid/unpaid` в `kind` добавляется id события (`payment.paid:<id>`), чтобы каждое изменение статуса было отдельной доставкой, а повторы одной — нет |
| SSRF вебхуков | адрес проверяется при сохранении и перед отправкой (DNS → IP). Между проверкой и соединением остаётся окно DNS rebinding; для продакшена — исходящий прокси с allowlist |
| Итоги на дату | «оплачено» — `paid_date ≤ as_of`; «просрочено» — срок < `as_of` и к этой дате не оплачено; «предстоит» — срок ≥ `as_of`. Учитываются материализованные периоды (история + ближайший и следующий), прогноз дальше не строится |
| Бюджет | «запланировано» — сумма периодов со сроком в периоде бюджета (по материализованным периодам: для будущих месяцев года виден ближайший и следующий период, прогноз дальше не строится). Остаток = бюджет − запланировано |
| Чек | один на период: ссылка и/или файл; новая часть заменяет прежнюю, прежний файл удаляется. Файл отдаётся с `nosniff` и `Content-Security-Policy: sandbox` |
| Шрифты панели | встроены в сборку (`@fontsource`), панель работает без интернета |

## Реализованные возможности

Обязательная часть:

- [x] Регулярные платежи RUB/USD/EUR, ежемесячно, периоды с отдельными статусами и снимками
- [x] Перенос на последний день месяца от якоря, високосный год
- [x] Отметка/отмена оплаты, фактическая дата, исправление даты, динамическая просрочка
- [x] Напоминания в Telegram за 3 дня, немедленные при позднем добавлении, без дублей, ретраи
- [x] Soft delete с сохранением истории
- [x] Роли admin/user, проверка на сервере, системный админ из `.env`
- [x] Веб-панель: вход, итоги по валютам, фильтры, вкладки, оплата с выбором даты, админ-разделы
- [x] Swagger, `openapi/openapi.yml`, единый формат ошибок, health
- [x] Запуск одной командой, сид, Makefile, тесты

Сверх обязательной части:

- [x] **Журнал действий** (`audit_logs`, `GET /api/v1/audit-logs`, страница «Журнал»): вход/неудачный вход/блокировка,
  выход, создание и прекращение платежей, отметки и отмены оплаты, исправление даты (до/после), управление
  пользователями (без паролей), отправленные и недоставленные уведомления; IP и user-agent. Пишется из сервисного
  слоя в той же транзакции, что и изменение. Логи приложения — JSON с `request_id`, секреты маскируются
- [x] **Кнопка «Оплачено» в Telegram**: inline-кнопка, привязка `telegram_user_id`, отказ непривязанным,
  идемпотентность, редактирование сообщения «кто и когда», long polling в worker
- [x] **Чек или ссылка к оплате**: `PUT/GET/DELETE /api/v1/payment-occurrences/{id}/receipt` (multipart: `url`
  и/или `file`), скачивание `…/receipt/file` только авторизованным. Ссылки только http/https; файлы PNG/JPG/PDF
  до 5 МБ, тип определяется по магическим байтам, имя случайное, хранение в volume `uploads`. Права как у
  отметки оплаты, действия в журнале. В панели — кнопка «Чек» и пометка у периода
- [x] **Календарь оплат и итоги на дату**: `GET /api/v1/payments/calendar?from&to` (периоды по дням, статусы,
  итоги дня по валютам, до 92 дней) и `GET /api/v1/payments/summary?as_of=YYYY-MM-DD` (оплачено к дате,
  просрочено на дату, предстоит). В панели — месячная сетка с бейджами (цвет + знак ✓/!/○), итоги дня,
  клик по периоду — детали и отметка оплаты, переход по месяцам, выбор даты итогов
- [x] **Бюджет на месяц и год**: таблица `budgets` (тип, год, месяц, валюта, плановая сумма), `PUT/GET/DELETE
  /api/v1/budgets` (менять — admin, смотреть — все) и `GET /api/v1/budgets/report` — запланировано, оплачено,
  остаток, превышение по каждой валюте. В панели — шкалы прогресса и предупреждение о превышении
- [x] **Email через SMTP**: канал `email` (`NotificationChannel`), письмо text + HTML, общий список и email
  пользователей, тот же UNIQUE/ретраи/без дублей; Mailpit в профиле `demo-mail`; тесты с мок-SMTP
- [x] **Webhook**: CRUD адресов (admin), 4 события, JSON со `schema_version`, подпись HMAC-SHA256, ключ
  идемпотентности, таймауты, ретраи с backoff, журнал доставок, тестовая отправка, SSRF-защита
  (только http/https, запрет внутренних адресов, переключается `WEBHOOK_ALLOW_PRIVATE`), секрет зашифрован (Fernet)
- [x] **Другие каналы**: Slack/Discord/Mattermost incoming webhook (`CHAT_WEBHOOK_URL`), подключается без
  изменений в ядре; Telegram, email и webhook используют тот же `NotificationChannel`; инструкция «как добавить свой канал»
- [x] **Проработанный UX**: дашборд «просрочено / ближайшие 7 дней / оплачено недавно» с отметкой в один клик,
  карточки по валютам, поиск, сортировка, фильтры запоминаются, статусы не только цветом (штамп, знаки ✓ ! ◆, текст),
  загрузка/пустые состояния/ошибки/toast, подтверждения опасных действий, карточки вместо таблиц на телефоне,
  тёмная тема (по системной настройке или переключателем), фокус и aria, суммы через `Intl.NumberFormat`,
  русские даты. Дизайн-система — [`DESIGN.md`](DESIGN.md)
- [x] **Telegram-бот как интерфейс**: ответы на вопросы (`/topay`, `/overdue`, `/week`, `/paid`, `/summary`, вопросы
  словами), привязка без ввода id (`/bind`, deep link), добавление платежа фразой (`/add`, разбор без ИИ —
  `domain/phrase.py`), недельная сводка, повторы о просрочке; в панели — «Быстро фразой», «Проверить сейчас»,
  редактирование платежа
- [x] Периодичность: еженедельно, ежеквартально, ежегодно (стратегии `RecurrenceStrategy`, 29 фев → 28 фев в невисокосный год)

## Требование → где реализовано → чем проверено

| Требование | Где | Проверка |
|---|---|---|
| Запуск одной командой, миграции и сид автоматически | `docker-compose.yml`, `backend/docker-entrypoint.sh`, `app/bootstrap.py` | запуск из чистого клона, `scripts/acceptance.py` |
| Без авторизации данные недоступны | `api/deps.py` (`get_auth`), `App.tsx` (`Protected`) | `test_permissions_matrix.py` (401 на каждый эндпоинт) |
| Пользователь не выполнит действия админа через API | `require_admin` в роутерах | `test_permissions_matrix.py` (403), `test_payments.py`, `acceptance.py` п. 2 |
| Админ из `.env`, не управляется через API | `AuthService.sync_system_admin`, `UserService._get_manageable` | `test_users.py`, `test_auth.py`, `acceptance.py` п. 10 |
| Периоды, следующий период с отдельным статусом, история | `domain/schedule.py`, `OccurrenceGenerator` | `test_schedule.py`, `test_payments.py` |
| 31-е число, високосный год | `domain/schedule.py` | `test_schedule.py`, `test_recurrence_strategies.py` |
| Отметка/отмена оплаты, дата очищается, не в будущем | `domain/status.py`, `OccurrenceService.mark` | `test_status.py`, `test_payments.py` |
| Исправление даты убирает просрочку, срок не меняется | `domain/status.py` | `test_status.py`, `test_payments.py`, `acceptance.py` п. 5 |
| Напоминание за ≥ 3 дня, без дублей, немедленно при позднем добавлении | `ReminderService`, `DeliveryDispatcher`, `notification_deliveries` | `tests/worker/test_reminders.py` |
| Оплаченный / удалённый не напоминает | `_still_relevant`, `cancel_open_*` | `test_reminders.py` |
| Валюты и итоги по каждой отдельно | `domain/money.py`, `SummaryService` | `test_payments.py`, `test_calendar_summary.py` |
| Сохранность после перезапуска | volume `pgdata` | `docker compose down` / `up` вручную |
| OpenAPI и Swagger | `app/openapi_dump.py`, `/api/v1/docs` | `test_openapi_file.py` |
| Аудит | `AuditService`, `/audit-logs` | `test_audit.py` |
| Кнопка «Оплачено» в Telegram | `services/telegram_updates.py` | `test_telegram_button.py` |
| Чеки | `ReceiptService`, `storage.py` | `test_receipts.py` |
| Календарь, итоги на дату | `SummaryService.calendar`, `summary(as_of)` | `test_calendar_summary.py` |
| Бюджеты | `BudgetService` | `test_budgets.py` |
| Email | `channels/email.py` | `test_email_channel.py` |
| Webhook | `channels/webhook.py`, `WebhookService` | `test_webhooks.py` |
| Slack/Discord/Mattermost | `channels/chat_webhook.py` | `test_chat_webhook.py` |

## Известные ограничения

- Реальная отправка в Telegram проверена только против мок-API (`httpx.MockTransport`) и в режиме «лог вместо
  отправки»; для живой проверки нужен токен бота и `chat_id`.
- Rate limit входа хранится в памяти одного процесса api.
- Доставка — «не больше одного успешного `sent`»; при падении worker между ответом внешнего API и записью
  статуса возможен один повтор после таймаута.
- Календарь, итоги на дату и бюджеты считаются по материализованным периодам (история + ближайший и следующий),
  долгосрочный прогноз не строится.
- SSRF-проверка вебхуков не закрывает DNS rebinding между проверкой и соединением.

## Переменные окружения

Полный список с комментариями — в [`.env.example`](.env.example). Главное:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `ADMIN_LOGIN`, `ADMIN_PASSWORD` | `admin` / — | системный администратор (обязательно) |
| `SECRET_KEY` | — | ключ HMAC токенов сессий, ≥ 16 символов (обязательно) |
| `APP_TIMEZONE` | `Europe/Moscow` | часовой пояс «сегодня» |
| `APP_FAKE_TODAY` | пусто | демо: подменить «сегодня» |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | пусто | бот и чат; без токена — лог вместо отправки |
| `REMINDER_DAYS_BEFORE` | `3` | за сколько дней напоминать (не меньше 3) |
| `WORKER_INTERVAL_SECONDS` | `60` | период фоновой проверки |
| `COOKIE_SECURE` | `false` | `true` за HTTPS |
| `SEED_ON_START`, `SEED_USER_PASSWORD` | `true`, `user12345` | демо-данные |

Если обязательная переменная не задана, api не стартует и пишет, какой именно не хватает.
