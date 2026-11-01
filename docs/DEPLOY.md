# Развёртывание GIFT MARKET

Три сценария:

1. **Локально без Docker** — для разработки (SQLite, `DEV_AUTH`).
2. **Docker Compose на одном сервере** — PostgreSQL + API + nginx с собранным фронтендом.
3. **Продакшен в интернете** — backend на Render (+ управляемый PostgreSQL), frontend на
   Cloudflare Pages.

Telegram требует **HTTPS** для Mini App и webhook — локальный HTTP подходит только для
разработки в браузере.

- [Что понадобится](#что-понадобится)
- [Docker Compose](#docker-compose)
- [Render: backend + PostgreSQL](#render-backend--postgresql)
- [Cloudflare Pages: frontend](#cloudflare-pages-frontend)
- [Переменные окружения](#переменные-окружения)
- [Миграции и данные](#миграции-и-данные)
- [Webhook Telegram](#webhook-telegram)
- [Бэкапы и обновления](#бэкапы-и-обновления)
- [Чек-лист продакшена](#чек-лист-продакшена)
- [Диагностика](#диагностика)

---

## Что понадобится

| Ресурс | Зачем |
|---|---|
| Аккаунт GitHub | репозиторий для Render/Cloudflare |
| Аккаунт Render | backend + PostgreSQL |
| Аккаунт Cloudflare | Cloudflare Pages (можно заменить на nginx/VPS) |
| Бот в Telegram | `BOT_TOKEN`, `BOT_USERNAME` |
| Домен (опционально) | красивый URL и стабильный CORS-origin |

Проверьте локально перед деплоем:

```bash
cd backend && .venv/bin/pytest -q          # 34 passed
cd ../frontend && npm test && npm run build
```

---

## Docker Compose

Файл `docker-compose.yml` поднимает три сервиса:

| Сервис | Образ | Порт | Комментарий |
|---|---|---|---|
| `db` | `postgres:16-alpine` | 5432 | том `pgdata`, healthcheck `pg_isready` |
| `api` | `backend/Dockerfile` | 8000 | `scripts/start.sh`: миграции → seed (если включён) → uvicorn |
| `web` | `frontend/Dockerfile` (nginx 1.27) | 8080 | SPA + прокси `/api` → `http://api:8000` |

### Запуск

```bash
cp backend/.env.example backend/.env
cp .env.example .env
```

В `backend/.env` обязательно:

```env
ENV=production
BOT_TOKEN=123456:AA...
BOT_USERNAME=your_bot
WEBAPP_URL=https://your.domain
PUBLIC_BASE_URL=https://your.domain
WEBHOOK_SECRET=<openssl rand -hex 32>
ADMIN_TELEGRAM_IDS=<ваш telegram id>
DEV_AUTH=false
CORS_ORIGINS=https://your.domain
TRUSTED_HOSTS=your.domain,api.your.domain
```

`DATABASE_URL` в compose переопределяется автоматически на
`postgresql+psycopg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@db:5432/<POSTGRES_DB>`, поэтому
строку в `backend/.env` можно не трогать.

```bash
docker compose up --build -d
docker compose logs -f api          # миграции и старт
curl http://localhost:8000/api/health
```

Откройте `http://localhost:8080` — приложение работает, `/api` проксируется в контейнер
`api`. Без Telegram вход возможен только при `DEV_AUTH=true` (в production он запрещён).

### Остановка / обновление

```bash
docker compose down            # с сохранением тома pgdata
docker compose down -v         # ⚠️ удалить БД
docker compose up --build -d   # пересобрать после git pull
```

Для reverse-proxy с HTTPS (Caddy/Traefik/nginx) направьте домен на `web:8080` и
`api:8000`; можно также проксировать `/api` на уровне хоста и не публиковать 8000 наружу.

---

## Render: backend + PostgreSQL

В репозитории есть `render.yaml` (Blueprint). Шаги:

1. **Push репозитория в GitHub** (ветка `main`).
2. Render → **New → Blueprint** → выберите репозиторий. Render прочитает `render.yaml`.
3. Создастся:
   - PostgreSQL `gift-market-db` (`frankfurt`, `basic-256mb`);
   - web-сервис `gift-market-api` (`runtime: docker`, `rootDir: backend`,
     `dockerfilePath: ./Dockerfile`, healthcheck `/api/health`).
4. Заполните секреты, помеченные `sync: false`:

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | токен от @BotFather |
| `BOT_USERNAME` | username бота без `@` |
| `WEBAPP_URL` | `https://<pages-домен>` (фронтенд) |
| `PUBLIC_BASE_URL` | `https://<render-домен>` (backend) |
| `ADMIN_TELEGRAM_IDS` | ваш Telegram ID (супер-админ) |
| `CORS_ORIGINS` | `https://<pages-домен>` (можно несколько через запятую) |
| `WEBHOOK_SECRET` | Render сгенерирует сам (`generateValue: true`) — не меняйте |
| `TRUSTED_HOSTS` | `<render-домен>` |

`DATABASE_URL` Render подставит из базы (`fromDatabase.connectionString`), приложение
нормализует `postgres://` → `postgresql+psycopg://` автоматически.

5. Дождитесь деплоя (Docker build ≈ 2–4 мин) и проверьте:

```bash
curl https://gift-market-api.onrender.com/api/health
curl https://gift-market-api.onrender.com/api/health/ready
curl https://gift-market-api.onrender.com/api/meta
```

6. Миграции применяются автоматически при старте (`scripts/start.sh` → `alembic upgrade head`).
   Демо-каталог в продакшене **не** заливается; при необходимости:
   `SEED_DEMO_DATA=true` в Render Environment → Manual Deploy → после сидинга выключите.

> `plan: starter` выбран, потому что сборка Docker и постоянный процесс не укладываются в
> free-план Render; при желании замените в `render.yaml` или в UI. Free-план «засыпает» и
> первый запрос идёт секунды — для webhook это плохо, поэтому для продакшена берите платный.

### Если создаёте сервис вручную (без Blueprint)

- **Environment**: Docker, root directory `backend`, Dockerfile `./Dockerfile`.
- **Health check path**: `/api/health`.
- **Disk**: не требуется (данные в PostgreSQL).
- Добавьте переменные из таблицы выше + `ENV=production`, `LOG_LEVEL=INFO`,
  `WEB_CONCURRENCY=2`.
- В `DATABASE_URL` вставьте **Internal Database URL** (не External).

---

## Cloudflare Pages: frontend

1. Cloudflare Dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Репозиторий `Gifts`, ветка `main`.
3. Настройки сборки:

| Параметр | Значение |
|---|---|
| Framework preset | None / Vite |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `frontend` |
| Environment variable | `NODE_VERSION=20` |

4. Переменные окружения (Production **и** Preview):

```env
VITE_API_URL=https://gift-market-api.onrender.com/api
VITE_DEMO_MODE=false
```

`VITE_API_URL` встраивается в сборку, поэтому после его изменения нужен новый deploy.

5. SPA-фолбэк и заголовки уже лежат в `frontend/public/`:
   - `_redirects`: `/* /index.html 200`;
   - `_headers`: `nosniff`, `Referrer-Policy`, кэш ассетов и картинок.

6. Привяжите домен (`Pages → Custom domains`) и обновите `WEBAPP_URL`/`CORS_ORIGINS` на
   backend.

> **Почему не относительный `/api`?** На Cloudflare Pages нет прокси до backend, поэтому
> сборка должна знать абсолютный адрес API. Запросы идут cross-origin, и backend разрешает
> их через `CORS_ORIGINS`. Заголовки `Authorization` и `X-Dev-Telegram-Id` добавлены в
> `allow_headers`.

### Альтернатива: nginx-образ

```bash
cd frontend
docker build -t gift-market-web \
  --build-arg VITE_API_URL=https://api.example.com/api .
docker run -p 8080:80 gift-market-web
```

`nginx.conf` отдаёт SPA, кэширует `/assets` и проксирует `/api` на `http://api:8000`
(имя сервиса в compose). Для другого адреса API используйте `VITE_API_URL` при сборке.

---

## Переменные окружения

### Backend

| Переменная | Обязательна в проде | Значение по умолчанию | Описание |
|---|---|---|---|
| `ENV` | да | `development` | `production` включает строгие проверки |
| `LOG_LEVEL` | нет | `INFO` | уровень логов |
| `API_PREFIX` | нет | `/api` | префикс API |
| `DATABASE_URL` | да | `sqlite:///./gift_market.db` | в проде только PostgreSQL |
| `BOT_TOKEN` | да | — | токен бота |
| `BOT_USERNAME` | да | — | для ссылок в UI |
| `WEBAPP_URL` | да | — | публичный URL фронтенда |
| `PUBLIC_BASE_URL` | да | — | публичный URL backend (для webhook) |
| `WEBHOOK_SECRET` | да | — | сверяется с `secret_token` webhook |
| `INIT_DATA_MAX_AGE_SECONDS` | нет | `86400` | срок жизни initData |
| `ADMIN_TELEGRAM_IDS` | да | — | ID через запятую; авто-выдача superadmin |
| `DEV_AUTH` | да (false) | `false` | локальный вход без Telegram |
| `DEMO_TELEGRAM_ID` | нет | `900000001` | демо-пользователь |
| `CORS_ORIGINS` | да | localhost | явный список origin |
| `TRUSTED_HOSTS` | да | `*` | домены backend |
| `COMMISSION_PERCENT` | нет | `10` | начальное значение (дальше — админка) |
| `MIN_LISTING_PRICE` / `MAX_LISTING_PRICE` | нет | `10` / `100000` | границы лота |
| `BALANCE_HOLD_HOURS` | нет | `72` | удержание начислений |
| `LISTING_RESERVATION_MINUTES` | нет | `20` | резерв лота под оплату |
| `CLEANUP_INTERVAL_SECONDS` | нет | `60` | период фоновых задач |
| `RATE_LIMIT_READ/WRITE/CHECKOUT/AUTH` | нет | `300/60`, `60/60`, `15/60`, `60/60` | лимиты |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | нет | `10` / `20` | пул соединений |
| `TONAPI_BASE_URL` / `TONAPI_KEY` | нет | `https://tonapi.io` / — | проверка TON-адреса |
| `WEB_CONCURRENCY` | нет | `2` | воркеры uvicorn |
| `SEED_DEMO_DATA` | нет | `false` | демо-каталог при старте контейнера |

### Frontend (build-time)

| Переменная | Значение |
|---|---|
| `VITE_API_URL` | `/api` (локально) или `https://api.example.com/api` |
| `VITE_DEMO_MODE` | `false` в проде |
| `VITE_SUPPORT_URL` | ссылка на поддержку (необязательно) |

### Compose (корневой `.env`)

| Переменная | Значение |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | учётные данные БД |
| `POSTGRES_PORT` | порт на хосте (5432) |
| `ENV` | `production` |
| `WEB_CONCURRENCY` | число воркеров API |
| `SEED_DEMO_DATA` | `true` только для демо-стенда |

---

## Миграции и данные

```bash
# локально
cd backend && source .venv/bin/activate
alembic upgrade head
alembic current
alembic history --verbose

# в контейнере
docker compose exec api alembic upgrade head
docker compose exec api alembic current

# новая миграция после изменения моделей
alembic revision --autogenerate -m "add something"
```

Правила:

- миграции запускаются автоматически при старте контейнера;
- откат (`alembic downgrade`) выполняется осознанно и вручную — сначала бэкап;
- первая миграция `d50396de1f46_initial_schema.py` создаёт все 25 таблиц и партиальный
  уникальный индекс `uq_listing_active_ownership`;
- SQLite используется только локально и в тестах; приложение не стартует в `production`
  с не-PostgreSQL `DATABASE_URL`.

### Первый администратор

`ADMIN_TELEGRAM_IDS=<id>` достаточно: при первом запросе с валидным initData пользователь
получает роль `superadmin` и запись в `admin_users`. Проверить:

```bash
curl -s https://api.example.com/api/me -H "Authorization: tma <initData>" | jq '.is_admin, .admin_role'
```

---

## Webhook Telegram

1. Убедитесь, что `PUBLIC_BASE_URL` — публичный HTTPS и `WEBHOOK_SECRET` задан.
2. Откройте админку → **Настройки → Telegram → «Установить webhook»**
   (вызывает `POST /api/admin/telegram/setup-webhook`), либо вручную:

```bash
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://api.example.com/api/telegram/webhook",
    "secret_token": "'"$WEBHOOK_SECRET"'",
    "allowed_updates": ["message", "pre_checkout_query", "callback_query"],
    "drop_pending_updates": false
  }'

curl "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
```

3. Проверка со стороны backend:

```bash
curl https://api.example.com/api/telegram/webhook      # {"ok": true, "configured": true}
curl https://api.example.com/api/admin/telegram/status -H "Authorization: tma <admin initData>"
```

Типичные проблемы:

| Симптом | Причина |
|---|---|
| webhook отвечает 403 | `secret_token` не совпадает с `WEBHOOK_SECRET` |
| `last_error_message: SSL error` | нет валидного HTTPS-сертификата |
| `last_error_message: 502/503` | сервис спит (free-план) или падает при старте |
| платежи не доходят | `allowed_updates` без `pre_checkout_query`/`message` |
| мини-приложение не открывается | `WEBAPP_URL` не HTTPS или домен не разрешён Telegram |

---

## Бэкапы и обновления

```bash
# бэкап PostgreSQL из compose
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > backup-$(date +%F-%H%M).sql.gz

# восстановление
gunzip -c backup-2026-11-01-1200.sql.gz \
  | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

- Render: включите автоматические бэкапы базы в настройках плана; перед крупными
  миграциями делайте ручной снапшот.
- Обновление кода: `git pull` → `docker compose up --build -d` (compose) или push в
  `main` (Render/Cloudflare авто-деплой).
- Порядок безопасного релиза: миграция обратно совместима → деплой API → деплой фронта.

---

## Чек-лист продакшена

- [ ] `ENV=production`, `DEV_AUTH=false`
- [ ] PostgreSQL (не SQLite), бэкапы включены
- [ ] `BOT_TOKEN`, `BOT_USERNAME`, `WEBAPP_URL`, `PUBLIC_BASE_URL` заданы
- [ ] `WEBHOOK_SECRET` — случайные 32+ символа, совпадает с `setWebhook`
- [ ] `ADMIN_TELEGRAM_IDS` содержит ваш ID, админка открывается
- [ ] `CORS_ORIGINS` — точный домен фронтенда (без `*`)
- [ ] `TRUSTED_HOSTS` — домен backend
- [ ] `/api/health` и `/api/health/ready` отвечают 200
- [ ] `getWebhookInfo` без `last_error_message`
- [ ] тестовая покупка за Stars: заказ `fulfilled`, предмет в коллекции, комиссия и
      начисление продавцу корректны
- [ ] уведомления приходят в Telegram
- [ ] `payout_note` и текст о ручных выплатах видны в профиле
- [ ] rate limit проверен (быстрый спам запросов → 429)
- [ ] логи собираются (Render Logs / `docker compose logs`) и в них есть `error`-события
- [ ] HTTPS на обоих доменах, HSTS на прокси
- [ ] определён процесс выплат продавцам (вне кода)

---

## Диагностика

| Симптом | Что проверить |
|---|---|
| `Invalid production configuration: BOT_TOKEN is required` | переменная не попала в контейнер (env_file/секреты) |
| `Invalid production configuration: DATABASE_URL must point to PostgreSQL` | `DATABASE_URL` всё ещё SQLite |
| 500 на `/api/home` | миграции не применены: `alembic upgrade head`, `alembic current` |
| 401 на всех запросах | initData не передаётся или `BOT_TOKEN` другой (подпись не сходится) |
| 403 на админке | нет роли/`is_admin`; проверьте `admin_users` и `ADMIN_TELEGRAM_IDS` |
| 409 при создании счёта | лот уже зарезервирован/продан или свой собственный |
| `invoice_url` пустой | запуск без `BOT_TOKEN` — это dev-режим (`dev_simulated: true`) |
| CORS-ошибка в браузере | `CORS_ORIGINS` не содержит точный origin фронтенда |
| статика 404 после обновления | кэш `index.html`; проверьте `_headers`/сброс CDN |
| Telegram API 502 | заблокирован исходящий доступ или неверный токен |
| пустой каталог | нет данных: `python seed.py` (или админка → создать коллекцию) |
