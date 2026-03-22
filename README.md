# kb-compose-bundle

Самодостаточный deployment bundle для локальной мультимодальной knowledge base:
- PostgreSQL + pgvector
- Neo4j
- Ollama
- Python API (FastAPI)
- Python Worker (ETL / Indexer / Scheduler)
- Worker Dummy API для ручной загрузки документов

## Что внутри

- `docker-compose.yml`
- `.env.template`
- `init/postgres/001_postgres_init.sql`
- `init/neo4j/001_neo4j_init.cypher`
- `api/` — FastAPI search service
- `worker/` — ETL/indexer/scheduler
- `knowledge/` — bind-mount для твоих локальных файлов
- `Makefile`

## Быстрый старт

```bash
cp .env.template .env
mkdir -p knowledge

docker compose up -d postgres neo4j ollama

docker compose run --rm neo4j-init

docker compose exec ollama ollama pull embeddinggemma

# включить embeddings в .env после загрузки модели
# KB_ENABLE_EMBEDDINGS=true

docker compose up -d --build api worker worker-api
```

После старта:
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Worker Dummy API: `http://localhost:8010`
- Neo4j Browser: `http://localhost:7474`
- PostgreSQL: `localhost:5432`
- Ollama: `http://localhost:11434`

## Полезные команды

```bash
make infra
make pull-model
make app
make logs
make reindex
```

## Важно

- `init/postgres/*.sql` выполняются только при **первой** инициализации пустого data volume Postgres.
- `NEO4J_AUTH` задаёт только начальный пароль и не меняет его, если `/data` уже содержит существующую БД.
- Для простого локального старта в compose используется база Neo4j `neo4j`, а не отдельная `knowledge`, чтобы избежать лишней операционной сложности.
- Если хочешь пересоздать схему Postgres заново, удали volume `postgres_data`.
- Если хочешь полностью пересоздать Neo4j, удали volume `neo4j_data`.

## Структура knowledge/

Сюда можно класть:
- `md`, `txt`, `json`, `yaml`, `log`
- `pdf`, `docx`, `pptx`
- `py`, `c`, `cpp`, `js`, `ts`, `sh`, `sql`
- `jpg`, `png`, `webp`, `svg`, `drawio`, `puml`

Worker будет обходить `/data/knowledge` внутри контейнера.

Для ручной загрузки документа без прямого копирования в `knowledge/` можно использовать dummy endpoint:

```bash
curl -X POST http://localhost:8010/dummy/documents \
  -F "file=@./README.md" \
  -F "relative_path=uploads/README.md"
```
