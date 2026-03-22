# Unit Test Plan for Worker

## Scope

Этот документ описывает unit-тесты для сервиса `worker/` как ETL / indexing / scheduling компонента.

Под `worker` в текущем репозитории понимается `worker/src/kb_worker`, то есть ingestion pipeline, который:

- сканирует файловые источники;
- классифицирует документ;
- извлекает текст или OCR-данные;
- режет контент на чанки;
- обогащает метаданными;
- извлекает сущности и символы;
- строит embeddings;
- пишет данные в PostgreSQL;
- строит graph projection в Neo4j.

## Архитектурный контекст

После чтения `arch/01-architecture-overview-v2-multimodal.puml`, `arch/03-etl-sequence-v2-multimodal.puml` и текущей реализации `worker/src/kb_worker` картина такая:

- `WorkerScheduler` запускает циклы сканирования и передаёт файлы в `ETLPipeline`.
- `FileScanner` обходит `source_roots`, фильтрует файлы и собирает `FileRecord`.
- `ETLPipeline.process_file()` является главным orchestration-методом.
- Ветка extraction выбирается через `DocumentClassifier`.
- Затем идут `Chunker`, `MetadataEnricher`, `EntityExtractor`, `OllamaEmbedder`, `PostgresStore`, `Neo4jProjectionStore`.

Важно:

- Архитектурно ETL задуман как мультимодальный и более глубокий.
- В текущем коде часть веток является stub/упрощением:
  - `OCRExtractor.extract_image()` всегда возвращает пустой результат;
  - `OfficePdfExtractor` почти заглушка;
  - `EntityExtractor` работает по простому regex;
  - `CodeParser` полноценно поддерживает только Python через `ast`;
  - image embeddings не используются;
  - `follow_symlinks` в `Settings` сейчас фактически не участвует в `FileScanner.scan()`.
- Эти различия надо фиксировать в тест-плане как текущее поведение.

## Цель unit-тестов

- Зафиксировать контракт текущего ETL pipeline.
- Проверить orchestration и ветвление без реальных PostgreSQL, Neo4j и Ollama.
- Локализовать регрессии в classifier/chunker/scanner/pipeline до интеграционных тестов.

## Out of Scope

- Реальные подключения к PostgreSQL, Neo4j, Ollama.
- Реальная обработка OCR/PDF/DOCX через внешние тулзы.
- End-to-end тесты через `docker compose`.
- Нагрузочные тесты и file watcher/inotify сценарии.

## Предлагаемая структура тестов

- `tests/test_pipeline.py`
- `tests/test_scheduler.py`
- `tests/test_scanner.py`
- `tests/test_classifier.py`
- `tests/test_chunker.py`
- `tests/test_enricher.py`
- `tests/test_entity_extractor.py`
- `tests/test_embedder.py`
- `tests/test_code_parser.py`
- `tests/test_extractors.py`
- `tests/test_postgres_store_helpers.py`
- `tests/test_neo4j_projection.py`
- `tests/test_main.py`

## Общие test doubles

Нужны mocks/stubs для:

- `PostgresStore`
- `Neo4jProjectionStore`
- `OllamaEmbedder`
- `TextExtractor`
- `OfficePdfExtractor`
- `OCRExtractor`
- `CodeParser`
- `magic.from_file`
- `httpx.Client`
- `psycopg.connect`
- `neo4j.GraphDatabase.driver`
- `time.sleep`

Базовый подход:

- Unit-тесты `ETLPipeline` не должны использовать реальные DB clients.
- После создания `ETLPipeline` зависимости лучше подменять mock-объектами.
- Для storage-классов тестировать только orchestration/helper-логику и SQL/queries как контракт, но не живую БД.

## 1. ETLPipeline.process_file

Файл: `worker/src/kb_worker/pipeline.py`

Это главный unit-test surface.

### Что проверять

- skip unchanged files;
- корректный порядок ETL шагов;
- корректная запись в bundle;
- обработка ошибок и `mark_failed`;
- возврат `bool` как итог индексации.

### Набор кейсов

1. Unchanged file пропускается
- `postgres.has_changed()` возвращает `False`.
- Ожидание: `process_file()` возвращает `False`.
- Никакие extractor/enricher/embed/upsert/project не вызываются.

2. Успешный happy path
- `has_changed()` возвращает `True`.
- Все стадии выполняются успешно.
- Ожидание: вызываются `_extract_into_bundle`, `enricher.enrich`, `entities.extract`, `_embed`, `postgres.upsert_bundle`, `neo4j.project_bundle`.
- Метод возвращает `True`.

3. `source_type` берётся из classifier
- Проверить, что `bundle.source_type` заполняется до этапов enrichment/upsert.

4. Entity extractor получает именно `bundle.chunks`
- Это важно, потому что сущности извлекаются после extraction и enrichment.

5. Ошибка на любом шаге не валит весь worker
- Смоделировать exception в extractor, enricher, embedder, postgres или neo4j.
- Ожидание: `process_file()` возвращает `False`, вызывает `postgres.mark_failed(...)`.

6. В `mark_failed()` передаётся `bundle.document_id`
- Даже если ошибка произошла после создания bundle, но до `upsert_bundle()`.

7. Ошибка после `upsert_bundle()` тоже переводится в failed
- Это текущее поведение стоит зафиксировать, даже если later может понадобиться отдельно маркировать partial success.

## 2. ETLPipeline._extract_into_bundle

### Что проверять

Нужно отдельными unit-тестами покрыть каждую ветку `source_type`.

1. `text_native`
- Вызывает `text_extractor.extract(path)`.
- Передаёт текст в `chunker.chunk_text(text)`.
- Заполняет `bundle.chunks`.

2. `office_document` с pages
- `office_pdf_extractor.extract()` возвращает `raw_text, pages`.
- `bundle.pages = pages`.
- Для каждой страницы вызывается `chunker.chunk_text(page.page_text, page_number=page.page_number)`.

3. `office_document` без pages
- Если pages пусты, pipeline чанкует `raw_text`.

4. `pdf_document` без OCR
- Есть `pages`, `requires_ocr=False`.
- Чанки строятся по `page.page_text`.

5. `pdf_document` fallback на `raw_text`
- Если pages есть, но тексты пустые и итоговых чанков нет, а `raw_text` не пустой, используется fallback `chunk_text(raw_text)`.

6. `pdf_document` с OCR
- `requires_ocr=True` и extractor вернул пустые pages.
- Вызывается `ocr_extractor.extract_image(path)`.
- Заполняются `bundle.pages`, `bundle.ocr_blocks`.
- Чанки создаются как `chunk_kind="ocr"`.

7. `image`
- В `bundle.assets` добавляется `AssetArtifact` с `asset_type="image"` и `asset_role="source_image"`.
- OCR branch вызывается всегда.
- OCR text превращается в `ocr`-chunks.

8. `diagram`
- Используется `text_extractor.extract(path)`.
- Чанки создаются с `chunk_kind="diagram"`.
- В `bundle.assets` добавляется `diagram_source`.

9. `code`
- Используется `text_extractor.extract(path)`.
- `bundle.language` определяется через `classifier.guess_language(path)`.
- Чанки создаются с `chunk_kind="code"`.
- `code_parser.parse(path, language)` заполняет `bundle.symbols` и `bundle.symbol_links`.

10. `unknown`
- Используется generic text extraction + `chunker.chunk_text(text)`.

## 3. ETLPipeline._embed

### Что проверять

1. В embedder отправляется список `chunk.content`.
2. Embeddings раскладываются обратно по chunk в том же порядке.
3. Если embedder вернул меньше векторов, чем чанков, лишние чанки остаются с `embedding=None`.
4. Если embedder вернул `None` для отдельных чанков, это значение сохраняется.
5. Если чанков нет, вызывается `embed_texts([])` и побочных эффектов нет.

## 4. ETLPipeline.close

### Что проверять

1. `close()` вызывает только `neo4j.close()`.
2. `close()` не закрывает `postgres` и `embedder`.
- Это текущее поведение, его лучше зафиксировать тестом.

## 5. WorkerScheduler

Файл: `worker/src/kb_worker/scheduler.py`

### Что проверять

1. `run_once()` обрабатывает все файлы из scanner
- `processed` равен сумме truthy-результатов `pipeline.process_file()`.

2. `run_once()` корректно возвращает `0`, если файлов нет.

3. `run_forever()` циклически вызывает `run_once()`
- С mock `time.sleep`.

4. `run_forever()` использует `settings.scheduler_interval_seconds`

5. `run_forever()` в `finally` вызывает `close()`
- Даже при exception из `run_once()`.

6. `close()` делегирует в `pipeline.close()`

## 6. Main CLI

Файл: `worker/src/kb_worker/main.py`

### Что проверять

1. `build_parser()` поддерживает `run-once`
2. `build_parser()` поддерживает `run-forever`
3. `main()` для `run-once` вызывает `scheduler.run_once()`
4. `main()` для `run-forever` вызывает `scheduler.run_forever()`
5. `setup_logging()` вызывается с `settings.log_level`
6. В `finally` всегда вызывается `scheduler.close()`

Отдельное замечание:

- Для ветки `run-forever` сейчас возможен double-close:
  - `WorkerScheduler.run_forever()` сам вызывает `self.close()` в `finally`;
  - `main()` потом снова вызывает `scheduler.close()`.
- Это стоит зафиксировать как текущее поведение отдельным unit-тестом, а не терять.

## 7. FileScanner

Файл: `worker/src/kb_worker/services/scanner.py`

### Что проверять

1. Несуществующий source root пропускается
- Ошибки нет, результат корректный.

2. Сканер берёт только файлы
- Директории не попадают в результат.

3. Hidden files исключаются при `include_hidden=False`
- Если любой segment path начинается с `.`, файл пропускается.

4. Hidden files включаются при `include_hidden=True`

5. Файлы с неподдерживаемым расширением пропускаются

6. Supported files превращаются в `FileRecord`
- Проверить `path`, `checksum`, `size_bytes`, `modified_at`, `mime_type`.

7. `_checksum()` считает SHA-256 корректно

8. `_mime_type()` возвращает результат `magic.from_file(..., mime=True)`

9. `_mime_type()` безопасно возвращает `None` при исключении

10. Порядок файлов
- Если хочется стабильности, тесты лучше не полагать на filesystem order.
- В самом документе это важно зафиксировать как источник flaky tests.

11. `follow_symlinks` сейчас не влияет на поведение
- Настройка есть в `Settings`, но `scan()` её не использует.
- Это стоит отметить как текущее ограничение.

## 8. DocumentClassifier

Файл: `worker/src/kb_worker/services/classifier.py`

### Что проверять

1. Text extensions -> `text_native`
2. Office extensions -> `office_document` и `is_paged=True`
3. PDF extensions -> `pdf_document`
4. PDF с `mime_type` starting with `image/` -> `requires_ocr=True`
5. Code extensions -> `code` и `is_code=True`
6. Image extensions -> `image`, `is_image=True`, `requires_ocr=True`
7. Diagram extensions -> `diagram`, `is_diagram=True`
8. Unknown extension -> `unknown`

### `guess_language`

1. Возвращает язык для известных расширений
2. Возвращает `None` для неизвестных расширений
3. `.hpp/.cpp/.cc/.cxx` мапятся в `cpp`
4. `.yaml/.yml` мапятся в `yaml`

## 9. Chunker

Файл: `worker/src/kb_worker/services/chunker.py`

### Что проверять

1. Пустой или whitespace-only текст возвращает `[]`
2. Короткий текст даёт один chunk
3. Длинный текст режется на несколько chunk по `chunk_size_chars`
4. Overlap учитывается через `chunk_overlap_chars`
5. `chunk_index` инкрементируется последовательно
6. `start_offset` и `end_offset` выставляются корректно
7. `page_number` пробрасывается в каждый chunk
8. `chunk_kind` пробрасывается в каждый chunk
9. Нет бесконечного цикла при overlap >= size
- Логика `start = max(end - overlap, start + 1)` это предотвращает; тест должен это зафиксировать.

## 10. MetadataEnricher

Файл: `worker/src/kb_worker/services/enricher.py`

### Что проверять

1. `title = path.stem`
2. `language` определяется через `DocumentClassifier.guess_language`
3. `metadata` получает:
- `filename`
- `extension`
- `size_bytes`
- `modified_at`
- `repo_hint`
- `path_parts`

4. Метод возвращает тот же `bundle`

### `_repo_hint`

1. Возвращает путь до ближайшего git root
2. Возвращает `None`, если `.git` не найден
3. Ищет по `path.parents`, а не только в текущей директории

## 11. EntityExtractor

Файл: `worker/src/kb_worker/services/entity_extractor.py`

### Что проверять

1. Capitalized tokens длиной от 3 символов извлекаются
2. Для каждого mention выставляется:
- `canonical_name`
- `mention_text`
- `entity_type="keyword"`
- `confidence=0.35`
- `chunk_index`

3. Извлекаются несколько сущностей из одного chunk
4. Пустой список chunk -> пустой результат
5. lower-case токены не попадают

Важно:

- Это regex-baseline, а не настоящий NER.
- Тесты должны фиксировать именно текущую простую эвристику.

## 12. OllamaEmbedder

Файл: `worker/src/kb_worker/services/embedder.py`

### Что проверять

1. При `enable_embeddings=False` возвращается список `[None, ...]` той же длины, что `texts`
2. Пустой вход `[]` возвращает `[]`
3. Для каждого текста выполняется POST на `/api/embeddings`
4. Payload содержит `model` и `prompt`
5. Успешный ответ добавляет `payload.get("embedding")` в results
6. Ошибка HTTP или JSON не валит метод целиком
- Вместо этого соответствующий элемент results становится `None`

7. При частичных сбоях остальные тексты продолжают обрабатываться
8. Используется context manager `httpx.Client(...)`

## 13. Extractors

### `TextExtractor`

Файл: `worker/src/kb_worker/extractors/text.py`

1. Читает текст как UTF-8 с `errors="ignore"`
2. Возвращает ровно то, что прочитано из файла

### `OfficePdfExtractor`

Файл: `worker/src/kb_worker/extractors/office_pdf.py`

1. Для `.md/.txt` читает файл и возвращает:
- `raw_text`
- `pages=[PageArtifact(page_number=1, page_text=raw_text)]`

2. Для остальных расширений сейчас возвращает пустой `raw_text` и пустой `pages`
- Это стоит зафиксировать как текущую заглушку.

### `OCRExtractor`

Файл: `worker/src/kb_worker/extractors/ocr.py`

1. `extract_image()` сейчас всегда возвращает `([], [], "")`
- Это текущее stub-поведение и его нужно фиксировать тестом.

## 14. CodeParser

Файл: `worker/src/kb_worker/parsers/code_parser.py`

### Что проверять

1. Для не-Python language возвращает `([], [])`
2. Для Python файла с syntax error возвращает `([], [])`
3. Находит `FunctionDef`
4. Находит `AsyncFunctionDef`
5. Находит `ClassDef`
6. Формирует `fq_name` как `<module>.<symbol>`
7. Для функций пишет `signature="def <name>(...)"`
8. Для классов пишет `signature="class <name>"`
9. Для `ast.Call` на `ast.Name` создаёт `SymbolLinkArtifact(link_type="CALLS")`
10. Не создаёт CALLS link для более сложных вызовов типа `obj.method()`
- Это текущее ограничение реализации.

## 15. PostgresStore helper/orchestration tests

Файл: `worker/src/kb_worker/storage/postgres.py`

Полностью unit-тестировать живую SQL-интеграцию не нужно, но стоит проверить helper/orchestration contracts через mocks курсора и connection.

### `has_changed`

1. Если запись не найдена, возвращает `True`
2. Если checksum отличается, возвращает `True`
3. Если checksum совпадает, возвращает `False`

### `upsert_bundle`

1. Создаёт `index_jobs` со статусом `running`
2. Вызывает по порядку:
- `_upsert_document`
- `_replace_pages`
- `_replace_assets`
- `_replace_ocr_blocks`
- `_replace_chunks`
- `_replace_entities`
- `_replace_symbols`

3. В конце обновляет job до `done`
4. Вызывает `conn.commit()`

### `mark_failed`

1. Пишет job со статусом `failed`
2. `error_text` режется до 4000 символов
3. Вызывает `commit()`

### `_vector_literal`

1. `None` -> `None`
2. `[]` -> `None`
3. Непустой vector -> строка формата `[0.12345678,...]`

### `_ensure_file`

1. Возвращает `id` из `RETURNING`
2. Корректно вычисляет extension из `source_path`
3. Для пути без точки extension становится пустой строкой

### `_upsert_document`

1. Обновляет `bundle.document_id` значением из `RETURNING`
2. Сериализует `bundle.metadata` в JSON

### `_replace_entities`

1. Для каждого entity делает upsert в `entities`
2. Для entity с `chunk_index` создаёт запись в `chunk_entities`
3. Для entity без `chunk_index` связь с chunk не создаётся

### `_replace_symbols`

1. Перед вставкой symbols удаляет старые symbols файла
2. Вызывает `_ensure_file(...)`
3. Вставляет symbols
4. Удаляет старые `symbol_links`
5. Вставляет новые `symbol_links`

## 16. Neo4jProjectionStore

Файл: `worker/src/kb_worker/storage/neo4j_projection.py`

### Что проверять

1. `project_bundle()` ничего не делает при `enable_neo4j_projection=False`
2. При включённой проекции открывает session и вызывает `execute_write(self._project_tx, bundle)`
3. `close()` вызывает `driver.close()`

### `_project_tx`

1. Создаёт/обновляет `Document`
2. Для каждой page создаёт `Page` и `HAS_PAGE`
3. Для каждого chunk создаёт `Chunk` и `HAS_CHUNK`
4. Для chunk с `page_number` создаёт связь `Page -> Chunk`
5. Для entity создаёт `Entity`
6. Для entity с `chunk_index` создаёт `MENTIONS`
7. Для symbol создаёт `Symbol`
8. Для symbol link создаёт `CALLS`

## 17. Settings and config parsing

Файл: `worker/src/kb_worker/config.py`

### Что проверять

1. `parse_source_roots()` разбирает CSV-строку в список `Path`
2. Уже готовый список остаётся без изменений
3. `supported_extensions` содержит ключевые форматы из README

## 18. Logging helper

Файл: `worker/src/kb_worker/logging.py`

### Что проверять

1. `setup_logging("INFO")` вызывает `logging.basicConfig(...)`
2. Неизвестный уровень логирования fallback-ится в `logging.INFO`

## Критичные edge cases, которые обязательно зафиксировать

- `process_file()` не должен продолжать pipeline после `has_changed=False`
- Ошибки внутри pipeline должны конвертироваться в `mark_failed`, а не пробрасываться наружу
- OCR/image branches пока могут возвращать пустой результат, и это не должно ломать pipeline
- `follow_symlinks` сейчас не используется
- `run-forever` через `main()` может приводить к double-close
- `ETLPipeline.close()` закрывает только Neo4j projection
- `OfficePdfExtractor` и `OCRExtractor` сейчас являются заглушками, это нужно фиксировать тестами осознанно

## Минимальный порядок реализации тестов

Если писать тесты поэтапно, оптимальная последовательность такая:

1. `DocumentClassifier`
2. `Chunker`
3. `ETLPipeline.process_file`
4. `ETLPipeline._extract_into_bundle`
5. `FileScanner`
6. `MetadataEnricher`
7. `OllamaEmbedder`
8. `CodeParser`
9. `Scheduler` и `main`
10. storage helper tests

## Риски и замечания

- Тесты должны фиксировать текущие упрощения, а не ожидать "идеальный мультимодальный pipeline" из диаграмм.
- Особенно важно не перепутать архитектурно запланированное поведение и текущий код:
  - image embeddings не используются;
  - OCR почти всегда пустой;
  - office/pdf extraction stubbed;
  - entity extraction regex-based;
  - Python parser ограничен `ast`-логикой.
- Если следующим шагом потребуется код тестов, лучше сначала завести общие fixtures для `Settings`, `FileRecord`, `ETLBundle` и mock pipeline dependencies.
