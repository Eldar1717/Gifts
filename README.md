# GIFT MARKET — Telegram Mini App маркетплейс коллекционных подарков

Полноценный маркетплейс цифровых коллекционных предметов внутри Telegram: покупка за
Telegram Stars, инвентарь с серийными номерами, коллекции и редкости, перепродажа между
пользователями, внутренний журнал начислений продавца, история операций и защищённая
админ-панель.

> **Важно о терминологии.** Предметы в этой витрине — **внутренние цифровые предметы
> GIFT MARKET**, которые хранятся в базе данных проекта. Они **не являются** официальными
> Telegram Collectible Gifts, **не являются** NFT и не выпускаются в блокчейне. В модели
> данных есть отдельные явные статусы источника (`internal`, `telegram_official`,
> `external_nft`) и архитектурные хуки для TON — но приложение никогда не выдаёт внутренний
> предмет за предмет, выпущенный on-chain. Подробнее: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#ton-и-внешние-nft-хуки-без-имитации).

---

## Содержание

- [Что реализовано](#что-реализовано)
- [Стек](#стек)
- [Быстрый старт (локально)](#быстрый-старт-локально)
- [Демо-данные и вход без Telegram](#демо-данные-и-вход-без-telegram)
- [Как устроены деньги](#как-устроены-деньги)
- [Оплата Stars: полный цикл](#оплата-stars-полный-цикл)
- [Тесты и проверки](#тесты-и-проверки)
- [Структура репозитория](#структура-репозитория)
- [Админ-панель](#админ-панель)
- [Переменные окружения](#переменные-окружения)
- [Docker и деплой](#docker-и-деплой)
- [Документация](#документация)
- [Что остаётся за владельцем проекта](#что-остаётся-за-владельцем-проекта)
- [Границы реализации](#границы-реализации)

---

## Что реализовано

### Витрина и каталог

- **Главная**: рекомендации, популярное, новинки, редкие коллекции, последние продажи,
  топ продавцов, живые метрики оборота.
- **Маркет**: поиск по названию/коллекции, фильтры по редкости, цене и категории,
  сортировки по популярности, цене и дате, бесконечная подгрузка, состояние фильтров
  в URL.
- **Карточка предмета**: 3D-подобное превью, редкость, тираж, серийный номер и владелец
  конкретного экземпляра, график истории цен, история перепродаж, продавец с рейтингом.
- **Коллекции**: страницы коллекций с составом, редкостью, прогрессом сбора; пять
  уровней редкости, ограниченные тиражи.
- **Избранное**, **уведомления**, **история заказов**, **профиль продавца**.

### Пользователь

- Вход по Telegram `initData` (подпись проверяется на сервере).
- **Моя коллекция**: предметы с серийным номером, датой приобретения, текущим и прошлыми
  владельцами, возможностью выставить на продажу и создать оффер.
- **Профиль**: Telegram ID, username, аватар, количество предметов, покупки/продажи, оборот,
  рейтинг продавца, история операций, начисленный баланс, настройки приватности.
- **Продажа**: создание лота, изменение цены, отмена, офферы (принять/отклонить),
  лента уведомлений о статусах.
- **Выплаты**: заявка на выплату продавцу с явной пометкой, что внутренний баланс — не
  кошелёк и выплата выполняется вручную (см. [ниже](#что-остаётся-за-владельцем-проекта)).

### Администрирование

Защищённая админ-панель (`/admin`, доступ по ролям `superadmin` / `admin` / `moderator` /
`support`) и REST-API `/api/admin/*`:

- обзорные метрики: оборот, число сделок, выручка платформы, начисления продавцов,
  активные пользователи, активные лоты, популярные предметы, график выручки;
- пользователи: поиск, блокировка, выдача прав, ручная корректировка баланса, уведомления;
- каталог: категории, коллекции, предметы, выпуск новых предметов, выдача предметов,
  TON-адрес коллекции (проверка через TON API);
- сделки: заказы, возвраты, лоты, транзакции, заявки на выплату;
- модерация: жалобы, отзывы, скрытие отзывов;
- настройки: **комиссия платформы (0–50 %)**, мин/макс цена лота, удержание средств,
  лимит активных лотов, режим обслуживания, минимальная сумма выплаты, текст о выплатах;
- **журнал аудита** всех действий администраторов (кто, что, до/после, IP, user-agent).

### Надёжность

- Транзакционные покупки с блокировкой предмета и лота (`SELECT … FOR UPDATE`);
- защита от двойной продажи (частичный уникальный индекс: один предмет — один активный лот),
- идемпотентная обработка платежей (`WebhookEvent.update_id`, ключи журнала, статусы платежа);
- серверная проверка суммы, валюты, назначения и владельца заказа при оплате;
- rate limiting (отдельные лимиты на авторизацию, запись, кассу, чтение);
- проверка `initData`: HMAC-SHA256, срок жизни, обязательный `auth_date`;
- production-гарды: приложение не стартует с `DEV_AUTH=true`, SQLite, без `BOT_TOKEN`
  или с CORS `*`;
- структурированные логи критических событий (покупка, оплата, передача владения,
  выплата, действия администратора).

Полный API: **83 операции**, OpenAPI — `/docs` (Swagger UI), `/redoc`, `/api/openapi.json`.

---

## Стек

| Слой | Технологии |
|---|---|
| Frontend | React 18, TypeScript (strict), Vite 6, Tailwind CSS v4, React Router 6, TanStack Query 5, Telegram WebApp SDK, lucide-react |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (typed), Pydantic v2 + pydantic-settings, Alembic, psycopg 3, uvicorn |
| БД | PostgreSQL 16 (в Docker/Render); SQLite — только локальная разработка и тесты |
| Тесты | pytest (backend), vitest + jsdom (frontend), ruff |
| Инфраструктура | Docker, docker-compose, Render Blueprint, Cloudflare Pages (или nginx-образ) |

Денежные значения — **целые числа Stars (XTR)**. В коде нет `float` для денег.

---

## Быстрый старт (локально)

Нужно: Python 3.11+, Node.js 20+, npm. PostgreSQL для локального запуска не обязателен —
по умолчанию используется SQLite-файл.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env                 # уже настроен на SQLite + DEV_AUTH
alembic upgrade head                 # создаёт 25 таблиц
python seed.py                       # каталог, коллекционеры, история сделок
uvicorn app.main:app --reload --port 8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/home | head -c 300
```

Swagger: <http://127.0.0.1:8000/docs>.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env                 # VITE_API_URL=/api (прокси на 127.0.0.1:8000)
npm run dev                          # http://localhost:5173
```

Vite проксирует `/api` на `http://127.0.0.1:8000`; в браузере приложение открывается без
Telegram благодаря `DEV_AUTH`.

### 3. Пересоздание демо-базы

```bash
cd backend
source .venv/bin/activate
python seed.py --reset               # удаляет все таблицы и наполняет заново
```

### 4. Полезные команды

```bash
# backend
ruff check app tests seed.py         # линтер
pytest -q                            # 34 теста
alembic revision --autogenerate -m "change"   # новая миграция

# frontend
npm run typecheck                    # tsc --noEmit
npm test                             # 23 теста (vitest)
npm run build                        # production-сборка в dist/
npm run preview                      # предпросмотр сборки на 4173
```

---

## Демо-данные и вход без Telegram

`python seed.py` создаёт:

| Что | Значение |
|---|---|
| Администратор (superadmin) | Telegram ID `900000000`, `@giftmarket_admin` |
| Коллекционеры | `900000001` … `900000006` (`@demo_collector`, `@lunar_maria`, `@kai_flux`, `@nora_vault`, `@atlas_shop`, `@mira_gems`) |
| Каталог | 6 коллекций × 2 предмета, цены от 30 ★ до 2500 ★, лимитированные тиражи |
| История | сделки, отзывы, избранное, лоты, уведомления, начисления |

Если в `backend/.env` задано `ADMIN_TELEGRAM_IDS=900000001`, демо-пользователь
`900000001` тоже получает `superadmin` — удобно, чтобы видеть админку тем же аккаунтом,
от которого совершаются покупки.

**Локальный вход**: в браузере откройте «Профиль» → блок «Демо-идентификация» и введите
Telegram ID (например, `900000002`). Значение хранится в `localStorage` и отправляется
заголовком `X-Dev-Telegram-Id`, который backend принимает **только** при `DEV_AUTH=true`
и `ENV≠production`.

Демо-оплата: на карточке предмета при `dev_mode` доступна кнопка симуляции оплаты
(`POST /api/checkout/dev-pay`). Вне development/prod этот эндпоинт возвращает 404, а
настоящий путь — Telegram-инвойс и webhook.

---

## Как устроены деньги

- **Комиссия платформы** — настройка в БД (`platform_settings.commission_percent`),
  по умолчанию 10 %, допустимый диапазон 0–50 %, меняется в админке. Значение из `.env`
  используется только при первом создании настроек.
- **Формула**: `commission = amount * percent // 100`, `seller = amount - commission`.
  Остаток всегда достаётся продавцу — сумма частей равна сумме платежа.
- **Первичная продажа** (выпуск предмета платформой): продавца нет, вся сумма — выручка
  платформы.
- **Перепродажа**: комиссия платформы + начисление продавцу.
- **Начисления продавца** — журнал (`transactions`) с бакетами `pending` / `available` /
  `platform` / `payout`; средства попадают в `available` после удержания (по умолчанию 72 ч),
  фоновый воркер (`services/maintenance.py`) переводит их по расписанию.
- **Идемпотентность**: операции журнала помечены ключами (`sale:<order>`, `commission:<order>`,
  `release:<tx>`, `refund:<order>`, `payout-request:<id>`, …) с уникальными индексами —
  повторный webhook не начисляет деньги дважды.
- **Все суммы считаются на сервере.** Клиент передаёт только `item_id` / `listing_id`;
  цена, комиссия и сумма выплаты берутся из БД.

> Внутренний баланс — **не** банковский кошелёк и **не** крипто-кошелёк. Заявка на выплату
> переводит средства в состояние «ожидает ручной выплаты»; автоматического вывода Stars или
> TON в проекте нет. Юридически корректный механизм выплат — отдельная задача владельца
> платформы (см. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#выплаты-продавцам-честная-граница)).

---

## Оплата Stars: полный цикл

1. `POST /api/checkout/invoice` — сервер проверяет доступность предмета/лота, считает сумму по
   своей цене, создаёт `orders` + `payments` (статус `pending`), резервирует лот на 20 минут и
   возвращает `invoice_url` из Telegram `createInvoiceLink` (валюта XTR, пустой provider token).
2. Пользователь открывает счёт (`Telegram.WebApp.openInvoice`), Telegram присылает боту
   `pre_checkout_query` → сервер проверяет заказ и отвечает `answerPreCheckoutQuery`.
3. После оплаты приходит `successful_payment` → `verify_and_record_payment` сверяет
   `invoice_payload`, валюту, сумму, срок и статус; затем `fulfill_order` в одной транзакции:
   запись платежа → передача владения и `ownership_history` → финансовый журнал →
   уведомления → статус `fulfilled`.
4. Право собственности никогда не выдаётся по запросу с фронтенда: только этот обработчик
   может завершить заказ.
5. Повторные доставки webhook отсекаются по `update_id` и статусу платежа/заказа;
   расхождение суммы или валюты переводит платёж в `failed`, заказ не исполняется.

Возвраты: `refunds` + `payment.status=refunded` + обратные проводки журнала; возврат Stars
выполняется через Telegram `refundStarPayment` там, где Telegram это поддерживает.

Детали схемы и инвариантов: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Настройка бота и Mini App: [docs/TELEGRAM.md](docs/TELEGRAM.md).

---

## Тесты и проверки

| Набор | Команда | Результат |
|---|---|---|
| Backend: безопасность, комиссия, касса, лоты, выплаты, админка | `cd backend && pytest -q` | **34 passed** |
| Frontend: форматирование денег/дат, API-клиент, ошибки | `cd frontend && npm test` | **23 passed** |
| Backend-линтер | `cd backend && ruff check app tests seed.py` | clean |
| Frontend-типы и сборка | `cd frontend && npm run typecheck && npm run build` | clean |

Что именно покрыто:

- подпись `initData` (валидная, подделанная, просроченная, чужой токен), 401/403, RBAC;
- параметризованный расчёт комиссии, включая `333 ★` при 15 % → `49 / 284`;
- первичная покупка (владение + серийный номер + `minted_count`), перепродажа (сплит 10/90,
  удержание), смена комиссии через админку на 20 %;
- повторная покупка того же предмета → 409, самопокупка → 409, клиентская цена игнорируется;
- идемпотентность webhook, несовпадение суммы, обязательный secret-token, `pre_checkout`;
- жизненный цикл лота: создание, дубль, минимальная цена, изменение цены, отмена, повторное
  выставление, чужое владение → 409, заблокированный пользователь → 403;
- избранное, оффер → принятие → лот, выплаты (удержание, релиз, approve/paid);
- payload главной страницы и маркета.

---

## Структура репозитория

```text
.
├── backend/
│   ├── app/
│   │   ├── api/            # deps, router, routes (public, account, market, admin, telegram)
│   │   ├── core/           # config, enums, logging, rate_limit, security (HMAC initData)
│   │   ├── db/             # base, session, lock helpers
│   │   ├── models/         # 25 SQLAlchemy-моделей (entities.py)
│   │   ├── schemas/        # Pydantic-схемы запросов/ответов
│   │   └── services/       # orders, payments, ledger, ownership, marketplace,
│   │                       # catalog, pricing, notifications, maintenance, ton, audit
│   ├── alembic/            # миграции (initial schema)
│   ├── tests/              # 34 теста
│   ├── scripts/start.sh    # миграции → seed (опционально) → uvicorn
│   ├── seed.py             # демо-данные (--reset)
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/     # Layout, GiftCard, PriceChart, ui, TelegramGate
│   │   ├── context/        # тосты
│   │   ├── hooks/          # useApi, useCheckout, useCollections
│   │   ├── lib/            # api-клиент, telegram SDK, форматирование, типы
│   │   └── pages/          # Home, Market, ItemDetail, Collection, CollectionDetail,
│   │                       # Favorites, Notifications, Orders, Profile, Seller, Admin, About
│   ├── public/             # _redirects, _headers, favicon, изображения подарков
│   ├── Dockerfile, nginx.conf
│   └── .env.example
├── docs/                   # API, ARCHITECTURE, DEPLOY, TELEGRAM
├── docker-compose.yml      # db + api + web
├── render.yaml             # Render Blueprint (API + PostgreSQL)
└── .env.example            # переменные compose
```

---

## Админ-панель

Открывается по адресу `/admin` внутри Mini App, если у пользователя есть роль
администратора (`admin_users.is_active = true` и `users.is_admin = true`).

Назначение первого администратора:

```sql
-- один раз после применения миграций
INSERT INTO admin_users (user_id, role, is_active, created_at)
SELECT id, 'superadmin', true, now() FROM users WHERE telegram_id = <ВАШ_TELEGRAM_ID>;
UPDATE users SET is_admin = true WHERE telegram_id = <ВАШ_TELEGRAM_ID>;
```

либо проще — `ADMIN_TELEGRAM_IDS=<id>` в `.env` до первого запуска (seed/бутстрап выдаст
роль автоматически), либо `python seed.py`, где администратор создаётся из
`ADMIN_TELEGRAM_IDS`.

Каждое изменяющее действие пишется в `audit_logs` вместе с `before`/`after`.

---

## Переменные окружения

Полный контракт — [`backend/.env.example`](backend/.env.example) и
[`frontend/.env.example`](frontend/.env.example); таблица со значениями для продакшена —
в [docs/DEPLOY.md](docs/DEPLOY.md#переменные-окружения).

Минимум для локального запуска:

```env
ENV=development
DATABASE_URL=sqlite:///./gift_market.db
DEV_AUTH=true
ADMIN_TELEGRAM_IDS=900000001
COMMISSION_PERCENT=10
```

Минимум для продакшена:

```env
ENV=production
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/giftmarket
BOT_TOKEN=123456:ABC…
BOT_USERNAME=your_bot
WEBAPP_URL=https://your-frontend.example.com
PUBLIC_BASE_URL=https://your-backend.example.com
WEBHOOK_SECRET=<random 32+ chars>
ADMIN_TELEGRAM_IDS=<your telegram id>
DEV_AUTH=false
CORS_ORIGINS=https://your-frontend.example.com
TRUSTED_HOSTS=your-backend.example.com
```

Приложение откажется стартовать в `ENV=production`, если нарушено любое из условий:
`DEV_AUTH=true`, отсутствует `BOT_TOKEN`, БД не PostgreSQL, пустой `WEBHOOK_SECRET`,
CORS содержит `*`.

---

## Docker и деплой

Один хост целиком:

```bash
# быстрый локальный просмотр (без Telegram, с демо-каталогом)
cp backend/.env.example backend/.env
cp .env.example .env
# в корневом .env: ENV=development и SEED_DEMO_DATA=true
docker compose up --build -d
# web: http://localhost:8080   api: http://localhost:8000
```

Для боевого стенда: в `backend/.env` укажите `ENV=production`, `BOT_TOKEN`, `BOT_USERNAME`,
`WEBAPP_URL`, `PUBLIC_BASE_URL`, `WEBHOOK_SECRET`, `ADMIN_TELEGRAM_IDS`, `DEV_AUTH=false`,
`CORS_ORIGINS`, а в корневом `.env` — пароль PostgreSQL и `SEED_DEMO_DATA=false`.
Без этих значений приложение намеренно не стартует (production-гарды).

Docker-compose поднимает `postgres:16`, API (миграции при старте) и nginx с собранным
фронтендом, проксирующий `/api` в контейнер `api`.

Рекомендуемая связка для интернета:

| Часть | Куда |
|---|---|
| Backend + PostgreSQL | **Render** (Blueprint `render.yaml`) → `https://gift-market-api.onrender.com` |
| Frontend | **Cloudflare Pages** (или nginx-образ из `frontend/Dockerfile`) → `https://gift-market.pages.dev` |

Пошагово, включая настройку CORS, миграций, webhook и проверку платежей:
[docs/DEPLOY.md](docs/DEPLOY.md).

---

## Документация

| Файл | Содержание |
|---|---|
| [docs/API.md](docs/API.md) | авторизация, ошибки, лимиты, все 83 эндпоинта, примеры curl, статусы |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | схема данных, денежные инварианты, транзакция покупки, защиты, TON-хуки, уведомления |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Docker, Render, Cloudflare Pages, PostgreSQL, webhook, бэкапы, чек-лист |
| [docs/TELEGRAM.md](docs/TELEGRAM.md) | создание бота, Mini App, Stars-платежи, webhook, что делает владелец |

Живая спецификация доступна на запущенном backend: `/docs` (Swagger UI) и
`/api/openapi.json`.

---

## Что остаётся за владельцем проекта

Код готов, но эти шаги требуют ваших аккаунтов и внешних сервисов:

1. **Создать бота** в `@BotFather`, получить `BOT_TOKEN` и `BOT_USERNAME`.
2. **Создать Mini App** (BotFather `/newapp` или кнопка меню) и указать URL фронтенда;
   этот же URL прописать в `WEBAPP_URL`.
3. **Развернуть backend и frontend**, заполнить `PUBLIC_BASE_URL`, `CORS_ORIGINS`,
   `TRUSTED_HOSTS`.
4. **Установить webhook** `https://<backend>/api/telegram/webhook` с `secret_token` —
   кнопкой в админке или curl-командой из [docs/DEPLOY.md](docs/DEPLOY.md#webhook-telegram).
5. **Назначить администратора** (`ADMIN_TELEGRAM_IDS`).
6. **Проверить платёж** реальной покупкой за Stars (тестовые платежи в Telegram для Stars
   не предусмотрены — используется минимальный предмет).
7. **Юридический механизм выплат продавцам** — вне кода: налоги, KYC, договор с
   платёжным провайдером. Сейчас заявки только фиксируются и решаются вручную.
8. **TON/NFT** (опционально): если планируется настоящая on-chain коллекция, нужен контракт,
   кошелёк проекта, ключи TON API и отдельная верификация владения. Текущие хуки — только
   хранение адресов и проверка существования адреса.

## Границы реализации

Честно о том, чего нет:

- **Нет автоматического вывода Stars/TON продавцам.** Есть заявка, статусы и ручное
  подтверждение администратором; это сознательное ограничение, а не забытая функция.
- **Нет выпуска NFT.** Внутренние предметы не связаны с блокчейном; поля
  `ton_collection_address`, `nft_address`, `external_verified` существуют для будущей
  интеграции и заполняются только администратором с проверкой.
- **Нет реальной интеграции TON-кошелька на фронтенде** (TonConnect). Привязка адреса —
  текстовое поле с валидацией формата, без подписи кошелька.
- **Нет CSV-экспорта и сложной аналитики** — только обзорные метрики админки.
- Отзывы и офферы реализованы как рабочие сущности, но без чата между пользователями.
