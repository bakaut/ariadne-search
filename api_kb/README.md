# kb-api

FastAPI Search API для локальной мультимодальной базы знаний.

Что умеет сейчас:
- health endpoints;
- POST `/search` с query classification и search plan;
- lexical search по PostgreSQL FTS;
- semantic search по pgvector через Ollama query embeddings;
- OCR search по `ocr_blocks`;
- symbol/code search по таблицам `symbols` и `files`;
- optional exact search через `ripgrep` по mounted source roots;
- graph context из Neo4j для top results.

Что пока упрощено:
- image similarity branch пока заглушка;
- rerank эвристический, без cross-encoder;
- Neo4j expansion использует только текущую graph projection модель;
- нет auth/rate limiting.

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
export KB_POSTGRES_DSN=postgresql://kb:kb@postgres:5432/kb
export KB_NEO4J_URI=bolt://neo4j:7687
export KB_NEO4J_USER=neo4j
export KB_NEO4J_PASSWORD=secret
export KB_SOURCE_ROOTS=/data/knowledge
kb-api serve --host 0.0.0.0 --port 8000
```

## Основные endpoints

- `GET /health/live`
- `GET /health/ready`
- `POST /search`
