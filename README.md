# xam_backend

Бэкенд мессенджера (MVP): регистрация, личные диалоги, обмен текстовыми сообщениями в реальном времени и статус присутствия (online/offline).

## Стек

- Python 3.11+
- FastAPI
- PostgreSQL 15+
- SQLAlchemy 2.0 (async) + Alembic
- WebSocket (нативный FastAPI)
- JWT (Access Token)
- Redis (опционально, для присутствия)
- passlib/bcrypt (хеширование паролей)

## Архитектура

Монолит с разделением слоёв: Роутеры → Сервисы → Репозитории/Модели.

## API (v1)

### Аутентификация

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Регистрация: `username` (3–32, `[A-Za-z0-9_]`), `password` (мин. 8), `display_name`. Возвращает JWT |
| POST | `/api/v1/auth/login` | Вход по `username`/`password`, возвращает `access_token` и `token_type` |

### Пользователи

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/api/v1/users/me` | Профиль текущего пользователя |
| GET | `/api/v1/users/search?q=` | Поиск пользователей по username |

### Диалоги

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/chats` | Создать или получить личный диалог: `{ "participant_id": "uuid" }` |
| GET | `/api/v1/chats` | Список чатов с последним сообщением, сортировка по времени активности |

В БД диалог хранится с `user1_id < user2_id` и ограничением `UNIQUE(user1_id, user2_id)`.

### Сообщения

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/v1/chats/{chat_id}/messages` | Отправка: `{ "content": "...", "client_message_id": "uuid" }` |
| GET | `/api/v1/chats/{chat_id}/messages?limit=50&before=` | История, cursor-based пагинация |

### WebSocket

`ws://<host>/ws?token=<jwt>`

Сервер → клиент:

```json
{ "type": "new_message", "data": { } }
{ "type": "user_status", "data": { "user_id": "uuid", "status": "online" } }
```

Клиент → сервер: `ping` (keep-alive), опционально `typing`.

## Схема БД

- `users`: `id` UUID PK, `username` VARCHAR(32) UNIQUE, `password_hash` VARCHAR(255), `display_name` VARCHAR(64), `avatar_url` TEXT, `created_at` TIMESTAMPTZ, `last_seen` TIMESTAMPTZ
- `chats`: `id` UUID PK, `user1_id` UUID FK, `user2_id` UUID FK, `created_at` TIMESTAMPTZ, `CHECK (user1_id < user2_id)`, `UNIQUE(user1_id, user2_id)`
- `messages`: `id` UUID PK, `chat_id` UUID FK (INDEX), `sender_id` UUID FK, `content` TEXT, `client_message_id` UUID, `created_at` TIMESTAMPTZ (INDEX), `is_read` BOOLEAN
- Индекс `idx_messages_chat_created` на `(chat_id, created_at DESC)`

## Запуск (dev)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Swagger UI: http://localhost:8000/docs

## Требования

- Все эндпоинты, кроме `register`/`login`, защищены JWT; WebSocket требует валидный токен
- Валидация через Pydantic-схемы
- CORS: `http://localhost:5173` в dev
- Единый формат ошибок: `{ "detail": "..." }`
