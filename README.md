# xam_backend

Бэкенд мессенджера (MVP): регистрация, личные диалоги, обмен текстовыми сообщениями и изображениями в реальном времени и статус присутствия (online/offline).

## Стек

- Python 3.11+ (проверено на 3.14)
- FastAPI
- PostgreSQL 15+ (проверено на 18)
- SQLAlchemy 2.0 (async) + Alembic
- WebSocket (нативный FastAPI)
- JWT (Access Token)
- bcrypt (хеширование паролей)
- Присутствие хранится в памяти процесса ConnectionManager (Redis для MVP не требуется)

## Архитектура

Монолит с разделением слоёв: Роутеры → Сервисы → Репозитории/Модели.

```
app/
  api/deps.py            # JWT-аутентификация, зависимости
  api/v1/                # auth, users, chats, realtime (WebSocket)
  core/                  # конфигурация, безопасность, обработчики ошибок
  db/                    # Base, async-движок, фабрика сессий
  models/                # users, chats, messages
  schemas/               # Pydantic-схемы запросов/ответов
  repositories/          # SQL-запросы
  services/              # бизнес-логика
  realtime/              # ConnectionManager и события WebSocket
alembic/                 # миграции
tests/                   # pytest: REST + WebSocket (TestClient и реальный uvicorn)
```

## API (v1)

### Аутентификация

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Регистрация: `username` (3–32, `[A-Za-z0-9_]`), `password` (мин. 8), `display_name`. Возвращает `201` и JWT |
| POST | `/api/v1/auth/login` | Вход по `username`/`password`, возвращает `access_token` и `token_type` |

Ответ обоих эндпоинтов:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "uuid", "username": "alice", "display_name": "Alice", "avatar_url": null, "created_at": "...", "last_seen": null }
}
```

### Пользователи

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/api/v1/users/me` | Профиль текущего пользователя |
| GET | `/api/v1/users/search?q=&limit=` | Поиск пользователей по username (без самого себя) |

### Диалоги

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/chats` | Создать или получить личный диалог: `{ "participant_id": "uuid" }` |
| GET | `/api/v1/chats` | Список чатов с последним сообщением и unread-счётчиком, сортировка по времени активности |

В БД диалог хранится с `user1_id < user2_id` и ограничением `UNIQUE(user1_id, user2_id)`, поэтому повторный вызов для той же пары (в любом порядке) возвращает существующий чат.

### Сообщения

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/chats/{chat_id}/messages` | Отправка: `{ "content": "...", "client_message_id": "uuid" }`. `client_message_id` опционален и обеспечивает идемпотентность |
| POST | `/api/v1/chats/{chat_id}/images` | Отправка изображения: `multipart/form-data` с полем `file`, опциональными `caption` (до 4000 символов) и `client_message_id` |
| GET | `/api/v1/chats/{chat_id}/messages?limit=50&before=` | История, cursor-based пагинация по `created_at` (новые сначала); `next_cursor` в ответе |
| POST | `/api/v1/chats/{chat_id}/read` | Пометить входящие сообщения чата прочитанными |

После сохранения сообщения (текстового или изображения) событие `new_message` рассылается всем активным сессиям обоих участников.

Изображения принимаются в форматах JPEG, PNG, GIF и WEBP; тип определяется по содержимому файла, а не по заголовку `Content-Type`. Максимальный размер задаётся `MAX_IMAGE_SIZE_BYTES` (по умолчанию 5 МиБ). Файлы сохраняются в `UPLOAD_DIR` и отдаются по URL `/media/images/<uuid>.<ext>`. Имена файлов — случайные UUID, поэтому URL работает как непубликуемая ссылка; SVG и другие форматы отклоняются. Неподдерживаемый формат возвращает `415`, превышение размера — `413`, пустой файл — `400`.

Поле `message_type` в объекте сообщения принимает значения `text` или `image`; для изображения заполнены `image_url`, `image_mime_type`, `image_size_bytes`, а `content` содержит подпись (пустую строку, если подписи нет).

### WebSocket

`ws://<host>/ws?token=<jwt>`

Сервер → клиент:

```json
{ "type": "new_message", "data": { "id": "uuid", "chat_id": "uuid", "sender_id": "uuid", "content": "...", "message_type": "text", "image_url": null, "image_mime_type": null, "image_size_bytes": null, "client_message_id": null, "created_at": "...", "is_read": false } }
{ "type": "user_status", "data": { "user_id": "uuid", "status": "online" } }
{ "type": "typing", "data": { "chat_id": "uuid", "user_id": "uuid", "is_typing": true } }
{ "type": "pong" }
{ "type": "error", "data": { "detail": "..." } }
```

Клиент → сервер: `ping` (текстом или `{"type": "ping"}`), `{"type": "typing", "data": {"chat_id": "uuid", "is_typing": true}}`.

Статус `online` рассылается партнёрам по чатам при первом подключении пользователя, `offline` — при закрытии последней сессии (одновременно обновляется `users.last_seen`). Невалидный токен закрывает соединение с кодом `1008`.

## Схема БД

- `users`: `id` UUID PK, `username` VARCHAR(32) UNIQUE, `password_hash` VARCHAR(255), `display_name` VARCHAR(64), `avatar_url` TEXT, `created_at` TIMESTAMPTZ, `last_seen` TIMESTAMPTZ
- `chats`: `id` UUID PK, `user1_id` UUID FK, `user2_id` UUID FK, `created_at` TIMESTAMPTZ, `CHECK (user1_id < user2_id)`, `UNIQUE(user1_id, user2_id)`
- `messages`: `id` UUID PK, `chat_id` UUID FK (INDEX), `sender_id` UUID FK, `content` TEXT, `client_message_id` UUID, `created_at` TIMESTAMPTZ (INDEX), `is_read` BOOLEAN, `message_type` VARCHAR(16) (`text`/`image`), `image_url` TEXT, `image_mime_type` VARCHAR(64), `image_size_bytes` INTEGER
- Индекс `idx_messages_chat_created` на `(chat_id, created_at DESC)`
- Дедупликация: `UNIQUE(chat_id, sender_id, client_message_id)`
- Ограничения: `message_type IN ('text', 'image')`, для `image` обязателен `image_url`

## Запуск (dev)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn main:app --reload
```

По умолчанию используется `postgresql+asyncpg://postgres:postgres@localhost:5432/xam` — создайте БД и при необходимости измените `DATABASE_URL` в `.env`.

Для локального запуска без миграций можно выставить `AUTO_CREATE_TABLES=true` — приложение создаст таблицы из метаданных при старте.

Swagger UI: http://localhost:8000/docs, проверка живости: http://localhost:8000/health.

## Запуск в Docker

`Dockerfile` собирает образ на `python:3.12-slim` и запускает `uvicorn` от непривилегированного пользователя. `docker-entrypoint.sh` перед стартом применяет миграции (`alembic upgrade head`); отключить это можно переменной `RUN_MIGRATIONS=false`.

`docker-compose.yml` поднимает приложение вместе с PostgreSQL 16:

```bash
copy .env.example .env   # при необходимости задайте SECRET_KEY и CORS_ORIGINS
docker compose up --build
```

- API: http://localhost:8000, Swagger UI: http://localhost:8000/docs
- PostgreSQL доступен только внутри сети compose (сервис `db`, база `xam`); данные хранятся в volume `postgres_data`
- Загруженные изображения хранятся в volume `uploads_data` (в контейнере — `/app/uploads`)
- Переменные `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `API_PORT` можно переопределить в `.env`
- `DATABASE_URL` для контейнера собирается автоматически и указывает на `db:5432`, значение из локального `.env` игнорируется
- Остановить: `docker compose down`, удалить данные БД: `docker compose down -v`

Собрать и запустить только приложение (без compose), если PostgreSQL уже доступен:

```bash
docker build -t xam_backend .
docker run --rm -p 8000:8000 --env-file .env -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/xam xam_backend
```

### Переменные окружения

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `SECRET_KEY` | Ключ подписи JWT (обязательно сменить в prod) | dev-ключ для локального запуска |
| `JWT_ALGORITHM` | Алгоритм JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Время жизни access-токена | `1440` |
| `DATABASE_URL` | DSN SQLAlchemy async | PostgreSQL localhost/xam |
| `DATABASE_ECHO` | Логировать SQL | `false` |
| `AUTO_CREATE_TABLES` | Создавать таблицы при старте | `false` |
| `UPLOAD_DIR` | Каталог хранения изображений | `uploads` |
| `MEDIA_URL_PREFIX` | URL-префикс раздачи изображений | `/media` |
| `MAX_IMAGE_SIZE_BYTES` | Максимальный размер изображения, байт | `5242880` (5 МиБ) |
| `CORS_ORIGINS` | Разрешённые origin через запятую | `http://localhost:5173` |

## Тесты и линт

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
```

Тесты используют SQLite и не требуют запущенного PostgreSQL; сценарии presence/typing дополнительно проверяются через реальный uvicorn-сервер.

## Требования

- Все эндпоинты, кроме `register`/`login`, защищены JWT; WebSocket требует валидный токен
- Валидация через Pydantic-схемы
- CORS настраивается через `CORS_ORIGINS`
- Единый формат ошибок: `{ "detail": "..." }` с корректными HTTP-статусами
