# Outline → Dify RAG

Self-hosted RAG-система на базе [Outline](https://www.getoutline.com/) и [Dify](https://dify.ai/).

Outline используется как корпоративная Wiki и источник документов. Dify индексирует документы, создаёт embeddings и предоставляет RAG-интерфейс для чатботов.

## Кратко

Нужны уже запущенные Outline и Dify.

Документация Outline: [outline/README.md](outline/README.md)
Документация Dify: [dify/README.md](https://github.com/langgenius/dify/blob/main/README.md)

```bash
cp .env.example .env
# заполните OUTLINE_*, DIFY_*, DIFY_DATASET_ID, OUTLINE_COLLECTION_ID, SYNC_INTERVAL

docker compose up -d --build
docker compose logs -f outline2dify
```


## Архитектура

```text
                         ┌──────────────────────┐
                         │       Outline        │
                         │    Локальная Wiki    │
                         └──────────┬───────────┘
                                    │
                              Outline API
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ outline-dify-sync    │
                         │      Python          │
                         └──────────┬───────────┘
                                    │
                           Dify Dataset API
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │        Dify          │
                         │     База знаний      │
                         │                      │
                         │      Outline-kb      │
                         └──────────┬───────────┘
                                    │
                              Эмбеддинги
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      LM Studio       │
                         │                      │
                         │ Nomic Embeddings     │
                         │ GPT-OSS-20B          │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Чатбот Dify      │
                         │                      │
                         │ Ввод пользователя    │
                         │       ↓              │
                         │ Поиск в базе знаний  │
                         │       ↓              │
                         │ LLM                  │
                         │       ↓              │
                         │ Ответ                │
                         └──────────────────────┘
```

## Компоненты

| Компонент                              | Назначение                                      |
| -------------------------------------- | ----------------------------------------------- |
| Outline                                | Wiki и источник документации                    |
| Dify                                   | RAG-платформа, индексация документов и чатбот   |
| LM Studio                              | Локальный сервер LLM и эмбеддингов              |
| `text-embedding-nomic-embed-text-v1.5` | Текстовые эмбеддинги                            |
| `openai/gpt-oss-20b`                   | LLM                                             |
| Python-сервис синхронизации            | Синхронизирует документы Outline в Dify         |
| Nginx                                  | Обратный прокси и прокси для WebSocket          |

---

# 1. Outline

Установите и запустите Outline официальным Docker-развёртыванием.

Для этой схемы нужен API-ключ Outline с доступом к документам, которые нужно синхронизировать.

Создайте API-ключ в Outline.

API Outline доступен по пути:

```text
/api/...
```

Пример:

```bash
curl \
  -X POST \
  http://localhost:3000/api/documents.info \
  -H "Authorization: Bearer YOUR_OUTLINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "DOCUMENT_ID"
  }'
```

## Как получить ID документа

URL документа, например:

```text
http://127.0.0.1/doc/dify-rag-test-4jhObpceuQ
```

содержит публичный `urlId`. ID документа в API — это UUID.

Получите UUID через:

```text
documents.list
```

или через API Outline.

---

# 2. Экспорт документов Outline

Для синхронизации используются методы:

```text
documents.list
documents.info
documents.export
```

`documents.info` возвращает метаданные документа.

Пример:

```bash
curl \
  -X POST \
  http://localhost:3000/api/documents.info \
  -H "Authorization: Bearer YOUR_OUTLINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "294f72cd-1b64-4730-a451-dc2ba0be22ca"
  }'
```

В ответе есть метаданные, например:

```json
{
  "id": "294f72cd-1b64-4730-a451-dc2ba0be22ca",
  "title": "Dify RAG Test",
  "revision": 4,
  "collectionId": "7fb8d5e2-cf8a-4d06-95b6-f1c9d511fe13"
}
```

Содержимое документа получается так:

```bash
curl \
  -X POST \
  http://localhost:3000/api/documents.export \
  -H "Authorization: Bearer YOUR_OUTLINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "294f72cd-1b64-4730-a451-dc2ba0be22ca"
  }'
```

Пример:

```json
{
  "data": "# Dify RAG Test\n\nSome document content..."
}
```

Экспортированное содержимое — это Markdown.

---

# 3. WebSocket в Outline

Если Outline стоит за Nginx, нужна поддержка WebSocket.

Пример:

```nginx
server {
    listen 3000;
    server_name localhost;

    location / {
        proxy_pass http://outline:3000;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Без поддержки WebSocket Outline может показывать ошибки вида:

```text
WebSocket connection to
'ws://localhost:3000/realtime/?EIO=4&transport=websocket'
failed
```

---

# 4. Dify

Установите Dify через его Docker-развёртывание.

Для этой схемы важны сервисы:

```text
api
api_websocket
web
worker
redis
db
nginx
```

Сервис `api_websocket` нужен для Socket.IO в Dify.

## WebSocket в Dify

Dify использует путь:

```text
/socket.io/
```

Браузер подключается к:

```text
ws://localhost/socket.io/?EIO=4&transport=websocket
```

В конфигурации Nginx Socket.IO нужно направить на отдельный WebSocket-сервис Dify.

Пример:

```nginx
location /socket.io/ {
    proxy_pass http://api_websocket:5001;

    proxy_http_version 1.1;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}
```

Успешное обновление до WebSocket в логе Nginx выглядит так:

```text
GET /socket.io/?EIO=4&transport=websocket HTTP/1.1" 101
```

Если `api_websocket` пишет:

```text
Socket connect rejected: missing token
```

проверьте, что к Dify всегда обращаются через одно и то же имя хоста.

Например, не смешивайте:

```text
http://127.0.0.1
```

и:

```text
http://localhost
```

Используйте одно имя хоста.

---

# 5. Создание базы знаний в Dify

Откройте Dify и создайте базу знаний (Knowledge Base).

Для этой схемы:

```text
Knowledge Base:
Outline-kb
```

Dataset ID можно взять из URL.

Например:

```text
http://127.0.0.1/datasets/4bffe83f-e069-4bc6-ab15-f6e1921a8d21/documents
```

Dataset ID:

```text
4bffe83f-e069-4bc6-ab15-f6e1921a8d21
```

Создайте API-ключ Dify.

---

# 6. LM Studio

LM Studio используется как локальный сервер моделей с API, совместимым с OpenAI.

Запустите модели:

```text
text-embedding-nomic-embed-text-v1.5
openai/gpt-oss-20b
```

Обе модели могут работать одновременно, если хватает RAM/VRAM.

Обычно LM Studio отдаёт OpenAI-совместимый API по адресу:

```text
http://localhost:1234/v1
```

## Проверка доступных моделей

```bash
curl http://localhost:1234/v1/models | jq '.data[] | .id'
```

## Проверка эмбеддингов

```bash
curl http://localhost:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-nomic-embed-text-v1.5",
    "input": "This is a test document"
  }'
```

Успешный ответ содержит вектор эмбеддинга.

---

# 7. Настройка моделей в Dify

В Dify настройте провайдера, совместимого с OpenAI.

Для LLM:

```text
Модель:
openai/gpt-oss-20b

Тип:
LLM

API Endpoint:
http://host.docker.internal:1234/v1
```

Для эмбеддингов:

```text
Модель:
text-embedding-nomic-embed-text-v1.5

Тип:
Text Embedding

API Endpoint:
http://host.docker.internal:1234/v1
```

Важно: Base URL включает `/v1`.

Не используйте:

```text
http://host.docker.internal:1234
```

и не используйте:

```text
http://host.docker.internal:1234/v1/embeddings
```

Dify сам добавляет нужный endpoint API.

---

# 8. Импорт документов в Dify

Документы можно импортировать вручную в:

```text
Knowledge → Outline-kb
```

После индексации Dify выполняет примерно такую цепочку:

```text
Markdown
   ↓
Нарезка на чанки
   ↓
Эмбеддинг
   ↓
Векторный индекс
```

В итоге у документа должен появиться статус available/ready.

---

# 9. RAG-чатбот

Создайте чатбот в Dify.

Базовый сценарий:

```text
ВВОД ПОЛЬЗОВАТЕЛЯ
    ↓
ПОИСК ПО БАЗЕ ЗНАНИЙ
    ↓
LLM
    ↓
ОТВЕТ
```

Узел Knowledge Retrieval использует:

```text
Outline-kb
```

Узел LLM использует:

```text
openai/gpt-oss-20b
```

LLM должна получать найденный контекст.

Простой системный промпт:

```text
Вы — полезный ассистент.

Отвечайте на вопрос пользователя, используя только предоставленный контекст базы знаний.

Если ответа нет в контексте, скажите, что информации недостаточно.

Не выдумывайте информацию.
```

---

# 10. Проверка RAG

Создайте в Outline простой документ:

```markdown
# Тест Dify RAG

Секретное кодовое имя проекта — BLUE-FOX-742.

Команда инфраструктуры использует Kubernetes.
```

Синхронизируйте его в Dify.

Затем спросите чатбот:

```text
Какое секретное кодовое имя проекта?
```

Ожидаемый ответ:

```text
BLUE-FOX-742
```

Сценарий в Dify должен работать так:

```text
Вопрос пользователя
      ↓
Эмбеддинг Nomic
      ↓
Векторный поиск в Outline-kb
      ↓
Релевантный чанк документа
      ↓
GPT-OSS-20B
      ↓
Ответ
```

Если чатбот отвечает, что в базе знаний нет этой информации, сначала посмотрите вывод узла `KNOWLEDGE RETRIEVAL`.

Если нужного чанка нет, проблема в индексации или поиске.

Если чанк есть, проблема в промпте LLM или в том, как к нему подключён контекст.

---

# 11. Автоматическая синхронизация Outline → Dify

Ручная загрузка неудобна, поэтому в проекте есть Python-сервис синхронизации.

Сервис:

1. Получает документы из Outline.
2. Проверяет ревизии документов.
3. Экспортирует изменённые документы в Markdown.
4. Создаёт новые документы в Dify.
5. Обновляет изменённые документы в Dify.
6. Удаляет из Dify документы, удалённые в Outline.
7. Хранит состояние синхронизации в постоянном томе.

Архитектура:

```text
Outline
   │
   │ documents.list
   ▼
sync.py
   │
   ├── новый документ
   │       ↓
   │   создание в Dify
   │
   ├── изменённый документ
   │       ↓
   │   обновление в Dify
   │
   └── удалённый документ
           ↓
       удаление в Dify
```

---

# 12. Структура проекта синхронизации

```text
outline-dify-sync/
├── Dockerfile
├── docker-compose.yml
├── sync.py
├── .env
└── state/
```

## Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY sync.py .

RUN pip install --no-cache-dir requests

RUN mkdir -p /data

ENV STATE_FILE=/data/outline_dify_state.json

CMD ["python", "-u", "sync.py"]
```

## docker-compose.yml

Если Outline и Dify доступны в одной Docker-сети:

```yaml
services:
  outline-dify-sync:
    build:
      context: .
      dockerfile: Dockerfile

    container_name: outline-dify-sync

    environment:
      OUTLINE_URL: "http://outline:3000"
      OUTLINE_API_KEY: "${OUTLINE_API_KEY}"

      DIFY_URL: "http://api:5001"
      DIFY_API_KEY: "${DIFY_API_KEY}"

      DIFY_DATASET_ID: "4bffe83f-e069-4bc6-ab15-f6e1921a8d21"

      OUTLINE_COLLECTION_ID: "7fb8d5e2-cf8a-4d06-95b6-f1c9d511fe13"

      STATE_FILE: "/data/outline_dify_state.json"

      SYNC_INTERVAL: "300"

    volumes:
      - sync-data:/data

    restart: unless-stopped

volumes:
  sync-data:
```

`.env`:

```dotenv
OUTLINE_API_KEY=YOUR_OUTLINE_API_KEY
DIFY_API_KEY=YOUR_DIFY_API_KEY
```

Не коммитьте `.env` в Git.

---

# 13. Сеть Docker

Из контейнера синхронизации не используйте:

```text
http://localhost:3000
```

Внутри контейнера:

```text
localhost
```

указывает на сам контейнер.

Используйте имена сервисов Docker:

```text
http://outline:3000
http://api:5001
```

Если Outline и Dify развёрнуты разными Compose-проектами, создайте общую внешнюю сеть:

```bash
docker network create rag-network
```

Добавьте сеть в оба Compose-проекта:

```yaml
networks:
  rag-network:
    external: true
```

Затем подключите к ней нужные сервисы.

После этого сервис синхронизации обращается напрямую к:

```text
http://outline:3000
http://api:5001
```

минуя публичные endpoint'ы Nginx.

---

# 14. Интервал синхронизации

Сервис синхронизации работает постоянно.

Например:

```text
SYNC_INTERVAL=300
```

означает:

```text
синхронизация
 ↓
пауза 5 минут
 ↓
синхронизация
 ↓
пауза 5 минут
 ↓
...
```

Состояние хранится в:

```text
/data/outline_dify_state.json
```

и сохраняется через Docker-том:

```yaml
volumes:
  sync-data:
```

Благодаря этому после перезапуска контейнера сервис не считает каждый документ новым.

---

# 15. Запуск сервиса синхронизации

Сборка и запуск:

```bash
docker compose up -d --build
```

Просмотр логов:

```bash
docker compose logs -f outline-dify-sync
```

Первая синхронизация:

```text
Loading documents from Outline...
Found 12 documents in Outline.

[SYNC] Kubernetes
  Creating in Dify...
  Created: ...

[SYNC] Deployments
  Creating in Dify...
  Created: ...

Sync finished.
Next sync in 300 seconds...
```

Если ничего не изменилось:

```text
[SKIP] Kubernetes (revision 4)
[SKIP] Deployments (revision 2)

Sync finished.
```

Если документ изменился:

```text
[SYNC] Kubernetes (revision 5)
  Updating Dify document ...
  Updated.
```

---

# 16. Рекомендуемая модель доступа

Текущую схему стоит рассматривать как основу для более крупной RAG-системы с контролем доступа.

Outline остаётся источником правды для прав на документы.

Возможная архитектура в будущем:

```text
                    Outline
                       │
              Коллекции / ACL
                       │
             ┌─────────┴─────────┐
             │                   │
        Разработка              HR
             │                   │
             ▼                   ▼
       Dify: разработка       Dify: HR
             │                   │
             └─────────┬─────────┘
                       │
                       ▼
                    RAG API
                       │
                Личность пользователя
                       │
                 Проверка прав
                       │
                       ▼
                     Ответ
```

Документы разного уровня конфиденциальности не стоит складывать в одну открытую базу знаний, если приложение не проверяет права до поиска.

---

# 17. Устранение неполадок

## Dify не может создать эмбеддинги

Ошибка:

```text
provider_initialize
Default model not found for text-embedding
```

Настройте в Dify модель текстовых эмбеддингов.

Рекомендуемая модель:

```text
text-embedding-nomic-embed-text-v1.5
```

---

## LM Studio сообщает

```text
Unexpected endpoint or method. (POST /embeddings)
```

Проверьте Base URL в Dify.

Правильно:

```text
http://host.docker.internal:1234/v1
```

Неправильно:

```text
http://host.docker.internal:1234
```

Dify должен формировать запрос:

```text
POST /v1/embeddings
```

---

## В документе Outline есть текст, а экспорт пустой

Убедитесь, что документ сохранён и опубликован, и повторите:

```bash
documents.export
```

Endpoint экспорта должен вернуть Markdown.

---

## WebSocket Outline не работает

В Nginx нужны строки:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

---

## WebSocket Dify возвращает ошибки соединения

Проверьте:

```bash
docker compose ps api_websocket
```

Сервис `api_websocket` должен быть запущен.

Nginx должен направлять:

```text
/socket.io/
```

на:

```text
api_websocket:5001
```

Успешное обновление протокола выглядит так:

```text
101 Switching Protocols
```

Если `api_websocket` пишет:

```text
Socket connect rejected: missing token
```

обращайтесь к Dify через одно и то же имя хоста, например:

```text
http://localhost
```

и не смешивайте его с:

```text
http://127.0.0.1
```

---

## `api_websocket` не может прочитать Redis

Проверьте:

```bash
docker compose logs api_websocket
docker compose logs redis
```

Из контейнера WebSocket:

```bash
docker compose exec api_websocket sh
```

Затем проверьте доступность Redis:

```bash
python -c "import socket; s=socket.create_connection(('redis',6379),5); print('OK')"
```

Ожидаемый результат:

```text
OK
```

---

## Контейнер синхронизации не подключается к Outline или Dify

Внутри контейнера синхронизации не используйте `localhost`.

Используйте DNS Docker:

```text
http://outline:3000
http://api:5001
```

Проверьте связность:

```bash
docker compose exec outline-dify-sync sh
```

Затем проверьте сервисы изнутри контейнера.

---

# 18. Итог

Готовая система выглядит так:

```text
                    ┌──────────────┐
                    │    Outline   │
                    │     Wiki     │
                    └──────┬───────┘
                           │
                     синхронизация
                           │
                           ▼
                    ┌──────────────┐
                    │     Dify     │
                    │ Outline-kb   │
                    └──────┬───────┘
                           │
                    векторный поиск
                           │
                           ▼
                    ┌──────────────┐
                    │ LM Studio    │
                    │              │
                    │ Nomic        │
                    │ GPT-OSS-20B  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Чатбот Dify  │
                    └──────────────┘
```

В результате получается полностью self-hosted стек Wiki + RAG: Outline хранит документацию, а Dify отвечает за поиск и слой LLM.

Этот README можно положить в корень репозитория. Я намеренно оставил в нём **практическую последовательность настройки с нуля**, а не только описание готовой архитектуры.
