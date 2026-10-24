# Handoff: Invoice Keeper — память проекта для продолжения в другом агенте

Документ для **передачи контекста** без истории чата. Репозиторий: `git@github.com:andreytitar/AezaInvoiceKeeperCucoders.git`, рабочая ветка фронтенда **`feat/aeza-frontend`** (без push).
Последние значимые коммиты (октябрь 2026):

| Коммит | Сообщение |
|--------|-----------|
| `3fc9842` | style(ui): Unify Aeza tokens and controls |
| `ad7e989` | feat(shell): Refresh navigation and dialogs |
| `012a306` | feat(payments): Refine dashboard and actions |
| `2b8b547` | feat(calendar): Refine calendar and totals |
| `d0c4645` | feat(admin): Refresh management pages |
| `43dcb12` | style(auth): Refresh team sign-in |
| `da769e6` | feat: Redesign web panel and Telegram bot UX |
| `f63a8c1` | feat(teams): Add 24-hour sandbox teams so anyone can try the product from the bot |

**Тесты:** `make test` → **383 passed** (PostgreSQL в Docker, профиль `test`).

**Секреты:** `.env` в `.gitignore`, в git только `.env.example`.

---

## 1. Зачем проект

**Invoice Keeper** — хакатон Aeza (Middle): команда ведёт **регулярные платежи** (аренда, подписки, серверы). За **≥3 дня** до срока — напоминание в **Telegram-чат**; в **веб-панели** и **боте** видно, что оплатить, что просрочено, что уже оплачено. **Три валюты** (RUB, USD, EUR), итоги **без конвертации**.

Дублирующая краткая памятка для Cursor: `.cursor/rules/invoice-keeper-memo.mdc` (alwaysApply). Правило про несколько агентов: `.cursor/rules/multi-agent.mdc`.

---

## 2. Запуск и остановка

```bash
cp .env.example .env
docker compose up --build          # или make up
docker compose down                # остановка, volumes сохраняются
docker compose down -v             # удалить БД и uploads (осторожно)
make test                          # полный pytest в контейнере
```

| Сервис | Назначение |
|--------|------------|
| `app` | FastAPI + статика React, порт `APP_PORT` (8000) |
| `worker` | Тик 60 с: периоды, напоминания, доставки, **Telegram long polling** |
| `db` | PostgreSQL 16, volume `pgdata` |
| `caddy` | HTTPS для прод-домена (см. `Caddyfile`) |
| `mailpit` | Профиль `demo-mail` — демо SMTP |
| `tests` | Профиль `test` — pytest |

Без `TELEGRAM_BOT_TOKEN` — **dry-run**: сообщения в лог worker (`[DRY-RUN Telegram]`).

**Демо-логины** (из сида): `admin` / `change-me-admin`, `ivan`/`maria` / `user12345`.

**Подмена «сегодня»:** `APP_FAKE_TODAY=YYYY-MM-DD` в `.env`.

---

## 3. Архитектура

Модульный монолит, **один Docker-образ**, два процесса: `api` и `worker`.

```
frontend/ (React + Vite + TS)  →  собирается в образ, отдаётся app
backend/app/
  api/           роутеры, deps, схемы
  services/      сценарии (auth, payments, occurrences, reminders, bot, teams…)
  domain/        чистая логика: schedule, status, money, clock, reminder_policy
  repositories/  SQLAlchemy, без commit (коммитит сервис)
  infrastructure/ security, channels (Telegram, email, webhook…), logging
  models/        ORM
  migrations/    Alembic (0001 … 0012)
openapi/openapi.yml + Swagger /api/v1/docs
```

**Инварианты:**

- Время только через **`Clock`** (`domain/clock.py`); `date.today()` в прикладном коде — антипаттерн (есть тест).
- **Просрочка** вычисляется (`domain/status.py`), не колонка в БД.
- **Даты периодов** от `anchor_day`, не от предыдущего периода (31→28/29→31).
- **Напоминания без дублей:** `notification_deliveries` + `UNIQUE(occurrence_id, channel, recipient, kind)` + `ON CONFLICT DO NOTHING`.
- **Decimal / NUMERIC** для денег, не float.

---

## 4. Предметная область (критично не сломать)

| Правило | Деталь |
|---------|--------|
| Просрочка | С **следующего** дня после `due_date`. Оплата **в день срока** — не просрочка |
| Отмена оплаты | `status=unpaid` → `paid_date` **очищается** |
| Удаление платежа | Soft delete; напоминаний больше нет; история и просроченные периоды остаются |
| Роли | Admin/user на **API**; системный admin из `.env`, не редактируется через API |
| Напоминания | Окно `REMINDER_DAYS_BEFORE` (мин. 3); оплаченные и удалённые — не напоминаем |
| Повторы просрочки | Отдельные `kind` `overdue:N`, интервал `OVERDUE_REMIND_EVERY_DAYS` |

Полный чек-лист приёмки — README § «Реализованные возможности» и `.cursor/rules/invoice-keeper-memo.mdc` §7.

---

## 5. Мультикоманда (teams)

Миграция **`0011_teams`**: сущность `Team`, `team_id` у пользователей, платежей, вебхуков, бюджетов и т.д.

| `TeamKind` | Поведение |
|------------|-----------|
| **PRIMARY** | Основная команда инсталляции (сид, admin из env) |
| **SANDBOX** | Временная команда из бота, **TTL 24 ч**, лимит создания **5/мин** |

**Sandbox из бота** (`TeamService.create_sandbox`):

- Выдаёт коды приглашения (admin/employee/invite), демо-платежи через `PaymentService`.
- Telegram user не должен уже быть в другой команде.
- Просроченные sandbox удаляются worker’ом (см. `teams.py` cleanup).

**Scope в API:** текущий пользователь `user.team_id`; репозитории фильтруют по команде. Бот: `BotAnswers(db, clock, team_id=...)`.

Тесты: `backend/tests/integration/test_teams.py`.

---

## 6. Telegram-бот (текущий UX, после редизайна)

### 6.1 Файлы

| Файл | Роль |
|------|------|
| `services/bot_answers.py` | Тексты экранов, клавиатуры, `BotAnswers` |
| `services/bot_list_format.py` | **Только UI списков:** `format_money_bot`, группировка по датам, итоги |
| `services/telegram_updates.py` | Long polling, callbacks, команды, чеки, /add |
| `services/telegram_link.py` | Коды привязки чата и аккаунта |
| `services/telegram_profile.py` | Профиль в боте |
| `services/telegram_login.py` | Web login через `start=weblogin_…` + Login Widget |
| `infrastructure/channels/formatting.py` | Тексты **напоминаний** (не путать с bot_list_format) |
| `infrastructure/channels/telegram.py` | HTTP к Bot API, `edit_message_text`, `answerCallbackQuery` |

### 6.2 Экраны (`ScreenId`)

`menu`, `topay`, `overdue`, `week`, `paid`, `summary`, `add_hint`, `site`.

**Единый шаблон списков неоплаченных** (`_unpaid_list`):

1. Заголовок с emoji · «N платежей»
2. «Страница X из Y» (если >1)
3. Группы по `due_date` (`render_grouped_payment_lines`, заголовок дня: 🔴 просрочка / сегодня / через N дней)
4. Строки: `N. title — **sum**` (HTML)
5. Итоги по валютам (`totals_currency_lines` / для topay label «Всего к оплате»)
6. Кнопки `✅ 1…8` (**4 в ряд**, `LIST_PAGE=8`)
7. Пагинация `◀️ · N/M · ▶️`
8. Футер (`_LIST_FOOTER`) + «🏠 В меню»

**Оплачено за 30 дней:** группировка по `paid_date`, без кнопок ✅, те же nav/футер.

**Сводка:** `📊 Сводка · дата`, блоки RUB/USD/EUR с `format_money_bot`.

**Дайджест на неделю:** блоки просрочки + «на неделю», до 8 строк каждый, кнопки ✅ с сквозной нумерацией (до `BUTTONS=6`), итоги, «💳 К оплате» / «🏠 В меню».

### 6.3 Callback-протокол

| Префикс | Пример | Назначение |
|---------|--------|------------|
| `nav:` | `nav:t:0`, `nav:m` | Навигация, edit сообщения |
| `nav:noop` | | Debounce / неактивная кнопка |
| `lp:` | `lp:t:{uuid}` | Оплатить из списка (новый формат с кодом экрана) |
| `lp:` | `lp:{uuid}` | **Legacy** (экран из эвристики текста) |
| `unpay:` | `unpay:t:0:{uuid}` | Отменить оплату после карточки |
| `paid:` | | Legacy под напоминаниями |
| `undo:` | | Отменить только что добавленный платёж |

Коды экранов: `t` topay, `o` overdue, `w` week, `p` paid, `s` summary, `m` menu, …

**После ✅ на topay/overdue/week:** сообщение **не** обновляется списком, а заменяется карточкой `format_paid_confirmation` + `paid_undo_keyboard`. Отмена → `OccurrenceService.mark(UNPAID)` → refresh экрана по `_CODE_TO_SCREEN[screen_code]`.

**Старые сообщения:** `screen_from_message_text()` + `parse_page_from_message()` в `bot_list_format.py`.

### 6.4 Команды и NL

`/start`, `/help`, `/topay`, `/overdue`, `/week`, `/paid`, `/summary`, `/add`, привязка чата, join по коду, sandbox, weblogin в `/start`.

Свободный текст в личке: `command_for_text()` → те же экраны.

Админ: `/add <фраза>` → `parse_payment_phrase` (`domain/phrase.py`).

### 6.5 Ограничение зоны правок (из недавней работы)

При **точечном редизайне только бота** договорённость была: **не трогать** домен, API контракты, БД, веб-панель — только слой ответов бота и форматирование сообщений. Сейчас в `main` уже **смешанный** коммит (и веб, и бот, и auth). Новые задачи — уточнять у пользователя scope.

---

## 7. Вход через Telegram (сайт)

Миграция **`0012_web_login_codes`**.

- **Deep link:** `t.me/<bot>?start=weblogin_<code>` — бот пишет `telegram_user_id` в код, фронт **poll** API.
- **Login Widget:** HMAC-SHA256, секрет = SHA256(bot token); fallback если нет deep link.
- Сервис: `telegram_login.py`, API: `backend/app/api/v1/auth.py` (расширен), фронт: `TelegramLoginWidget.tsx`, `LoginPage.tsx`.
- `PUBLIC_BASE_URL`, `TELEGRAM_BOT_USERNAME` / getMe, `COOKIE_SECURE` для HTTPS.

Тесты: `backend/tests/integration/test_telegram_web_login.py`.

---

## 8. Веб-панель (редизайн Aeza)

**Дизайн:** `DESIGN.md`; брендовые факты — `frontend/src/styles/AEZA-BRAND.md`.

- Одна система токенов в `frontend/src/index.css` (`:root` / `[data-theme=dark]`,
  Tailwind v4 `@theme`). Старые `theme-light.css` / `theme-dark.css` удалены.
- Aeza: `#4CC6F1`, нейтральные серые, белый/чёрный; без ретро-окон и bevel.
- Шрифты: **Exo 2** — заголовки/итоги, **Inter** — UI, **IBM Plex Mono** — суммы/даты.
  Подключение в `index.html`; неиспользуемые fontsource-пакеты удалены.
- Общие компоненты — `components/ui.tsx`, сплошные иконки — `components/Icon.tsx`.
  Sidebar с компактным меню аккаунта, мобильные иконки/подписи и safe area.
- Платежи: валютные карточки, бейджи, вкладки со счётчиками, одна главная кнопка
  строки + меню, мобильные фильтры в Dialog и карточки вместо таблицы.
- Календарь: выбран сегодняшний день сервера, мобильные точки, desktop-чипы
  с суммой, вертикальные итоги валют. ICS/Apple/Google и смена ссылки сохранены.
- Создание шаблонов, пользователей и вебхуков — в общих Dialog; редактирование
  шаблонов и пользователей — там же. Журнал показывает изменённые поля и
  свёрнутый JSON. Бюджет — месяц/год.
- DateInput показывает `дд.мм.гггг`, валидирует дату, передаёт ISO API.
  Тема по системе при первом входе, ручной выбор — в `ik-theme`.
- Все сценарии Telegram-входа/команд/привязки сохранены. QR-сканер в веб-панель
  намеренно не возвращён. Бэкенд, схемы и API не менялись.
- Vite proxy сохраняет Host (`changeOrigin:false`) для cookie CSRF; при необходимости
  отдельный локальный API выбирается через `API_PROXY_TARGET`.
- OpenAPI-типы: `frontend/src/api/schema.d.ts` (не изменены).

### 8.1. Проверка FRONTEND_TZ.md, 24.10.2026

- [x] Русские даты `дд.мм.гггг`, маска, проверка невозможной даты и границ.
- [x] Общий Button: варианты, размеры, disabled/loading, hover/focus.
- [x] Общие поля, checkbox, badge, card, table, dialog, tabs, skeleton, toast.
- [x] «Проверить напоминания» — secondary с иконкой.
- [x] Валютные карточки: крупный итог, три строки, нули как тире.
- [x] Пустые срочные блоки — карточки с EmptyState.
- [x] Шапки таблиц, суммы, даты и коды валют не разрываются.
- [x] Одна главная кнопка оплаты; дата, чек и отмена — в меню.
- [x] Статус — pill с точкой и второй строкой срока/даты оплаты.
- [x] Фильтры одной строкой на desktop, диалог на узких экранах, сброс.
- [x] Segmented control с реальными API-счётчиками.
- [x] Соседние дни календаря приглушены, жирных пустых рамок нет.
- [x] До двух чипов с полной суммой и +N; на телефоне точки.
- [x] Сегодня — голубой круг, легенда — бейджи с точками.
- [x] По умолчанию выбран сегодняшний день сервера.
- [x] Итоги в узкой панели — вертикальный список валют без переноса сумм.
- [x] Компактная шапка календаря, «Сегодня», ICS/Apple/Google.
- [x] Действия шаблонов в меню, удаление подтверждается в Dialog.
- [x] Названия шаблонов получили широкую колонку, числа не переносятся.
- [x] Форма нового платежа в Dialog, включая телефон.
- [x] Бюджет: общие карточки, суммы, периоды месяц/год.
- [x] Пользователи: общий список, роли, меню, create/edit/delete Dialog.
- [x] Вебхуки: статусы, меню, пустое состояние, история доставок.
- [x] Журнал: изменённые поля до/после и свёрнутый JSON.
- [x] Чистая страница входа с формой и блоком продукта.
- [x] Обработчики входа Telegram, команды и привязки сохранены.

**Результаты:**

- `npm run build --prefix frontend`: TypeScript и Vite без ошибок и предупреждений.
- `make test`: **383 passed**, один прежний Python SyntaxWarning в тесте ICS.
- `python3 scripts/acceptance.py --base http://127.0.0.1:18000`: всё зелёное.
- Production bundle (`vite preview`, порт 4173): **15** проверок основного UI,
  **22** проверки management, **6** проверок темы/клавиатуры/доступности; ошибок JS нет.
- **96** скриншотов: 8 страниц × 2 темы × 360/390/768/1024/1280/1440.
  Нет горизонтального скролла, наложений сумм в сводке и ошибок консоли.
- `npm run lint`: 0 ошибок; 10 предупреждений React (Fast Refresh и прежние
  эффекты/инициализация состояния). На TypeScript/build не влияют.
- Логи и JSON: `.design-review/{smoke-report,management-smoke-report,
  accessibility-smoke-report}.json`, `backend-tests.log`, `acceptance.log`,
  `frontend-build.log`, `frontend-lint.log`.
- Скриншоты: `.design-review/after/<width>-<theme>-<page>.png`,
  сводная матрица `after/report.json`, сравнения `after/comparison-*.jpg`.

Живой вход/доставка Telegram и production отдельно не проверялись. Нужны реальный
бот и проверка оператором; этот редизайн их API и серверную логику не меняет.
Тестовые данные CRUD удалены пересозданием только изолированной QA-БД, финальные
скриншоты сняты на чистом seed. Невыполненных пунктов фронтенд-редизайна нет.

---

## 9. Остальные реализованные фичи (кратко)

- **Журнал аудита** — `audit_logs`, страница Audit
- **Чеки** — URL/файл на occurrence; **QR ФНС** — `receipt_scan.py`, бот; сканер панели намеренно убран
- **Календарь** — API + UI; **ICS feed** — `calendar_feed.py`, токен пользователя
- **Бюджеты** — month/year по валютам
- **Email** — SMTP channel; **Webhooks** — HMAC, CRUD admin; **Chat webhook** — Slack/Discord/Mattermost
- **Редактирование** recurring payment (title, amount, currency)
- **Admin «проверить напоминания сейчас»**
- **Недельный дайджест** в чат — `digest.py`, `DIGEST_WEEKDAY` / `DIGEST_HOUR`

Подробности — README § «Реализованные возможности».

---

## 10. Миграции БД

| Версия | Суть |
|--------|------|
| 0001 | Базовая схема |
| 0003 | audit_logs |
| 0004 | telegram_updates_offset |
| 0005–0009 | receipts, budgets, webhooks, calendar token, fiscal sign |
| 0011 | **teams** |
| 0012 | **web login codes** |

При старте `app` выполняет `alembic upgrade head` (worker ждёт healthy app).

---

## 11. Ключевые API (префикс `/api/v1`)

| Группа | Назначение |
|--------|------------|
| `auth` | login/logout/me, Telegram web login, widget |
| `recurring-payments` | CRUD (admin create/delete) |
| `payment-occurrences` | list, mark paid/unpaid, paid_date, receipt |
| `payments/summary`, `payments/calendar` | Итоги и календарь |
| `users` | CRUD regular users (admin) |
| `budgets`, `webhooks`, `audit-logs` | Доп. возможности |
| `telegram` | link codes, chat binding |
| `calendar/feed` | ICS |
| `health`, `docs` | Операционка |

Спека: `openapi/openapi.yml`.

---

## 12. Worker: что делает каждый тик

1. Генерация периодов (`OccurrenceGenerator`)
2. Scan напоминаний + просрочных повторов
3. Dispatch очереди `notification_deliveries` (Telegram, email, webhook, chat)
4. Недельный digest (по расписанию)
5. Cleanup sandbox teams
6. **Telegram getUpdates** (если `TELEGRAM_POLLING_ENABLED`) → `TelegramUpdateHandler`

Heartbeat в БД → виден в health.

---

## 13. Тесты (ориентиры)

| Путь | Что проверяет |
|------|----------------|
| `tests/unit/test_bot_list_format.py` | Формат сумм, заголовки дней |
| `tests/unit/test_bot_ui.py` | Callback parse, screen heuristics |
| `tests/worker/test_telegram_bot.py` | Команды, free text, списки |
| `tests/worker/test_telegram_button.py` | lp/paid callbacks |
| `tests/integration/test_teams.py` | Изоляция команд, sandbox |
| `tests/integration/test_telegram_web_login.py` | Web login flow |

Домен: `test_status.py`, `test_phrase.py`, payments integration, reminders worker tests.

---

## 14. Продакшен / Caddy

`Caddyfile` настроен на домен **`aezainvoicekeepercucoders.fun`** → `reverse_proxy app:8000`.
Для HTTPS: `COOKIE_SECURE=true`, `PUBLIC_BASE_URL=https://…`, порты 80/443 на `caddy`.

---

## 15. Типичные ловушки (не повторять)

- Просрочка «со дня срока» вместо «со следующего дня»
- Складывание валют в один итог
- Права только в UI без проверки в роутере
- Дубли напоминаний без записи в `notification_deliveries`
- Float для денег
- Циклический import: `bot_list_format` **не** должен тянуть `bot_answers`; напоминания — через `formatting.py`
- Callback data Telegram **≤64 байт** — UUID в lp/unpay укладывается, длинные title в callback не класть

---

## 16. Состояние на момент handoff

- Редизайн фронтенда находится в `feat/aeza-frontend`, локальные коммиты без push.
  Развёртывания production не было.
- Для QA поднят отдельный локальный compose project `invoice-keeper-frontend-qa`
  с отдельной БД, API `127.0.0.1:18000`, отправка Telegram/email отключена.
  Предпросмотр собранного фронтенда — `http://127.0.0.1:4173`.
  HMR: `API_PROXY_TARGET=http://127.0.0.1:18000 npm run dev -- --host 127.0.0.1`.
- Порт 8000 на этой машине занят SSH-туннелем; не считать его локальной тестовой БД.
- Доказательства проверки и пары скриншотов — в игнорируемом `.design-review/`.
  `FRONTEND_TZ.md`, `PROMPT.md`, `.design-review/` в коммиты не включать.
- `.env` локальный, не в git. Живой Telegram и production отдельно не проверялись.

---

## 17. Как продолжать работу (инструкция агенту)

1. Прочитать **README** (быстрый старт, демо-сценарий) и этот файл.
2. Уточнить у пользователя **scope**: только бот / только фронт / полный стек.
3. При изменениях API — править **openapi**, `make openapi`, `schema.d.ts`, тесты permissions.
4. Любая логика дат/просрочки — **domain + unit tests**; не дублировать в боте.
5. Перед сдачей — **`make test`**; для Telegram — worker tests + ручная проверка с токеном.
6. **Не коммитить** `.env`; коммиты — только по явной просьбе пользователя.
7. Несколько агентов — делить по **владению файлами** (см. `multi-agent.mdc`), стыки проверяет «родитель».

---

## 18. Идеи / возможные следующие шаги (не обязательно сделано)

- Довести формат **напоминаний** до `format_money_bot` + единый стиль с списками (без циклических импортов).
- E2E/manual QA на втором боте / prod домене.
- Rate limit login в Redis при нескольких репликах api.
- Коммит `AGENT_HANDOFF.md` в git, если нужен другим разработчикам (сейчас файл локальный до push).

---

*Документ создан для handoff между агентами Cursor. Обновляйте секции 6, 8, 16 и таблицу коммитов при крупных изменениях.*
