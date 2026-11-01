# API GIFT MARKET

REST API маркетплейса: каталог, покупка за Telegram Stars, инвентарь, перепродажа,
внутренний журнал начислений, уведомления и админ-панель.

- **База**: `https://<backend-host>/api`
- **Формат**: JSON, `Content-Type: application/json`
- **OpenAPI**: `/docs` (Swagger UI), `/redoc`, `/api/openapi.json`
- **Версия**: 1.0.0
- **Деньги**: целые числа в Stars (XTR), поле всегда оканчивается на `_stars`

---

## Содержание

- [Авторизация](#авторизация)
- [Соглашения](#соглашения)
- [Ошибки](#ошибки)
- [Лимиты запросов](#лимиты-запросов)
- [Эндпоинты](#эндпоинты)
  - [Служебные](#служебные)
  - [Каталог](#каталог)
  - [Аккаунт](#аккаунт)
  - [Маркетплейс и покупка](#маркетплейс-и-покупка)
  - [Telegram webhook](#telegram-webhook)
  - [Администрирование](#администрирование)
- [Сценарии](#сценарии)
- [Перечисления](#перечисления)

---

## Авторизация

Каждый защищённый запрос отправляет подписанные данные Telegram Mini App:

```http
Authorization: tma query_id=AAH...&user=%7B%22id%22%3A123%7D&auth_date=1730000000&hash=...
```

Сервер проверяет `HMAC-SHA256(bot_token, data_check_string)`, срок жизни `auth_date`
(по умолчанию 86400 с) и создаёт/обновляет пользователя. Никаких паролей и cookie нет.

| Заголовок | Назначение |
|---|---|
| `Authorization: tma <initData>` | основной способ (Telegram Mini App) |
| `X-Dev-Telegram-Id: <id>` | **только** при `DEV_AUTH=true` и `ENV≠production` |
| `X-Request-Id` | необязательный; возвращается в ответе для трассировки |

Публичные эндпоинты (`/home`, `/market`, `/items`, `/collections`, `/sellers`, `/config`,
`/meta`, `/categories`) работают без авторизации, но при её наличии добавляют
персональные поля (`favorite`, `owned_by_me`, `can_buy`).

Роли:

| Роль | Доступ |
|---|---|
| `user` | аккаунт, покупки, лоты, выплаты |
| `moderator` / `support` | только чтение админ-разделов |
| `admin` | админ-разделы + изменения каталога и модерация |
| `superadmin` | всё, включая настройки, комиссию, выплаты, роли |

403 при отсутствии роли, 401 при отсутствии/невалидной авторизации.

---

## Соглашения

- **Пагинация**: `page` (с 1), `page_size`; ответ —
  `{ "items": [...], "total": 123, "page": 1, "page_size": 24, "pages": 6 }`.
- **Даты**: ISO-8601 без таймзоны, всегда UTC (`2026-11-01T12:00:00`). Фронтенд
  интерпретирует такие строки как UTC.
- **Деньги**: только целые числа; суммы рассчитывает сервер.
- **Идентификаторы**: `id` — внутренние; публичный номер заказа — `order_number`
  (`GM-YYMMDD-XXXXXX`), он и показывается пользователю.
- **Идемпотентность**: повторный вызов создания инвойса для недоступного лота вернёт 409;
  повторная доставка webhook не меняет состояние; `POST /checkout/dev-pay` идемпотентен по
  статусу заказа.
- **Никаких цен с клиента**: `POST /checkout/invoice` принимает только `item_id` или
  `listing_id`.

---

## Ошибки

```json
{ "detail": "Лот уже продан" }
```

- `detail` — строка, готовая к показу пользователю (на русском);
- 422 от FastAPI возвращает массив `detail[]` с `loc` и `msg` — клиент сворачивает его в
  строку (`price_stars: must be greater than 0`);
- 401 дополнительно содержит `"auth_required": true` и заголовок `WWW-Authenticate: Telegram`;
- 429 — `Retry-After` в секундах;
- 500 — нейтральное сообщение (в development — тип и текст исключения).

| Код | Когда |
|---|---|
| 200 / 201 / 204 | успех / создано / без тела |
| 400 | некорректный JSON, неподдерживаемая операция |
| 401 | нет/просрочена/подделана авторизация |
| 403 | нет прав, пользователь заблокирован, чужой ресурс |
| 404 | объект не найден (или скрыт) |
| 409 | конфликт состояния: лот занят, предмет продан, дубль, самопокупка |
| 422 | ошибка валидации схемы |
| 429 | rate limit |
| 500 / 502 | внутренняя ошибка / недоступность Telegram API |

---

## Лимиты запросов

Скользящее окно в памяти процесса, раздельно по пути и идентичности (Telegram-пользователь,
dev-ID или IP). Настраивается в `.env`:

| Группа | Переменная | По умолчанию | Применяется к |
|---|---|---|---|
| Чтение | `RATE_LIMIT_READ` | `300/60` | каталог, аккаунт-чтение, продавцы |
| Запись | `RATE_LIMIT_WRITE` | `60/60` | лоты, офферы, отзывы, жалобы, админ-мутации |
| Касса | `RATE_LIMIT_CHECKOUT` | `15/60` | `/checkout/*` |
| Авторизация | `RATE_LIMIT_AUTH` | `60/60` | резерв для auth-эндпоинтов |

> Лимитер — дополнительная защита для одного инстанса. При горизонтальном масштабировании
> замените бэкенд лимитера на Redis (интерфейс `RateLimiter` минимальный).

---

## Эндпоинты

Ниже — все 83 операции. Полные схемы — в `/docs`.

### Служебные

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | liveness: `{status, env, version, time}` |
| GET | `/health/ready` | readiness: проверка БД и настроек |
| GET | `/meta` | `{bot_username, webapp_url, dev_mode, bot_configured, ton_enabled, currency}` |
| GET | `/config` | комиссия, мин/макс цена лота, удержание, мин. выплата, режим обслуживания |

### Каталог

| Метод | Путь | Описание |
|---|---|---|
| GET | `/home` | главная: `featured`, `trending`, `new_arrivals`, `rare_collections`, `recent_sales`, `top_sellers`, `recommended`, `stats` |
| GET | `/market` | список лотов/первичных предметов |
| GET | `/items` | первичный каталог предметов |
| GET | `/items/{item_id}` | карточка предмета |
| GET | `/market/listings/{listing_id}` | карточка конкретного лота |
| GET | `/collections` | коллекции (`rarity`, `category`, `featured`, `limit`) |
| GET | `/collections/{slug}` | коллекция + её предметы |
| GET | `/categories` | категории |
| GET | `/sellers/{user_id}` | профиль продавца, статистика, рейтинг |
| GET | `/sellers/{user_id}/reviews` | отзывы о продавце |
| GET | `/sellers/{user_id}/listings` | активные лоты продавца |
| GET | `/sellers/{user_id}/collection` | публичная коллекция (если разрешено настройками) |

Параметры `/market` и `/items`:

| Параметр | Тип | Значение |
|---|---|---|
| `q` | string ≤ 80 | поиск по названию, коллекции, описанию |
| `collection` | string | slug коллекции |
| `category` | string | slug категории |
| `rarity` | repeated | `common`, `uncommon`, `rare`, `epic`, `legendary` |
| `min_price` / `max_price` | int | границы в Stars |
| `kind` | enum | `all` \| `primary` \| `resale` (только `/market`) |
| `sort` | enum | `recent` (по умолчанию), `price_asc`, `price_desc`, `popular`, `rarity` |
| `page`, `page_size` | int | `page_size` ≤ 60 |

### Аккаунт

| Метод | Путь | Описание |
|---|---|---|
| GET | `/me` | профиль, настройки, статистика, баланс, `is_admin`, роль |
| PATCH | `/me/settings` | `show_collection`, `allow_offers`, `notify_sales`, `notify_market` |
| POST | `/me/ton` | привязать TON-адрес (формат проверяется, подпись кошелька — нет) |
| GET | `/me/balance` | баланс продавца: `pending`, `available`, `withdrawn`, `lifetime`, `hold_hours`, `payout_note` |
| GET | `/me/transactions` | журнал транзакций пользователя |
| GET | `/me/collection` | инвентарь: серийный номер, дата, лот, оценка, `can_list` |
| GET | `/me/collection/{ownership_id}` | предмет + история владения и цен |
| GET | `/me/listings` | мои лоты |
| GET | `/me/payouts` | мои заявки на выплату |
| POST | `/me/payouts` | создать заявку: `amount_stars`, `method`, `destination` |
| GET | `/me/offers?direction=incoming\|outgoing` | офферы |
| GET | `/favorites` | избранное |
| POST | `/favorites/{item_id}` | переключить избранное |
| GET | `/notifications` | уведомления (`unread_only`) |
| POST | `/notifications/read` | отметить прочитанными (`null` = все) |

### Маркетплейс и покупка

| Метод | Путь | Описание |
|---|---|---|
| POST | `/listings` | выставить предмет: `{ownership_id, price_stars}` |
| PATCH | `/listings/{listing_id}` | изменить цену `{price_stars}` (только владелец) |
| DELETE | `/listings/{listing_id}` | отменить лот |
| GET | `/listings/{listing_id}` | публичные данные лота |
| POST | `/checkout/invoice` | создать заказ и счёт: `{item_id}` или `{listing_id}` |
| POST | `/checkout/dev-pay` | **только dev/staging**: имитация подтверждённой оплаты |
| GET | `/orders?role=buyer\|seller` | мои заказы (`status`) |
| GET | `/orders/{order_id}` | детали заказа (покупатель или продавец) |
| GET | `/orders/{order_id}/receipt` | чек: номер, суммы, комиссия, платёж |
| POST | `/orders/{order_id}/refund` | запрос возврата покупателем |
| POST | `/reviews` | отзыв: `{order_id, rating 1..5, comment}` |
| POST | `/offers` | оффер продавцу: `{ownership_id, price_stars, message}` |
| POST | `/offers/{offer_id}/accept` | принять оффер → создаётся лот по цене оффера |
| POST | `/offers/{offer_id}/decline` | отклонить оффер |
| POST | `/reports` | жалоба: `{target_type, target_id, reason, details}` |

`POST /checkout/invoice` ответ:

```json
{
  "order_id": 42,
  "order_number": "GM-261101-7K3M9A",
  "amount_stars": 1200,
  "currency": "XTR",
  "status": "pending_payment",
  "invoice_url": "https://t.me/$...",
  "expires_at": "2026-11-01T12:20:00",
  "commission_stars": 120,
  "seller_amount_stars": 1080,
  "item_name": "Violet Heart",
  "dev_simulated": false
}
```

`dev_simulated: true` — backend работает без `BOT_TOKEN` (только вне production), счёт
оплачивается через `/checkout/dev-pay`. Попытка вызвать `/checkout/dev-pay` в production → 404.

### Telegram webhook

| Метод | Путь | Описание |
|---|---|---|
| POST | `/telegram/webhook` | обновления бота: `pre_checkout_query`, `successful_payment`, `/start` |
| GET | `/telegram/webhook` | проверка конфигурации |

Webhook защищён заголовком `X-Telegram-Bot-Api-Secret-Token` (значение `WEBHOOK_SECRET`).
При несовпадении — 403. Каждый `update_id` сохраняется в `webhook_events`; повторная
доставка возвращает `{"ok": true, "duplicate": true}` без побочных эффектов.

### Администрирование

Все пути ниже требуют `admin`, мутации с пометкой ★ — `superadmin`/`admin`.

| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/overview` | оборот, выручка, сделки, активные пользователи, лоты, топ-предметы, серии |
| GET | `/admin/stats` | агрегированная статистика |
| GET | `/admin/users` | `q`, `blocked`, пагинация |
| PATCH | `/admin/users/{user_id}` ★ | `is_blocked`, `blocked_reason`, `is_admin`, `admin_role` |
| POST | `/admin/users/{user_id}/balance` ★ | корректировка баланса `{user_id, amount_stars, reason}` |
| POST | `/admin/users/{user_id}/notify` ★ | уведомление `?title=&body=` |
| GET | `/admin/categories` | категории с количеством коллекций |
| POST | `/admin/categories` ★ | создать категорию |
| PATCH | `/admin/categories/{id}` ★ | изменить категорию |
| GET | `/admin/collections` | коллекции |
| POST | `/admin/collections` ★ | выпустить коллекцию (`slug`, `name`, `rarity`, `status`, `category_id`, …) |
| PATCH | `/admin/collections/{id}` ★ | изменить коллекцию |
| POST | `/admin/collections/{id}/verify-ton` ★ | проверить TON-адрес через TON API |
| GET | `/admin/items` | предметы (`q`, `collection_id`) |
| POST | `/admin/items` ★ | создать предмет (`primary_price_stars`, `edition_size`, `rarity`, …) |
| PATCH | `/admin/items/{id}` ★ | изменить предмет |
| POST | `/admin/gifts/grant` ★ | выдать предмет `{user_id, item_id, quantity, reason}` |
| GET | `/admin/orders` | заказы (`status`, `q`) |
| POST | `/admin/orders/{id}/refund` ★ | возврат `?reason=` |
| GET | `/admin/listings` | лоты (`status`) |
| POST | `/admin/listings/{id}/cancel` ★ | принудительно снять лот |
| GET | `/admin/transactions` | журнал (`type`, `bucket`) |
| GET | `/admin/payouts` | заявки на выплату (`status`) |
| POST | `/admin/payouts/{id}` ★ | решение `{status: approved\|rejected\|paid, admin_note, external_reference}` |
| GET | `/admin/refunds` | возвраты |
| GET | `/admin/reports` | жалобы (`status`) |
| POST | `/admin/reports/{id}` ★ | решение `{status, resolution}` |
| GET | `/admin/reviews` | отзывы |
| POST | `/admin/reviews/{id}/hide` ★ | скрыть отзыв |
| GET | `/admin/settings` | настройки платформы |
| PATCH | `/admin/settings` ★ | комиссия (0–50), цены, удержание, обслуживание, выплаты |
| GET | `/admin/audit-logs` | журнал действий (`action`) |
| GET | `/admin/admins` ★ | список администраторов |
| GET | `/admin/telegram/status` | состояние бота и webhook |
| POST | `/admin/telegram/setup-webhook` ★ | зарегистрировать webhook |

Каждое изменяющее действие пишется в `audit_logs` (`admin_id`, `action`, `entity_type`,
`entity_id`, `before`, `after`, `ip_address`, `user_agent`, `created_at`).

---

## Сценарии

### 1. Покупка нового предмета (первичная продажа)

```bash
API=https://api.example.com/api
AUTH='Authorization: tma <initData>'

# 1. Найти предмет
curl "$API/market?kind=primary&sort=popular"

# 2. Создать счёт (цена берётся из БД)
curl -X POST "$API/checkout/invoice" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"item_id": 11}'

# 3. Открыть invoice_url в Telegram — оплата подтверждается webhook'ом

# 4. Дождаться статуса
curl "$API/orders/42" -H "$AUTH"
```

Пока заказ `pending_payment`, владение не меняется. Только после `successful_payment`
и серверной сверки суммы заказ становится `fulfilled`, а предмет появляется в
`/me/collection` с серийным номером.

### 2. Перепродажа

```bash
# выставить
curl -X POST "$API/listings" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"ownership_id": 60, "price_stars": 1200}'
# -> 201 {"listing": {...}, "commission_percent": 10, "seller_receives_stars": 1080}

# покупатель (другой initData) создаёт счёт
curl -X POST "$API/checkout/invoice" -H "$BUYER_AUTH" -H 'Content-Type: application/json' \
  -d '{"listing_id": 8}'
# -> 409, если лот уже зарезервирован/продан, свой собственный лот или предмет заблокирован
```

Лот резервируется на 20 минут (`reserved_until`). Неоплаченный заказ истекает, резерв
снимается фоновым воркером. После оплаты: комиссия платформы + начисление продавцу в
`pending`, через 72 ч — в `available`.

### 3. Выплата продавцу

```bash
curl -X POST "$API/me/payouts" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"amount_stars": 500, "method": "stars_manual", "destination": "@username"}'
```

Средства переходят в `payout`-бакет. Администратор переводит заявку в `approved` и затем
`paid` (или `rejected` — средства возвращаются на `available`). Автоматического вывода
Stars/TON нет — это осознанное ограничение.

### 4. Проверка идемпотентности webhook

```bash
curl -X POST "$API/telegram/webhook" \
  -H 'X-Telegram-Bot-Api-Secret-Token: <WEBHOOK_SECRET>' \
  -H 'Content-Type: application/json' \
  -d '{"update_id": 123, "message": {"successful_payment": {...}}}'
# повтор с тем же update_id -> {"ok": true, "duplicate": true}
```

### 5. Ошибки, которые стоит проверить вручную

| Действие | Ожидание |
|---|---|
| Второй инвойс на тот же лот | 409 |
| Покупка своего лота | 409 |
| Инвойс на неактивный предмет | 409 |
| `dev-pay` в production | 404 |
| Подменённая сумма в `successful_payment` | платёж `failed`, заказ не исполняется |
| Webhook без secret-token | 403 |
| Заблокированный пользователь | 403 |
| Чужой `ownership_id` в `POST /listings` | 409/403 |

---

## Перечисления

**Редкость**: `common`, `uncommon`, `rare`, `epic`, `legendary`

**Статус заказа**: `pending_payment`, `paid`, `fulfilled`, `failed`, `cancelled`,
`expired`, `refund_pending`, `refunded`

**Статус лота**: `active`, `reserved`, `sold`, `cancelled`, `expired`

**Статус платежа**: `pending`, `succeeded`, `failed`, `refunded`

**Тип транзакции**: `sale_credit`, `commission`, `refund_debit`, `settlement`,
`payout_request`, `payout_reversal`, `payout_paid`, `admin_adjustment`

**Бакет журнала**: `pending`, `available`, `platform`, `payout`, `external`

**Тип уведомления**: `purchase`, `sale`, `listing_created`, `listing_cancelled`,
`payment_status`, `seller_credit`, `payout`, `offer`, `system`, `admin`

**Источник предмета**: `internal` (предмет GIFT MARKET в БД), `telegram_official`,
`external_nft` — последние два только как явная маркировка, без имитации выпуска.

**Метод выплаты**: `stars_manual`, `bank_manual`, `ton_manual`

**Статус выплаты**: `requested`, `approved`, `rejected`, `paid`
