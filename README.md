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
  api/v1/                # auth, users, chats, groups, channels, realtime (WebSocket)
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

### Группы

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/groups` | Создать группу: `{ "title": "...", "description": "...", "member_ids": ["uuid"] }`. Создатель становится `owner`, возвращается `201` |
| GET | `/api/v1/groups` | Список групп пользователя с последним сообщением и `unread_count` |
| GET | `/api/v1/groups/{group_id}` | Группа с участниками (`members`) и ролями |
| PATCH | `/api/v1/groups/{group_id}` | Изменить `title`, `description`, `avatar_url` (owner/admin) |
| DELETE | `/api/v1/groups/{group_id}` | Удалить группу (только owner) |
| GET | `/api/v1/groups/{group_id}/members` | Участники группы |
| POST | `/api/v1/groups/{group_id}/members` | Добавить участников: `{ "user_ids": ["uuid"], "role": "member"\|"admin" }`. Роль `admin` может выдавать только owner |
| PATCH | `/api/v1/groups/{group_id}/members/{user_id}` | Изменить роль участника на `admin`/`member` (только owner) |
| DELETE | `/api/v1/groups/{group_id}/members/{user_id}` | Удалить участника (owner/admin) или выйти самому |
| POST | `/api/v1/groups/{group_id}/leave` | Выйти из группы; owner должен удалить группу |
| POST | `/api/v1/groups/{group_id}/messages` | Отправить сообщение в группу (участники) |
| GET | `/api/v1/groups/{group_id}/messages` | История сообщений группы |
| POST | `/api/v1/groups/{group_id}/images` | Отправить изображение в группу |
| POST | `/api/v1/groups/{group_id}/audio` | Отправить аудиосообщение в группу |
| POST | `/api/v1/groups/{group_id}/video-notes` | Отправить видеокружок в группу |
| POST | `/api/v1/groups/{group_id}/read` | Отметить сообщения группы прочитанными |

### Каналы

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/channels` | Создать канал: `{ "title": "...", "description": "...", "is_public": true, "member_ids": ["uuid"] }`. Создатель становится `owner` |
| GET | `/api/v1/channels` | Список каналов, на которые подписан пользователь |
| GET | `/api/v1/channels/{channel_id}` | Канал с участниками; публичный канал доступен без подписки |
| PATCH | `/api/v1/channels/{channel_id}` | Изменить `title`, `description`, `avatar_url`, `is_public` (owner/admin) |
| DELETE | `/api/v1/channels/{channel_id}` | Удалить канал (только owner) |
| POST | `/api/v1/channels/{channel_id}/subscribe` | Подписаться на публичный канал (идемпотентно) |
| POST | `/api/v1/channels/{channel_id}/unsubscribe` | Отписаться; owner не может отписаться |
| GET | `/api/v1/channels/{channel_id}/members` | Подписчики канала |
| POST | `/api/v1/channels/{channel_id}/members` | Добавить подписчиков/админов (owner/admin) |
| PATCH | `/api/v1/channels/{channel_id}/members/{user_id}` | Изменить роль на `admin`/`member` (только owner) |
| DELETE | `/api/v1/channels/{channel_id}/members/{user_id}` | Удалить подписчика (owner/admin) |
| POST | `/api/v1/channels/{channel_id}/messages` | Опубликовать сообщение (только owner/admin) |
| GET | `/api/v1/channels/{channel_id}/messages` | История канала (подписчики) |
| POST | `/api/v1/channels/{channel_id}/images` | Опубликовать изображение (только owner/admin) |
| POST | `/api/v1/channels/{channel_id}/audio` | Опубликовать аудиосообщение (только owner/admin) |
| POST | `/api/v1/channels/{channel_id}/video-notes` | Опубликовать видеокружок (только owner/admin) |
| POST | `/api/v1/channels/{channel_id}/read` | Отметить сообщения канала прочитанными |

Группы и каналы используют общую таблицу `chats` (`chat_type = "group"|"channel"`), поэтому отправка и история также доступны через общие маршруты `/api/v1/chats/{chat_id}/messages|images|audio|video-notes|read`. У групп писать может любой участник, у каналов — только `owner`/`admin`. События `new_message` рассылаются всем участникам группы/канала.

### Сообщения

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/chats/{chat_id}/messages` | Отправка: `{ "content": "...", "client_message_id": "uuid" }`. `client_message_id` опционален и обеспечивает идемпотентность |
| POST | `/api/v1/chats/{chat_id}/images` | Отправка изображения: `multipart/form-data` с полем `file`, опциональными `caption` (до 4000 символов) и `client_message_id` |
| POST | `/api/v1/chats/{chat_id}/audio` | Отправка аудиосообщения: `multipart/form-data` с полем `file`, опциональными `duration_seconds` (1–3600) и `client_message_id` |
| POST | `/api/v1/chats/{chat_id}/video-notes` | Отправка видеокружка: `multipart/form-data` с полем `file`, опциональными `duration_seconds` (1–3600) и `client_message_id` |
| GET | `/api/v1/chats/{chat_id}/messages?limit=50&before=` | История, cursor-based пагинация по `created_at` (новые сначала); `next_cursor` в ответе |
| POST | `/api/v1/chats/{chat_id}/read` | Пометить входящие сообщения чата прочитанными |

После сохранения сообщения (текстового, изображения, аудио или видеокружка) событие `new_message` рассылается всем активным сессиям участников: обоим собеседникам в личном диалоге или всем участникам группы/канала.

Изображения принимаются в форматах JPEG, PNG, GIF и WEBP; тип определяется по содержимому файла, а не по заголовку `Content-Type`. Максимальный размер задаётся `MAX_IMAGE_SIZE_BYTES` (по умолчанию 5 МиБ). Файлы сохраняются в `UPLOAD_DIR` и отдаются по URL `/media/images/<uuid>.<ext>`. Имена файлов — случайные UUID, поэтому URL работает как непубликуемая ссылка; SVG и другие форматы отклоняются. Неподдерживаемый формат возвращает `415`, превышение размера — `413`, пустой файл — `400`.

Аудиосообщения принимаются в форматах OGG, MP3, WAV, M4A и WEBM (лимит `MAX_AUDIO_SIZE_BYTES`, по умолчанию 25 МиБ), видеокружки — в MP4 и WEBM (лимит `MAX_VIDEO_NOTE_SIZE_BYTES`, по умолчанию 25 МиБ). Формат также определяется по содержимому файла. Файлы сохраняются в `UPLOAD_DIR` и отдаются по URL `/media/audio/<uuid>.<ext>` и `/media/video_notes/<uuid>.<ext>`.

Поле `message_type` в объекте сообщения принимает значения `text`, `image`, `audio` или `video_note`; для изображения заполнены `image_url`, `image_mime_type`, `image_size_bytes`, для аудио и видеокружка — `media_url`, `media_mime_type`, `media_size_bytes`, `media_duration_seconds`, а `content` содержит подпись изображения или пустую строку.

### WebSocket

`ws://<host>/ws?token=<jwt>`

Сервер → клиент:

```json
{ "type": "new_message", "data": { "id": "uuid", "chat_id": "uuid", "sender_id": "uuid", "content": "...", "message_type": "text", "image_url": null, "image_mime_type": null, "image_size_bytes": null, "media_url": null, "media_mime_type": null, "media_size_bytes": null, "media_duration_seconds": null, "client_message_id": null, "created_at": "...", "is_read": false } }
{ "type": "user_status", "data": { "user_id": "uuid", "status": "online" } }
{ "type": "typing", "data": { "chat_id": "uuid", "user_id": "uuid", "is_typing": true } }
{ "type": "pong" }
{ "type": "error", "data": { "detail": "..." } }
```

Клиент → сервер: `ping` (текстом или `{"type": "ping"}`), `{"type": "typing", "data": {"chat_id": "uuid", "is_typing": true}}`.

Статус `online` рассылается партнёрам по чатам при первом подключении пользователя, `offline` — при закрытии последней сессии (одновременно обновляется `users.last_seen`). Невалидный токен закрывает соединение с кодом `1008`.

## Схема БД

- `users`: `id` UUID PK, `username` VARCHAR(32) UNIQUE, `password_hash` VARCHAR(255), `display_name` VARCHAR(64), `avatar_url` TEXT, `created_at` TIMESTAMPTZ, `last_seen` TIMESTAMPTZ
- `chats`: `id` UUID PK, `chat_type` VARCHAR(16) (`direct`/`group`/`channel`), `user1_id` UUID FK NULL, `user2_id` UUID FK NULL, `owner_id` UUID FK NULL, `title` VARCHAR(128) NULL, `description` TEXT NULL, `avatar_url` TEXT NULL, `is_public` BOOLEAN, `created_at` TIMESTAMPTZ. Для `direct` заполнены `user1_id < user2_id` и `owner_id IS NULL`; для группы/канала — `owner_id` и `title`, а `user1_id`/`user2_id` пусты. Ограничения: `CHECK (user1_id < user2_id)`, `UNIQUE(user1_id, user2_id)`, `CHECK (chat_type IN ('direct','group','channel'))`
- `chat_members`: `chat_id` UUID FK + `user_id` UUID FK (составной PK), `role` VARCHAR(16) (`owner`/`admin`/`member`), `joined_at` TIMESTAMPTZ, `last_read_at` TIMESTAMPTZ NULL. Используется для групп и каналов; `last_read_at` хранит позицию прочтения для расчёта непрочитанных
- `messages`: `id` UUID PK, `chat_id` UUID FK (INDEX), `sender_id` UUID FK, `content` TEXT, `client_message_id` UUID, `created_at` TIMESTAMPTZ (INDEX), `is_read` BOOLEAN, `message_type` VARCHAR(16) (`text`/`image`/`audio`/`video_note`), `image_url` TEXT, `image_mime_type` VARCHAR(64), `image_size_bytes` INTEGER, `media_url` TEXT, `media_mime_type` VARCHAR(64), `media_size_bytes` INTEGER, `media_duration_seconds` INTEGER
- Индекс `idx_messages_chat_created` на `(chat_id, created_at DESC)`
- Дедупликация: `UNIQUE(chat_id, sender_id, client_message_id)`
- Ограничения: `message_type IN ('text', 'image', 'audio', 'video_note')`, для `image` обязателен `image_url`, для `audio`/`video_note` — `media_url`

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
- Загруженные изображения, аудиосообщения и видеокружки хранятся в volume `uploads_data` (в контейнере — `/app/uploads`)
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
| `UPLOAD_DIR` | Каталог хранения медиафайлов | `uploads` |
| `MEDIA_URL_PREFIX` | URL-префикс раздачи медиафайлов | `/media` |
| `MAX_IMAGE_SIZE_BYTES` | Максимальный размер изображения, байт | `5242880` (5 МиБ) |
| `MAX_AUDIO_SIZE_BYTES` | Максимальный размер аудиосообщения, байт | `26214400` (25 МиБ) |
| `MAX_VIDEO_NOTE_SIZE_BYTES` | Максимальный размер видеокружка, байт | `26214400` (25 МиБ) |
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
