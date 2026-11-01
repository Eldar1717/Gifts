# Telegram: бот, Mini App и платежи Stars

Пошаговая инструкция для владельца проекта: что сделать в Telegram, какие значения
прописать в окружении и как проверить, что оплата работает. Все шаги выполняются вами —
код к ним уже готов.

- [1. Создать бота](#1-создать-бота)
- [2. Создать Mini App](#2-создать-mini-app)
- [3. Прописать окружение](#3-прописать-окружение)
- [4. Проверить авторизацию](#4-проверить-авторизацию)
- [5. Платежи Stars](#5-платежи-stars)
- [6. Webhook](#6-webhook)
- [7. Проверка покупки](#7-проверка-покупки)
- [8. Возвраты](#8-возвраты)
- [9. Оформление и правила](#9-оформление-и-правила)
- [10. Частые вопросы](#10-частые-вопросы)
- [Что делает владелец, а что уже в коде](#что-делает-владелец-а-что-уже-в-коде)

---

## 1. Создать бота

1. Откройте [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Задайте имя (например, `GIFT MARKET`) и username, оканчивающийся на `bot`
   (`giftmarket_bot`).
3. Сохраните токен вида `123456789:AAH...` — это `BOT_TOKEN`. **Не коммитьте его.**
4. Полезные команды BotFather:

| Команда | Зачем |
|---|---|
| `/setdescription` | описание бота в профиле |
| `/setabouttext` | короткий текст «о боте» |
| `/setuserpic` | аватар |
| `/setcommands` | список команд (`start` — Открыть магазин) |
| `/mybots → Bot Settings → Payments` | настройки платежей (для Stars не обязательны) |

Бот должен быть **публичным** (не приватным), иначе Mini App и инвойсы не откроются у
других пользователей.

---

## 2. Создать Mini App

Есть два способа; оба ведут к одному URL фронтенда.

### Вариант A. Main Mini App через BotFather

1. `/mybots` → выберите бота → **Bot Settings → Configure Mini App** (или команда `/newapp`).
2. Укажите:
   - **Title**: `GIFT MARKET`;
   - **Description**: короткое описание;
   - **Photo**: 640×360;
   - **Web App URL**: `https://<ваш-фронтенд>` (обязательно HTTPS, без параметров);
   - **Short name**: например `shop`.
3. После этого приложение доступно:
   - по кнопке меню в чате с ботом,
   - по ссылке `https://t.me/<bot_username>/<short_name>`,
   - по deep link `https://t.me/<bot_username>?startapp=<параметр>`.

### Вариант B. Кнопка меню (без Main Mini App)

```bash
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setChatMenuButton" \
  -H 'Content-Type: application/json' \
  -d '{
    "menu_button": {
      "type": "web_app",
      "text": "GIFT MARKET",
      "web_app": { "url": "https://<ваш-фронтенд>" }
    }
  }'
```

Кнопка появится слева от поля ввода во всех чатах с ботом.

### Требования к фронтенду

- **HTTPS** с валидным сертификатом (Cloudflare Pages даёт автоматически).
- **Не блокировать iframe**: не отправляйте `X-Frame-Options: DENY` и
  `Content-Security-Policy: frame-ancestors 'none'`. Telegram Web открывает Mini App внутри
  iframe. Текущий backend таких заголовков не ставит, `frontend/public/_headers` — тоже.
- Мобильная вёрстка и корректный viewport (в проекте уже настроено).
- Приложение должно работать при `initData`, переданном в заголовке `Authorization: tma …`.

---

## 3. Прописать окружение

В `backend/.env` (или в Render Environment):

```env
BOT_TOKEN=123456789:AAH...
BOT_USERNAME=giftmarket_bot
WEBAPP_URL=https://giftmarket.pages.dev
PUBLIC_BASE_URL=https://gift-market-api.onrender.com
WEBHOOK_SECRET=<openssl rand -hex 32>
ADMIN_TELEGRAM_IDS=<ваш telegram numeric id>
DEV_AUTH=false
ENV=production
```

- `WEBAPP_URL` используется в кнопках `web_app` в сообщениях бота и в `/start`.
- `PUBLIC_BASE_URL` — база для webhook: `POST /admin/telegram/setup-webhook` вызывает
  `setWebhook("<PUBLIC_BASE_URL>/api/telegram/webhook", WEBHOOK_SECRET)`.
- `BOT_USERNAME` нужен публичному `/api/meta`, чтобы UI мог показать кнопку «Открыть бота».

Узнать свой Telegram ID: [@userinfobot](https://t.me/userinfobot) или
[@myidbot](https://t.me/myidbot).

> При первом же запросе с валидным `initData` пользователь из `ADMIN_TELEGRAM_IDS`
> автоматически получает роль `superadmin` в `admin_users`.

---

## 4. Проверить авторизацию

1. Откройте Mini App через бота (кнопка меню).
2. `GET /api/me` должен вернуть ваш профиль; в браузере запрос уходит с заголовком
   `Authorization: tma <initData>`.
3. Если 401:
   - `BOT_TOKEN` не тот, что у бота, из которого открыто приложение;
   - `auth_date` старше `INIT_DATA_MAX_AGE_SECONDS`;
   - фронтенд открыт по обычному URL, а не через Telegram (в браузере нужен `DEV_AUTH`).

Сервер проверяет подпись так:

```text
secret_key   = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)
data_check   = "auth_date=<...>\nquery_id=<...>\nuser=<...>"
valid        = HMAC_SHA256(key=secret_key, msg=data_check) == hash
```

Дополнительно проверяются срок жизни и наличие `auth_date`; `hash` не участвует в
`data_check_string`.

---

## 5. Платежи Stars

### Как это устроено в проекте

1. `POST /api/checkout/invoice` (backend) вычисляет сумму по своей БД и вызывает Bot API
   `createInvoiceLink` c:

```json
{
  "title": "Ember Crown",
  "description": "Ночной Пепел · EPIC · GIFT MARKET",
  "payload": "<uuid заказа>",
  "currency": "XTR",
  "prices": [{ "label": "Ember Crown", "amount": 650 }]
}
```

**`provider_token` не передаётся** — для Stars он не нужен (цифровые товары оплачиваются
внутренней валютой Telegram).

2. Фронтенд открывает ссылку через `Telegram.WebApp.openInvoice(url, callback)`.
3. Telegram шлёт боту `pre_checkout_query` → backend проверяет заказ, сумму и валюту и
   отвечает `answerPreCheckoutQuery`. При отказе пользователь видит причину и не платит.
4. После оплаты приходит `message.successful_payment`:

```json
{
  "currency": "XTR",
  "total_amount": 650,
  "invoice_payload": "<uuid>",
  "telegram_payment_charge_id": "...",
  "provider_payment_charge_id": "..."
}
```

5. Backend сверяет payload/сумму/валюту, фиксирует платёж и передаёт предмет в одной
   транзакции. **Только после этого** появляется владение.

### Требования Telegram

- Продажа цифровых товаров в ботах должна идти **в Stars (XTR)**; фиатные платёжные
  провайдеры для таких товаров не используются.
- Приложение обязано соблюдать [условия Telegram для ботов и Mini Apps](https://telegram.org/tos/bot-developers)
  и правила магазина приложений.
- Бот не должен запрашивать у пользователя платёжные данные — всё делает Telegram.

### Тестовый режим

- **Отдельной песочницы для Stars нет.** Реальный тест — покупка самого дешёвого предмета
  (в демо-каталоге это `Blush Ribbon` за 30 ★) и последующий возврат.
- Для локальной разработки есть `POST /api/checkout/dev-pay`: он прогоняет ту же проверку и
  исполнение, что webhook, но работает только при `DEV_AUTH=true` и `ENV≠production`.
- `is_test` в `payments` остаётся `false` для настоящих Stars-платежей (это поле для
  провайдеров с тестовыми токенами).

---

## 6. Webhook

Webhook обязателен: именно он подтверждает оплату и запускает передачу владения.

### Через админку

`/admin` → Настройки → Telegram → **«Установить webhook»**. Кнопка вызывает
`POST /api/admin/telegram/setup-webhook`, который:

1. проверяет `BOT_TOKEN` и `PUBLIC_BASE_URL` (должен быть HTTPS);
2. вызывает `setWebhook("<PUBLIC_BASE_URL>/api/telegram/webhook", token=WEBHOOK_SECRET)`;
3. записывает действие в `audit_logs`;
4. возвращает `getWebhookInfo`.

### Вручную

```bash
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://api.example.com/api/telegram/webhook",
    "secret_token": "'"$WEBHOOK_SECRET"'",
    "allowed_updates": ["message", "pre_checkout_query", "callback_query"],
    "drop_pending_updates": false
  }'
```

```bash
curl "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
# ожидается: url = ..., pending_update_count = 0, last_error_message отсутствует
```

Backend принимает webhook только с заголовком
`X-Telegram-Bot-Api-Secret-Token: <WEBHOOK_SECRET>`, иначе 403. Каждый `update_id`
сохраняется в `webhook_events`, повторная доставка не приводит к двойному начислению.

Проверить состояние:

```bash
curl https://api.example.com/api/telegram/webhook
# {"ok": true, "configured": true}
```

---

## 7. Проверка покупки

1. Откройте Mini App **другим** аккаунтом (не продавцом).
2. Купите первичный предмет → откроется счёт Stars → оплатите.
3. Ожидаемый результат в течение нескольких секунд:
   - `GET /api/orders/{id}` → `status: "fulfilled"`;
   - предмет появился в «Моя коллекция» с серийным номером;
   - в «Истории операций» — покупка;
   - продавцу (для перепродажи) начислено 90 % в `pending`;
   - в `GET /api/admin/overview` вырос оборот и выручка платформы.
4. Проверьте перепродажу: выставите предмет в «Моей коллекции», купите его вторым
   аккаунтом, убедитесь, что комиссия равна 10 % (или текущей настройке).
5. Проверьте защиту: попробуйте купить тот же лот вторым аккаунтом — должен быть 409.

Если заказ остался `pending_payment`, а Stars списались — смотрите `webhook_events` и
логи backend: скорее всего webhook не доставлен (см. `getWebhookInfo.last_error_message`).

---

## 8. Возвраты

- Покупатель запрашивает возврат: `POST /api/orders/{id}/refund` (создаётся `refunds` со
  статусом `requested`).
- Администратор подтверждает: `POST /api/admin/orders/{id}/refund?reason=...`.
- Backend вызывает `refundStarPayment(user_id, telegram_payment_charge_id)` и фиксирует
  обратные проводки журнала.

Ограничения:

- возврат возможен только для Stars-платежей (`XTR`) и только при наличии
  `telegram_payment_charge_id`;
- если предмет уже перепродан, возврат требует ручного урегулирования (сделка помечается,
  администратор решает вручную);
- Telegram может отклонить возврат — статус `refunds.status = failed`, ошибка сохраняется
  в `error`, действие отражается в аудите.

---

## 9. Оформление и правила

- **Название и описание** бота и Mini App не должны имитировать официальные продукты
  Telegram. В приложении уже есть дисклеймер: предметы — внутренние, не NFT и не
  официальные Telegram Collectible Gifts.
- **Политика конфиденциальности**: разместите её на своём домене и укажите ссылку в
  описании бота; приложение хранит Telegram ID, username, аватар и историю операций.
- **Условия использования** и правила возвратов стоит продублировать в боте
  (`/setdescription`) и в разделе «О приложении» (`terms_url` в настройках платформы).
- **Поддержка**: укажите контакт (`@username`) — пользователю нужен канал связи по
  платежам и выплатам.
- **Выплаты продавцам**: юридически это ваша ответственность (налоги, KYC, договор с
  провайдером). Приложение только фиксирует заявки и решения; автоматического вывода
  Stars/TON нет.
- **TON/NFT**: если позже добавите реальные on-chain предметы, не называйте внутренние
  предметы NFT и не показывайте фейковые ссылки на блокчейн.

---

## 10. Частые вопросы

**Можно ли открыть Mini App по прямой ссылке в браузере?**
Да, но без Telegram-авторизации: в продакшене вы увидите экран «Откройте через бота».
Для локальной разработки используйте `DEV_AUTH=true`.

**Почему `invoice_url` пустой?**
Backend запущен без `BOT_TOKEN` (dev-режим). Ответ содержит `dev_simulated: true`, оплата
эмулируется `POST /api/checkout/dev-pay`.

**Почему Telegram не присылает `successful_payment`?**
Проверьте `getWebhookInfo`: неверный URL, нет HTTPS, сервис недоступен, неверный
`secret_token`, либо webhook не был установлен после смены домена.

**Можно ли использовать long polling вместо webhook?**
Проект рассчитан на webhook (он же защищает от повторов через `update_id`). Polling не
реализован.

**Что будет, если два пользователя одновременно оплатят один лот?**
Первый заказ исполнится; второй получит `refund_pending` и возврат — лот уже `sold`,
владение проверяется под блокировкой.

**Можно ли продавать фиатные товары/подписки?**
Это вопрос правил Telegram и вашей юрисдикции; технически модель рассчитана на Stars и
цифровые коллекционные предметы.

---

## Что делает владелец, а что уже в коде

| Шаг | Кто |
|---|---|
| Создать бота, получить токен | владелец (BotFather) |
| Создать Mini App, указать URL | владелец (BotFather) |
| Задеплоить backend/frontend, HTTPS | владелец (Render/Cloudflare) |
| Заполнить env (`BOT_TOKEN`, `WEBAPP_URL`, `PUBLIC_BASE_URL`, `WEBHOOK_SECRET`, `ADMIN_TELEGRAM_IDS`) | владелец |
| Установить webhook | владелец (кнопка в админке) |
| Проверить покупку за Stars | владелец |
| Юридические документы, политика, поддержка | владелец |
| Организация выплат продавцам | владелец (вне кода) |
| Проверка `initData` (HMAC + срок) | код |
| Создание счёта, проверка суммы и валюты | код |
| `pre_checkout_query` / `successful_payment` | код |
| Идемпотентность, защита от повторов и двойной продажи | код |
| Передача владения, журнал, уведомления | код |
| Комиссия, баланс продавца, удержание | код + админка |
| Возвраты Stars | код (при поддержке Telegram) |
