# Outline → Dify RAG

Self-hosted RAG-система на базе [Outline](https://www.getoutline.com/) и [Dify](https://dify.ai/).

Outline используется как корпоративная Wiki и источник документов. Dify индексирует документы, создаёт embeddings и предоставляет RAG-интерфейс для чатботов.

## Architecture

```text
                         ┌──────────────────────┐
                         │       Outline        │
                         │   Self-hosted Wiki   │
                         └──────────┬───────────┘
                                    │
                              Outline API
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ outline-dify-sync     │
                         │      Python           │
                         └──────────┬───────────┘
                                    │
                           Dify Dataset API
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │        Dify          │
                         │    Knowledge Base    │
                         │                      │
                         │      Outline-kb      │
                         └──────────┬───────────┘
                                    │
                              Embeddings
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      LM Studio      │
                         │                      │
                         │ Nomic Embeddings     │
                         │ GPT-OSS-20B          │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Dify Chatbot     │
                         │                      │
                         │ User Input            │
                         │       ↓               │
                         │ Knowledge Retrieval   │
                         │       ↓               │
                         │ LLM                   │
                         │       ↓               │
                         │ Answer                │
                         └──────────────────────┘
```

## Components

| Component                              | Purpose                                     |
| -------------------------------------- | ------------------------------------------- |
| Outline                                | Wiki and source of truth for documentation  |
| Dify                                   | RAG platform, document indexing and chatbot |
| LM Studio                              | Local LLM and embedding server              |
| `text-embedding-nomic-embed-text-v1.5` | Text embeddings                             |
| `openai/gpt-oss-20b`                   | LLM                                         |
| Python sync service                    | Synchronizes Outline documents into Dify    |
| Nginx                                  | Reverse proxy and WebSocket proxy           |

---

# 1. Outline

Install and run Outline using the official Docker deployment.

The important requirement for this setup is that Outline has an API key that can access the documents which should be synchronized.

Create an API key in Outline.

The Outline API is available under:

```text
/api/...
```

For example:

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

## Getting the document ID

A document URL such as:

```text
http://127.0.0.1/doc/dify-rag-test-4jhObpceuQ
```

contains the public `urlId`, but the API document ID is a UUID.

Use:

```text
documents.list
```

or the Outline API to obtain the UUID.

---

# 2. Outline document export

For synchronization we use:

```text
documents.list
documents.info
documents.export
```

`documents.info` provides document metadata.

For example:

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

The response contains metadata such as:

```json
{
  "id": "294f72cd-1b64-4730-a451-dc2ba0be22ca",
  "title": "Dify RAG Test",
  "revision": 4,
  "collectionId": "7fb8d5e2-cf8a-4d06-95b6-f1c9d511fe13"
}
```

The actual document content is obtained with:

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

Example:

```json
{
  "data": "# Dify RAG Test\n\nSome document content..."
}
```

The exported content is Markdown.

---

# 3. Outline WebSocket

If Outline is behind Nginx, WebSocket support is required.

Example:

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

Without WebSocket support, Outline can show errors such as:

```text
WebSocket connection to
'ws://localhost:3000/realtime/?EIO=4&transport=websocket'
failed
```

---

# 4. Dify

Install Dify using its Docker deployment.

The important services for this setup are:

```text
api
api_websocket
web
worker
redis
db
nginx
```

The `api_websocket` service is required for Dify Socket.IO functionality.

## Dify WebSocket

Dify uses:

```text
/socket.io/
```

for its WebSocket connection.

The browser connects to:

```text
ws://localhost/socket.io/?EIO=4&transport=websocket
```

The Nginx configuration must route Socket.IO to the dedicated Dify WebSocket service.

Example:

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

A successful WebSocket upgrade should appear in the Nginx log as:

```text
GET /socket.io/?EIO=4&transport=websocket HTTP/1.1" 101
```

If `api_websocket` reports:

```text
Socket connect rejected: missing token
```

check that Dify is accessed consistently through the same hostname.

For example, do not mix:

```text
http://127.0.0.1
```

and:

```text
http://localhost
```

Use one hostname consistently.

---

# 5. Create Dify Knowledge Base

Open Dify and create a Knowledge Base.

For this setup:

```text
Knowledge Base:
Outline-kb
```

The Dataset ID can be obtained from the URL.

For example:

```text
http://127.0.0.1/datasets/4bffe83f-e069-4bc6-ab15-f6e1921a8d21/documents
```

The Dataset ID is:

```text
4bffe83f-e069-4bc6-ab15-f6e1921a8d21
```

Create a Dify API key.

---

# 6. LM Studio

LM Studio is used as an OpenAI-compatible local model server.

Run the following models:

```text
text-embedding-nomic-embed-text-v1.5
openai/gpt-oss-20b
```

Both models can run simultaneously if the available hardware has enough RAM/VRAM.

LM Studio normally exposes an OpenAI-compatible API on:

```text
http://localhost:1234/v1
```

## Check available models

```bash
curl http://localhost:1234/v1/models | jq '.data[] | .id'
```

## Test embeddings

```bash
curl http://localhost:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-nomic-embed-text-v1.5",
    "input": "This is a test document"
  }'
```

A successful response contains an embedding vector.

---

# 7. Configure Dify models

In Dify, configure an OpenAI-compatible provider.

For the LLM:

```text
Model:
openai/gpt-oss-20b

Type:
LLM

API Endpoint:
http://host.docker.internal:1234/v1
```

For embeddings:

```text
Model:
text-embedding-nomic-embed-text-v1.5

Type:
Text Embedding

API Endpoint:
http://host.docker.internal:1234/v1
```

The important detail is that the Base URL includes `/v1`.

Do not use:

```text
http://host.docker.internal:1234
```

and do not use:

```text
http://host.docker.internal:1234/v1/embeddings
```

Dify adds the API endpoint itself.

---

# 8. Importing documents into Dify

Documents can be imported manually into:

```text
Knowledge → Outline-kb
```

Once the document is indexed, Dify performs approximately:

```text
Markdown
   ↓
Chunking
   ↓
Embedding
   ↓
Vector index
```

The document should eventually have an available/ready status.

---

# 9. RAG Chatbot

Create a Chatbot in Dify.

The basic workflow is:

```text
USER INPUT
    ↓
KNOWLEDGE RETRIEVAL
    ↓
LLM
    ↓
ANSWER
```

The Knowledge Retrieval node uses:

```text
Outline-kb
```

The LLM node uses:

```text
openai/gpt-oss-20b
```

The LLM should receive the retrieved context.

A simple system prompt:

```text
You are a helpful assistant.

Answer the user's question using only the provided knowledge base context.

If the answer cannot be found in the context, say that you don't have enough information.

Do not invent information.
```

---

# 10. Test the RAG

Create a simple document in Outline:

```markdown
# Dify RAG Test

The secret project codename is BLUE-FOX-742.

The infrastructure team uses Kubernetes.
```

Synchronize it to Dify.

Then ask the chatbot:

```text
What is the secret project codename?
```

The expected answer is:

```text
BLUE-FOX-742
```

The Dify workflow should behave like:

```text
User question
      ↓
Nomic embedding
      ↓
Vector search in Outline-kb
      ↓
Relevant document chunk
      ↓
GPT-OSS-20B
      ↓
Answer
```

If the chatbot says:

```text
I’m sorry, but I don’t have that information in my knowledge base.
```

inspect the output of the `KNOWLEDGE RETRIEVAL` node first.

If the relevant chunk is missing, the problem is in indexing/retrieval.

If the chunk is present, the problem is in the LLM prompt/context connection.

---

# 11. Automatic Outline → Dify synchronization

Manual uploads are inconvenient, so this project includes a Python synchronization service.

The service:

1. Gets documents from Outline.
2. Checks document revisions.
3. Exports changed documents as Markdown.
4. Creates new documents in Dify.
5. Updates changed documents in Dify.
6. Deletes Dify documents that were removed from Outline.
7. Stores synchronization state in a persistent volume.

Architecture:

```text
Outline
   │
   │ documents.list
   ▼
sync.py
   │
   ├── new document
   │       ↓
   │   Dify create
   │
   ├── changed document
   │       ↓
   │   Dify update
   │
   └── deleted document
           ↓
       Dify delete
```

---

# 12. Sync project structure

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

If Outline and Dify are available on the same Docker network:

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

Do not commit `.env` to Git.

---

# 13. Docker networking

Do not use:

```text
http://localhost:3000
```

from inside the sync container.

Inside a container:

```text
localhost
```

refers to the container itself.

Use Docker service names instead:

```text
http://outline:3000
http://api:5001
```

If Outline and Dify are deployed by different Compose projects, create a shared external network:

```bash
docker network create rag-network
```

Add the network to both Compose projects:

```yaml
networks:
  rag-network:
    external: true
```

Then attach the required services to it.

The sync service can then communicate directly with:

```text
http://outline:3000
http://api:5001
```

without going through the public Nginx endpoints.

---

# 14. Synchronization interval

The sync service runs continuously.

For example:

```text
SYNC_INTERVAL=300
```

means:

```text
sync
 ↓
wait 5 minutes
 ↓
sync
 ↓
wait 5 minutes
 ↓
...
```

The state is stored in:

```text
/data/outline_dify_state.json
```

and persisted through the Docker volume:

```yaml
volumes:
  sync-data:
```

This prevents the service from treating every document as new after a container restart.

---

# 15. Running the sync service

Build and start:

```bash
docker compose up -d --build
```

Check logs:

```bash
docker compose logs -f outline-dify-sync
```

First synchronization:

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

When nothing changed:

```text
[SKIP] Kubernetes (revision 4)
[SKIP] Deployments (revision 2)

Sync finished.
```

When a document changes:

```text
[SYNC] Kubernetes (revision 5)
  Updating Dify document ...
  Updated.
```

---

# 16. Recommended security model

The current setup should be treated as the foundation for a larger access-controlled RAG system.

Outline should remain the source of truth for document permissions.

A possible future architecture:

```text
                    Outline
                       │
              Collections / ACL
                       │
             ┌─────────┴─────────┐
             │                   │
        Engineering             HR
             │                   │
             ▼                   ▼
       Dify Engineering       Dify HR
             │                   │
             └─────────┬─────────┘
                       │
                       ▼
                    RAG API
                       │
                  User identity
                       │
                  Permission check
                       │
                       ▼
                    Answer
```

Do not put documents with different confidentiality levels into one unrestricted Knowledge Base unless the application performs an appropriate permission check before retrieval.

---

# 17. Troubleshooting

## Dify cannot create embeddings

Error:

```text
provider_initialize
Default model not found for text-embedding
```

Configure a text embedding model in Dify.

Recommended model:

```text
text-embedding-nomic-embed-text-v1.5
```

---

## LM Studio reports

```text
Unexpected endpoint or method. (POST /embeddings)
```

Check the Dify Base URL.

Correct:

```text
http://host.docker.internal:1234/v1
```

Incorrect:

```text
http://host.docker.internal:1234
```

Dify must generate:

```text
POST /v1/embeddings
```

---

## Outline document contains text but export is empty

Check that the document has actually been saved/published and retry:

```bash
documents.export
```

The export endpoint should return Markdown.

---

## Outline WebSocket does not work

Nginx needs:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

---

## Dify WebSocket returns connection errors

Check:

```bash
docker compose ps api_websocket
```

The `api_websocket` service must be running.

Nginx should route:

```text
/socket.io/
```

to:

```text
api_websocket:5001
```

A successful upgrade appears as:

```text
101 Switching Protocols
```

If `api_websocket` reports:

```text
Socket connect rejected: missing token
```

check that Dify is accessed through a single consistent hostname, e.g.:

```text
http://localhost
```

rather than mixing:

```text
http://localhost
```

and:

```text
http://127.0.0.1
```

---

## `api_websocket` cannot read Redis

Check:

```bash
docker compose logs api_websocket
docker compose logs redis
```

From the WebSocket container:

```bash
docker compose exec api_websocket sh
```

Then verify Redis connectivity:

```bash
python -c "import socket; s=socket.create_connection(('redis',6379),5); print('OK')"
```

Expected:

```text
OK
```

---

## Sync container cannot connect to Outline or Dify

Do not use `localhost` inside the sync container.

Use Docker DNS:

```text
http://outline:3000
http://api:5001
```

Verify connectivity:

```bash
docker compose exec outline-dify-sync sh
```

Then test the services from inside the container.

---

# 18. Final result

The completed system provides:

```text
                    ┌──────────────┐
                    │    Outline   │
                    │     Wiki     │
                    └──────┬───────┘
                           │
                     automatic sync
                           │
                           ▼
                    ┌──────────────┐
                    │     Dify     │
                    │ Outline-kb   │
                    └──────┬───────┘
                           │
                     vector search
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
                    │ Dify Chatbot │
                    └──────────────┘
```

The result is a fully self-hosted Wiki + RAG stack where Outline acts as the source of documentation and Dify provides the retrieval and LLM layer.

Этот README можно положить в корень репозитория. Я намеренно оставил в нём **практическую последовательность настройки с нуля**, а не только описание готовой архитектуры.

