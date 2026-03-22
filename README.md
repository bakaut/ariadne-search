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
docker compose exec ollama ollama pull llama3.1:8b

# включить embeddings в .env после загрузки модели
# KB_ENABLE_EMBEDDINGS=true

docker compose up -d --build api worker worker-api
```

После старта:
- API: `http://localhost:8000`
- API Swagger UI: `http://localhost:8000/docs`
- Worker Dummy API: `http://localhost:8010`
- Worker Swagger UI: `http://localhost:8010/docs`
- Neo4j Browser: `http://localhost:7474`
- PostgreSQL: `localhost:5432`
- Ollama: `http://localhost:11434`

## Swagger / OpenAPI

Локально:
- search API Swagger UI: `http://localhost:8000/docs`
- search API OpenAPI JSON: `http://localhost:8000/openapi.json`
- worker dummy API Swagger UI: `http://localhost:8010/docs`
- worker dummy API OpenAPI JSON: `http://localhost:8010/openapi.json`

## Postman

Готовые Postman-файлы лежат в `postman/`:
- `postman/ariadne-search.postman_collection.json`
- `postman/ariadne-search-local.postman_environment.json`
- `postman/ariadne-search-remote.postman_environment.json`

Как использовать:
- импортируй collection и нужный environment в Postman;
- выбери environment c `baseUrl`;
- открой любой request из папки `Search`;
- в Postman нажми `</>` чтобы сгенерировать code snippet для текущего search-запроса.


## Полезные команды

```bash
make infra
make pull-model
make app
make logs
make reindex
```

## Важно

- В `.env` должен быть задан `KB_NEO4J_PASSWORD` с ненулевым и не-дефолтным значением. Значение `neo4j` невалидно для новых образов Neo4j.
- `init/postgres/*.sql` выполняются только при **первой** инициализации пустого data volume Postgres.
- Образ Postgres по умолчанию закреплён на `pgvector/pgvector:pg17-trixie`, чтобы уже созданный volume `postgres_data` не ломался из-за перехода на layout PostgreSQL 18.
- `NEO4J_AUTH` задаёт только начальный пароль и не меняет его, если `/data` уже содержит существующую БД.
- Для простого локального старта в compose используется база Neo4j `neo4j`, а не отдельная `knowledge`, чтобы избежать лишней операционной сложности.
- Если хочешь пересоздать схему Postgres заново, удали volume `postgres_data`.
- Если хочешь полностью пересоздать Neo4j, удали volume `neo4j_data`.

## Структура knowledge/

Сюда можно класть:
- текст и конфиги: `md`, `txt`, `rst`, `html`, `htm`, `json`, `yaml`, `yml`, `toml`, `log`
- документы: `pdf`, `doc`, `docx`, `rtf`, `odt`, `pptx`, `xlsx`
- код: `py`, `c`, `cc`, `cpp`, `cxx`, `h`, `hpp`, `js`, `ts`, `go`, `java`, `sql`, `sh`
- изображения: `jpg`, `jpeg`, `png`, `webp`, `tif`, `tiff`
- диаграммы: `svg`, `drawio`, `puml`, `plantuml`, `mmd`

Worker будет обходить `/data/knowledge` внутри контейнера.

## Dummy Upload Handler

Для ручной загрузки документа без прямого копирования в `knowledge/` можно использовать endpoint `POST /dummy/documents` на `worker-api`.

Формат запроса:
- `file` — multipart file, обязательный.
- `relative_path` — относительный путь внутри первого каталога из `KB_SOURCE_ROOTS`, опциональный.
- `force` — опциональный boolean; если `true`, ETL выполняется даже для уже известных checksum.
- если `relative_path` не передан, используется `filename` из multipart payload.

Ограничения handler'а:
- принимает только относительные пути.
- запрещает `..` и любые попытки выйти за пределы knowledge root.
- проверяет расширение файла по allowlist из worker config.
- сохраняет файл на диск перед синхронным ETL/indexing.

Статусы ответа:
- `indexed` — файл записан и успешно прошёл ETL/indexing.
- `unchanged` — файл уже был проиндексирован с тем же checksum.

Типовые ошибки:
- `400 Bad Request` — пустой upload, неподдерживаемое расширение, абсолютный путь, path traversal.
- `500 Internal Server Error` — файл сохранён, но indexing pipeline завершился ошибкой.

Текущее поведение по типам:
- `text`, `code`, `diagram` ветки уже дают searchable chunks.
- `image`, `pdf`, `docx` и остальные office/OCR ветки пока подключены как stub-экстракторы: файл будет принят и зарегистрирован как document/asset, но searchable text может не появиться, пока не подключён реальный extractor.

Пример:

```bash
curl -X POST http://localhost:8010/dummy/documents \
  -F "file=@./README.md" \
  -F "relative_path=uploads/README.md" \
  -F "force=true"
```

Для принудительной загрузки всего дерева `knowledge/` через dummy API:

```bash
./scripts/force-upload-knowledge.sh
```

Переменные:
- `WORKER_API_URL` — базовый URL worker API, по умолчанию `http://localhost:8010`.
- `KNOWLEDGE_DIR` — путь до локального каталога `knowledge/`, по умолчанию `./knowledge`.
- Скрипт автоматически пропускает файлы с расширениями вне worker allowlist.
