# kb-worker

Каркас Python Worker Container для ETL / Indexer / Scheduler.

Что умеет сейчас:
- сканирует дерево исходных файлов;
- определяет тип документа по расширению/mime;
- извлекает текст из text-native и code источников;
- режет текст на чанки;
- собирает базовые метаданные;
- делает upsert в PostgreSQL;
- строит graph projection в Neo4j;
- умеет работать как one-shot job или циклический scheduler.

Что пока заглушки:
- глубокий OCR;
- полноценный DOCX/PDF extraction;
- image embeddings;
- Tree-sitter символы и связи;
- LLM/NER-based entity extraction.

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
export KB_SOURCE_ROOTS=/data/knowledge
export KB_POSTGRES_DSN=postgresql://kb:kb@postgres:5432/kb
export KB_NEO4J_URI=bolt://neo4j:7687
export KB_NEO4J_USER=neo4j
export KB_NEO4J_PASSWORD=secret
kb-worker run-once
```

## Режимы

```bash
kb-worker run-once
kb-worker run-forever
```
