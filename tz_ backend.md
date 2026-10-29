Часть 1. Техническое задание: Бэкенд (FastAPI + PostgreSQL)
1.1. Общие сведения и архитектура
Цель MVP: Реализовать ядро мессенджера с поддержкой регистрации, личных диалогов, обмена текстовыми сообщениями в реальном времени и базового статуса присутствия (онлайн/офлайн).

Стек:

Язык: Python 3.11+

Фреймворк: FastAPI

СУБД: PostgreSQL 15+

ORM: SQLAlchemy 2.0 (async) + Alembic (миграции)

Realtime: WebSocket (нативный FastAPI)

Аутентификация: JWT (Access Token)

Кэш/Присутствие (опционально для MVP): Redis (для хранения активных WebSocket-сессий и статуса online)

Архитектурный стиль: Монолит с чётким разделением слоёв (Роутеры → Сервисы → Репозитории/Модели).

1.2. Функциональные требования
1.2.1. Аутентификация и пользователи
Регистрация:

Эндпоинт: POST /api/v1/auth/register

Поля: username (уникальный, 3–32 символа, буквы/цифры/_), password (мин. 8 символов), display_name (отображаемое имя).

Пароль хешируется (bcrypt/passlib). Возвращается JWT.

Вход:

Эндпоинт: POST /api/v1/auth/login

Принимает username и password. Возвращает access_token (JWT) и token_type.

Профиль:

Эндпоинт: GET /api/v1/users/me — возвращает данные текущего пользователя.

Эндпоинт: GET /api/v1/users/search?q={query} — поиск пользователей по username для начала диалога.

1.2.2. Диалоги (Чаты)
Для MVP реализуются только личные диалоги (1-на-1).

Создание/получение диалога:

Эндпоинт: POST /api/v1/chats

Тело: { "participant_id": "uuid_другого_пользователя" }

Логика: Если диалог между двумя пользователями уже существует — вернуть его. Если нет — создать новый.

Важно: В БД диалог хранится с полями user1_id и user2_id, где user1_id < user2_id (сортировка UUID), чтобы избежать дублирования.

Список диалогов:

Эндпоинт: GET /api/v1/chats

Возвращает список чатов пользователя с последним сообщением и временем активности (сортировка по убыванию времени).

1.2.3. Сообщения
Отправка сообщения:

Эндпоинт: POST /api/v1/chats/{chat_id}/messages

Тело: { "content": "текст", "client_message_id": "uuid" }

client_message_id — опционально, для идемпотентности и оптимистичного UI на фронте.

Сохранение в БД. После сохранения — рассылка через WebSocket участникам чата.

История сообщений:

Эндпоинт: GET /api/v1/chats/{chat_id}/messages?limit=50&before={timestamp_or_id}

Пагинация (cursor-based). Возвращает сообщения в обратном хронологическом порядке (новые сначала) или прямом (зависит от реализации фронта).

1.2.4. WebSocket (Realtime)
Эндпоинт: ws://.../ws?token={jwt}

Логика подключения:

Валидация JWT из query-параметра.

Добавление соединения в ConnectionManager (словарь user_id -> set[WebSocket]).

Отметка пользователя как online (в памяти или Redis).

События от сервера (Server → Client):

new_message: { "type": "new_message", "data": { message_object } }

user_status: { "type": "user_status", "data": { "user_id": "...", "status": "online"|"offline" } }

События от клиента (Client → Server):

ping (keep-alive).

(Опционально) typing — статус «печатает».

Отключение: Удаление из ConnectionManager, рассылка статуса offline (если нет других активных сессий).

1.3. Схема базы данных (PostgreSQL)
Таблица users
Поле	Тип	Ограничения
id	UUID	PK, default gen_random_uuid()
username	VARCHAR(32)	UNIQUE, NOT NULL
password_hash	VARCHAR(255)	NOT NULL
display_name	VARCHAR(64)	NOT NULL
avatar_url	TEXT	NULL
created_at	TIMESTAMPTZ	default now()
last_seen	TIMESTAMPTZ	NULL (обновляется при disconnect)
Таблица chats
Поле	Тип	Ограничения
id	UUID	PK
user1_id	UUID	FK → users.id, NOT NULL
user2_id	UUID	FK → users.id, NOT NULL
created_at	TIMESTAMPTZ	default now()
Constraint		CHECK (user1_id < user2_id), UNIQUE(user1_id, user2_id)
Таблица messages
Поле	Тип	Ограничения
id	UUID	PK
chat_id	UUID	FK → chats.id, NOT NULL, INDEX
sender_id	UUID	FK → users.id, NOT NULL
content	TEXT	NOT NULL
client_message_id	UUID	NULL (для дедупликации)
created_at	TIMESTAMPTZ	default now(), INDEX
is_read	BOOLEAN	default false
Индексы:

idx_messages_chat_created на (chat_id, created_at DESC) — для быстрой загрузки истории.

1.4. Нефункциональные требования (бэкенд)
Безопасность: Все эндпоинты (кроме register/login) защищены JWT middleware. WebSocket требует валидный токен.

Валидация: Pydantic-схемы для всех входящих данных.

CORS: Настроить для origin фронтенда (в dev — http://localhost:5173, в prod — домен).

Документация: Автоматическая через Swagger UI (/docs).

Обработка ошибок: Единый формат ответа об ошибке { "detail": "..." } с корректными HTTP-статусами.