# Архитектура GIFT MARKET

Документ описывает, как устроена система изнутри: слои, схему данных, денежные инварианты,
транзакцию покупки, защиты от мошенничества, фоновые задачи, уведомления, TON-хуки и
границы честности.

- [Обзор](#обзор)
- [Слои и ответственность](#слои-и-ответственность)
- [Схема данных](#схема-данных)
- [Деньги и журнал](#деньги-и-журнал)
- [Транзакция покупки](#транзакция-покупки)
- [Защиты](#защиты)
- [Фоновые задачи](#фоновые-задачи)
- [Уведомления](#уведомления)
- [TON и внешние NFT: хуки без имитации](#ton-и-внешние-nft-хуки-без-имитации)
- [Выплаты продавцам: честная граница](#выплаты-продавцам-честная-граница)
- [Админка и аудит](#админка-и-аудит)
- [Frontend](#frontend)
- [Расширение](#расширение)

---

## Обзор

```text
Telegram (Mini App)                Cloudflare Pages / nginx            Render / Docker
┌──────────────────┐    HTTPS     ┌────────────────────┐   /api      ┌──────────────────────┐
│ React 18 + Vite  │─────────────▶│ статика + прокси   │────────────▶│ FastAPI + SQLAlchemy │
│ Telegram WebApp  │              └────────────────────┘             │  ┌────────────────┐  │
└────────┬─────────┘                                                │  │ services/*     │  │
         │ initData (подпись)                                        │  └───────┬────────┘  │
         │                                                           │          │           │
         ▼                                                           │  ┌───────▼────────┐  │
   Telegram Bot API ◀──── webhook (X-Telegram-Bot-Api-Secret-Token)──│  │ platform/ledger│  │
   pre_checkout_query, successful_payment                            │  └───────┬────────┘  │
                                                                     └──────────┼───────────┘
                                                                                ▼
                                                                        PostgreSQL 16
```

Один процесс API = HTTP-слой + фоновый maintenance-loop (в каждом воркере, с
`job_locks`, чтобы задачи не дублировались).

---

## Слои и ответственность

| Слой | Где | Что делает |
|---|---|---|
| HTTP / валидация | `app/api/routes/*`, `app/schemas/*` | Pydantic-схемы, права, пагинация, коды ошибок |
| Авторизация | `app/core/security.py`, `app/api/deps.py` | HMAC-проверка `initData`, создание пользователя, роли |
| Домен | `app/services/*` | Заказы, платежи, владение, лоты, журнал, уведомления |
| Данные | `app/models/entities.py`, `alembic/` | 25 таблиц, индексы, CHECK/UNIQUE, партиальный уникальный индекс |
| Фон | `app/services/maintenance.py` | Резервы, просроченные заказы, созревание удержаний |
| Интеграции | `telegram_bot.py`, `ton.py` | Bot API (HTTPS), TON API (только чтение адреса) |

Правило: **route не считает деньги**. Роут валидирует вход и вызывает сервис; сервис
читает цену/комиссию из БД и пишет проводки.

---

## Схема данных

25 таблиц в одной миграции `d50396de1f46_initial_schema.py`.

### Пользователи и доступ

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `users` | `telegram_id`, `username`, `first_name/last_name`, `photo_url`, `is_admin`, `is_blocked`, `blocked_reason`, `show_collection`, `allow_offers`, `notify_sales`, `notify_market`, `ton_address`, `ton_address_verified_at`, `sales_count`, `purchases_count`, `rating_count`, `rating_sum`, `last_seen_at` | `UNIQUE(telegram_id)`, индекс `username`, CHECK счётчиков ≥ 0 |
| `admin_users` | `user_id`, `role` (`superadmin`/`admin`/`moderator`/`support`), `is_active`, `note` | `UNIQUE(user_id)`, FK → `users` |
| `user_settings` | `user_id`, `locale` | `UNIQUE(user_id)` |

### Каталог

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `categories` | `slug`, `name`, `description`, `emoji`, `sort_order`, `is_active` | `UNIQUE(slug)` |
| `collections` | `slug`, `name`, `description`, `cover_url`, `accent`, `category_id`, `rarity`, `status`, `is_featured`, `released_at`, `ton_collection_address`, `chain_verified` | `UNIQUE(slug)`, CHECK rarity, индексы `(status, is_featured)`, `category_id` |
| `collection_items` | `collection_id`, `name`, `description`, `image_url`, `back_image_url`, `glow`, `rarity`, `rarity_weight`, `edition_size`, `minted_count`, `primary_price_stars`, `is_limited`, `is_serialized`, `status`, `source`, `is_tradeable`, `is_featured`, `external_url` | `UNIQUE(collection_id, name)`, CHECK rarity/тираж/цена, индексы по редкости+статусу, дате, коллекции |

### Владение

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `gift_ownership` | `item_id`, `owner_id`, `serial_number`, `status` (`owned`/`burned`), `acquisition_type` (`primary`/`resale`/`admin_grant`), `acquired_at`, `acquired_price_stars` | `UNIQUE(item_id, serial_number)`, CHECK серийного номера, индексы владельца/статуса |
| `ownership_history` | `ownership_id`, `from_user_id`, `to_user_id`, `order_id`, `event` (`mint`/`resale`/`admin_grant`/`transfer`), `price_stars` | индекс `(ownership_id, created_at)` |

Серийный номер выдаётся как `item.minted_count + 1` под блокировкой строки предмета, поэтому
дубликатов не бывает даже при параллельных покупках.

### Торговля

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `marketplace_listings` | `ownership_id`, `seller_id`, `price_stars`, `status` (`active`/`reserved`/`sold`/`cancelled`/`expired`), `views`, `reserved_order_id`, `reserved_until`, `sold_order_id`, `sold_at`, `cancelled_at`, `listed_at` | CHECK статуса и цены; **частичный UNIQUE `uq_listing_active_ownership`** по `ownership_id` WHERE `status IN ('active','reserved')`; индексы по статусу+цене/дате, продавцу |
| `offers` | `ownership_id`, `buyer_id`, `seller_id`, `price_stars`, `message`, `status` | CHECK цены, индексы продавца/статуса |
| `price_history` | `item_id`, `ownership_id`, `listing_id`, `scope` (`gift`/`ownership`), `event` (`listed`/`price_changed`/`sold`/`cancelled`), `price_stars` | индексы по предмету/экземпляру и дате |

Частичный уникальный индекс — ключевое решение: у предмета может быть много исторических
лотов, но **не более одного активного**, при этом перевыставление после отмены не блокируется.

### Заказы и платежи

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `orders` | `order_number` (`GM-YYMMDD-XXXXXX`), `payload` (UUID для инвойса), `buyer_id`, `seller_id` (NULL для первичной продажи), `item_id`, `ownership_id`, `listing_id`, `order_type`, `status`, `amount_stars`, `currency` (`XTR`), `commission_percent`, `commission_stars`, `seller_amount_stars`, `hold_until`, `expires_at`, `paid_at`, `fulfilled_at`, `failure_reason` | `UNIQUE(order_number)`, `UNIQUE(payload)`, CHECK суммы > 0, CHECK статуса, **CHECK `commission + seller = amount`**, индексы покупателя/продавца/статуса+даты |
| `payments` | `order_id`, `provider` (`telegram_stars`), `invoice_payload`, `telegram_payment_charge_id`, `provider_payment_charge_id`, `amount_stars`, `currency`, `status`, `is_test`, `invoice_url`, `paid_at`, `raw_update` | `UNIQUE(invoice_payload)`, `UNIQUE(order_id)`, UNIQUE charge-id (когда задан), CHECK суммы |
| `refunds` | `order_id`, `payment_id`, `amount_stars`, `status` (`requested`/`processing`/`completed`/`failed`), `reason`, `telegram_refund_id`, `error`, `requested_by_user_id`, `completed_at` | CHECK суммы, индексы заказа/статуса |

`orders.payload` — случайный UUID, который уходит в Telegram; `order_number` — человекочитаемый
номер для UI и поддержки. Их нельзя путать: payload не показывается пользователю, номер не
используется для поиска платежа.

### Финансы

| Таблица | Ключевые поля | Ограничения |
|---|---|---|
| `transactions` | `user_id`, `order_id`, `payout_id`, `refund_id`, `type`, `bucket` (`pending`/`available`/`platform`/`payout`/`external`), `amount_stars`, `balance_after`, `description`, `idempotency_key` | `UNIQUE(idempotency_key)`, CHECK `amount_stars <> 0`, индексы пользователя/заказа/типа/даты |
| `seller_balances` | `user_id`, `pending_stars`, `available_stars`, `withdrawn_stars`, `lifetime_stars`, `currency`, `version` | `UNIQUE(user_id)`, CHECK всех счётчиков ≥ 0 |
| `payout_requests` | `user_id`, `amount_stars`, `method` (`stars_manual`/`bank_manual`/`ton_manual`), `destination`, `status` (`requested`/`approved`/`rejected`/`paid`), `admin_note`, `decided_by_user_id`, `decided_at`, `paid_at`, `external_reference` | CHECK суммы, индексы статуса/пользователя |
| `platform_settings` | `id=1`, `commission_percent`, `min_listing_price`, `max_listing_price`, `hold_hours`, `maintenance_mode`, `maintenance_message`, `max_active_listings`, `min_payout_stars`, `payout_note`, `terms_url`, `updated_by_user_id` | CHECK комиссии 0–50, `max ≥ min`, `min_payout > 0` |

### Прочее

| Таблица | Назначение |
|---|---|
| `favorites` | `UNIQUE(user_id, item_id)` |
| `reviews` | `UNIQUE(order_id)` — один отзыв на заказ, CHECK рейтинга 1–5, индекс продавца |
| `notifications` | тип, заголовок, текст, JSON-payload, `is_read`, `telegram_sent_at`, `telegram_error` |
| `reports` | жалобы: `target_type`, `target_id`, `reason`, `details`, `status`, `resolution` |
| `audit_logs` | `admin_user_id`, `action`, `entity_type`, `entity_id`, `before`, `after`, `ip_address`, `user_agent` |
| `webhook_events` | `UNIQUE(update_id)`, `update_type`, `payload`, `processed`, `error`, `received_at`, `processed_at` |
| `job_locks` | распределённая блокировка фоновых задач (`name`, `locked_until`, `holder`) |

---

## Деньги и журнал

### Формула

```python
commission = amount * percent // 100
seller     = amount - commission
assert commission + seller == amount      # гарантировано CHECK-констрейнтом в orders
```

`percent` читается из `platform_settings` в момент покупки и **замораживается** в заказе
(`orders.commission_percent`), поэтому смена настроек не переписывает историю.

- **Первичная продажа**: `seller_id = NULL`, `commission = amount`, `seller = 0` — вся сумма
  выручка платформы.
- **Перепродажа**: сплит по проценту; продавцу начисляется `seller`.

### Проводки

Журнал `transactions` — append-only. Каждая запись имеет уникальный `idempotency_key`:

| Событие | Ключ | Бакеты |
|---|---|---|
| Продажа | `sale:<order_id>` | `pending` (продавцу) |
| Комиссия | `commission:<order_id>` | `platform` |
| Созревание удержания | `release:<transaction_id>` | `pending → available` |
| Возврат | `refund:<order_id>` (+ `refund-commission:`, `refund-seller:`) | обратные проводки |
| Заявка на выплату | `payout-request:<payout_id>` | `available → payout` |
| Отклонение заявки | `payout-reversal:<payout_id>` | `payout → available` |
| Выплата | `payout-paid:<payout_id>` | `payout → external` |
| Ручная корректировка | `admin-adjust:<uuid>` | `available` |

`balance_after` фиксируется в момент проводки — журнал можно сверять с `seller_balances`.

### Удержание

После продажи средства попадают в `pending` и зреют `hold_hours` (по умолчанию 72).
`ledger.settle_due_holds()` в фоновом цикле переносит их в `available` отдельной проводкой
`settlement`. Пока удержание активно, продавец не может вывести эти средства: заявка
проверяет `available_stars`.

> Баланс — **внутренний учёт**, не кошелёк. См. [«Выплаты продавцам»](#выплаты-продавцам-честная-граница).

---

## Транзакция покупки

### 1. Создание заказа (`POST /checkout/invoice`)

```text
BEGIN
  item/listing = SELECT ... FOR UPDATE          # lock_row()
  проверить: активен, не свой, тираж не распродан, tradeable
  amount = listing.price_stars | item.primary_price_stars   # только из БД
  commission, seller = split(amount, platform.commission_percent)
  order = INSERT orders(... status=pending_payment, expires_at=now+20m, payload=uuid4)
  payment = INSERT payments(... status=pending)
  если перепродажа: listing.status='reserved', reserved_order_id=order.id, reserved_until=now+20m
  если есть бот: invoice_url = Telegram createInvoiceLink(XTR, amount, payload)
COMMIT
```

При ошибке Telegram — `ROLLBACK`, пользователь получает 409/502 и не остаётся с «висящим»
резервом.

### 2. `pre_checkout_query`

Проверяется: платёж существует, заказ `pending_payment`, сумма и валюта совпадают с заказом,
лот всё ещё `reserved` этим заказом или `active`, тираж не распродан, срок не истёк.
Ответ — `answerPreCheckoutQuery(ok)`; при отказе пользователь видит причину.

### 3. `successful_payment` → `verify_and_record_payment`

```text
invoice_payload → payment → FOR UPDATE order
charge_id не использован другим платежом          # защита от повторного использования
если payment.succeeded: вернуть (order, False)     # идемпотентно
currency == 'XTR' == order.currency
total_amount == order.amount_stars == payment.amount_stars
payment.status = succeeded, charge_id, paid_at, raw_update
order.status = paid (или paid с пометкой «оплата после истечения»)
```

Любое расхождение → `FraudError` → платёж не записывается, деньги не «присваиваются»,
событие остаётся в `webhook_events` с ошибкой.

### 4. Исполнение (`fulfill_paid_order`)

```text
BEGIN
  order = SELECT ... FOR UPDATE
  если fulfilled -> return (идемпотентно)
  buyer активен
  если resale:  listing FOR UPDATE, ownership FOR UPDATE, owner == seller, status owned
                transfer_resale(): owner=buyer, history(resale), order.ownership_id
                listing = sold
  иначе:        item FOR UPDATE, mint_primary(): serial = minted_count+1,
                ownership(primary), history(mint), item.minted_count += 1,
                если тираж исчерпан -> status=sold_out
  ledger.credit_sale(order)
  order.status = fulfilled, fulfilled_at, hold_until
  price_history(sold)
  notifications: покупка / продажа / начисление
COMMIT
```

Если исполнение невозможно (предмет продан другому, владелец изменился), заказ переходит в
`refund_pending`, создаётся запись `refunds`, пользователю уходит уведомление, а
`refund_stars_payment` вызывается там, где это поддерживает Telegram. Деньги при этом не
«теряются»: они отмечены как подлежащие возврату.

### 5. Возврат

`refunds.status`: `requested → processing → completed | failed`. Обратные проводки журнала
восстанавливают балансы продавца и платформы; заказ — `refund_pending` → `refunded`.

---

## Защиты

| Угроза | Механизм | Где |
|---|---|---|
| Подделка `initData` | HMAC-SHA256 по `WebAppData` + сравнение `hmac.compare_digest`, проверка `auth_date` | `core/security.py` |
| Просроченный initData | `INIT_DATA_MAX_AGE_SECONDS` (24 ч) + обязательный `auth_date` | `core/security.py` |
| Dev-заголовок в проде | `DEV_AUTH` игнорируется при `ENV=production`; прод-гард не даёт стартовать | `core/config.py` |
| Подмена цены | клиент не передаёт сумму; цена из `listing`/`item` под блокировкой | `services/orders.py` |
| Двойная продажа | `SELECT … FOR UPDATE` на `listing` + `ownership`, проверка `reserved_order_id`, частичный UNIQUE на активный лот | `services/orders.py`, модель |
| Конкурентная покупка | резерв лота на 20 мин, 409 при занятом лоте | `services/marketplace.py` |
| Повтор платежа | `UNIQUE(webhook_events.update_id)`, `UNIQUE(payments.invoice_payload)`, уникальный charge-id, идемпотентные ключи журнала | `api/routes/telegram.py`, `services/payments.py` |
| Подмена суммы в webhook | сверка `currency`, `total_amount`, `payload`, срока | `services/orders.py` |
| Чужое владение | проверка `ownership.owner_id == seller_id`, 409 | `services/marketplace.py` |
| Несанкционированная передача | передача только внутри `fulfill_paid_order`; отдельного «transfer» API нет | `services/orders.py` |
| Самопокупка | проверка покупателя и продавца/владельца | `services/orders.py` |
| Блокировка пользователя | `is_blocked` проверяется при покупке/продаже/выплате | `api/deps.py`, сервисы |
| Злоупотребление запросами | rate limiting по пути и идентичности | `core/rate_limit.py` |
| SQL-инъекции | только параметризованные запросы SQLAlchemy, никакой конкатенации SQL | везде |
| Секреты | только env, `.env` в `.gitignore`, в прод-гардах обязательные ключи | `core/config.py` |
| Скрытие ошибок | нейтральные сообщения 500 вне development, `X-Request-Id` для корреляции | `main.py` |
| Некорректные деньги | CHECK-констрейнты `commission + seller = amount`, `> 0`, `<> 0` | миграция |
| Потеря аудита | все админ-мутации проходят через `audit.log_action` | `services/audit.py` |

---

## Фоновые задачи

`maintenance_loop` запускается в lifespan и раз в `CLEANUP_INTERVAL_SECONDS` (60 с)
выполняет под `job_locks`:

1. `release_expired_reservations` — снимает `reserved` с истёкших лотов;
2. `expire_stale_orders` — переводит просроченные `pending_payment` в `expired`,
   освобождает резерв, помечает платёж;
3. `settle_due_holds` — созревает удержания (`pending → available`).

Так как loop есть в каждом воркере, `job_locks` гарантирует, что тик выполнит только один
процесс. Для нескольких инстансов за пределами одного хоста нужен внешний планировщик или
Redis-лок.

---

## Уведомления

`notifications.create_notification()` всегда пишет запись в БД (её видно в `/notifications`),
а затем best-effort отправляет сообщение в Telegram. Ошибки Telegram не ломают сделку —
они сохраняются в `telegram_error`.

| Событие | Кому | Тип |
|---|---|---|
| Счёт создан | покупателю | `payment_status` |
| Покупка завершена | покупателю | `purchase` |
| Продажа завершена | продавцу | `sale` |
| Начисление / созревание | продавцу | `seller_credit` |
| Лот выставлен / отменён | владельцу | `listing_created` / `listing_cancelled` |
| Оффер получен / принят | продавцу / покупателю | `offer` |
| Заявка на выплату и её статус | продавцу | `payout` |
| Системные сообщения | любому | `system` / `admin` |

Счётчик непрочитанных отдаёт `/api/notifications?unread_only=true` и бейдж в навигации.

---

## TON и внешние NFT: хуки без имитации

Что есть:

- `users.ton_address`, `users.ton_address_verified_at` — привязка адреса;
- `collections.ton_collection_address`, `collections.chain_verified` — адрес коллекции и
  флаг проверки;
- `collection_items.source` (`internal` / `telegram_official` / `external_nft`) и
  `external_url`;
- `POST /admin/collections/{id}/verify-ton` — проверка **существования** адреса через
  TON API (`tonapi.io`), с записью в аудит;
- `app/services/ton.py` — изолированный клиент с таймаутами и понятными ошибками.

Чего сознательно нет:

- минта NFT, деплоя контрактов, подписи транзакций;
- TonConnect на фронтенде и проверки подписи кошелька (адрес — просто строка с валидацией
  формата);
- заявлений, что внутренний предмет «в блокчейне».

Чтобы добавить настоящие NFT, потребуется: контракт коллекции (TEP-62/TEP-64), кошелёк
проекта, ключи, индексатор (TON API/Toncenter), верификация владения через доверенный
источник и отдельная миграция. Тогда `source=external_nft` и `chain_verified=true` станут
осмысленными, а UI сможет показывать ссылку на эксплорер.

---

## Выплаты продавцам: честная граница

Реализовано:

- начисление 90 % от суммы перепродажи в `pending`, созревание в `available`;
- заявка продавца (`payout_requests`) с методом и реквизитами;
- списание в бакет `payout`, решение администратора (`approved` / `rejected` / `paid`),
  внешний референс и аудит;
- текст-предупреждение `payout_note` в UI и API.

Не реализовано и не имитируется:

- автоматический вывод Stars: Telegram Bot API не предоставляет payout-API для Stars
  третьим лицам; прямой перевод требует иных договорённостей;
- автоматический вывод TON: нужен кастодиальный кошелёк, подпись транзакций и юридическая
  модель;
- налоги, KYC/AML, договор с платёжным провайдером.

Поэтому выплата — **ручная операция вне системы**, а заявка — учётная запись о намерении.
Это явно написано в интерфейсе (`payout_note`), в API (`/me/balance`) и в документации.

---

## Админка и аудит

- роли в `admin_users`, проверка в `require_admin` / `require_superadmin`;
- все мутации вызывают `audit.log_action(db, admin=…, action=…, entity_type=…, entity_id=…,
  before=…, after=…, request=…)`;
- настройки платформы меняются только `superadmin`/`admin`, комиссия валидируется 0–50 %;
- `GET /admin/overview` собирает метрики SQL-агрегатами (оборот, выручка, сделки, активные
  пользователи за 7/30 дней, активные лоты, топ предметов, серия выручки);
- UI админки (`/admin`) повторяет эти операции и не содержит кнопок без обработчиков.

---

## Frontend

- **Vite 6 + React 18 + TS strict**; страницы — `lazy()`-чанки, ошибки ловит `ErrorBoundary`.
- **TanStack Query** — кэш, инвалидация после мутаций, оптимистичных денежных изменений нет.
- **API-клиент** (`lib/api.ts`) — единая точка: заголовок `Authorization: tma <initData>`,
  нормализация ошибок в `ApiError` с русским текстом, отсутствие цен в запросах.
- **Telegram SDK** (`lib/telegram.ts`) — `initData`, haptics, `openInvoice`, BackButton,
  MainButton, тема; все вызовы защищены от отсутствия SDK (браузер).
- **Дизайн** — тёмная тема, Tailwind v4 `@theme`, mobile-first, нижняя навигация из 5 вкладок,
  safe-area, анимации появления, 3D-подобные карточки подарков (слои, блики, параллакс).
- **Честность данных** — на фронтенде нет «заглушечных» балансов и фиктивных кнопок;
  баланс, комиссия и статусы приходят с сервера.

---

## Расширение

- **Новые платёжные провайдеры**: `payments.provider` — enum; добавьте сервис, вебхук и
  отдельный `verify_*`, не меняя логику владения.
- **Redis для лимитов и лocks**: заменить реализацию `RateLimiter` и `job_locks` (интерфейсы
  минимальные).
- **Партиционирование `transactions`/`price_history`** по дате при росте объёма.
- **Read-replica** для каталога: все публичные чтения идут через `select`, без записи.
- **NFT-слой**: отдельный сервис верификации владения, а не правки в `orders.py`.
- **Аналитика**: `audit_logs`, `transactions`, `orders` уже содержат достаточные поля для
  выгрузки в DWH.
