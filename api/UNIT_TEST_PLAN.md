# Unit Test Plan for API

## Scope

Этот документ описывает unit-тесты для сервиса `api/` как search orchestrator.

Под "api worker" в текущем репозитории разумно понимать компонент `api/src/kb_api`, потому что отдельный `worker/` здесь отвечает за ETL/indexing, а не за HTTP/search orchestration.

## Архитектурный контекст

После чтения `arch/01-architecture-overview-v2-multimodal.puml`, `arch/04-search-sequence-v2-multimodal.puml` и текущей реализации `api/src/kb_api` картина такая:

- `api` является orchestration layer над PostgreSQL, Neo4j и Ollama.
- Входной запрос проходит через `QueryClassifier`, который строит `SearchPlan`.
- `SearchService` вызывает нужные retrieval branches: `exact`, `lexical`, `code`, `ocr`, `semantic`.
- Результаты нормализуются в `SearchHit`, затем merge/dedupe, optional graph enrichment и rerank.
- `FastAPI`-роуты поверх этого слоя почти не содержат бизнес-логики.

Важно:

- Архитектурно в диаграммах есть `image` branch.
- В текущем коде `QueryClassifier` умеет выставлять `plan.image=True`.
- Но `SearchService.search()` не исполняет image retrieval branch вообще.
- Это должно быть явно отражено в тест-плане как текущий gap, а не как баг в тестах.

## Цель unit-тестов

- Проверить, что orchestration-логика API стабильна и не ломает search pipeline.
- Зафиксировать текущий контракт поведения до интеграционных тестов с PostgreSQL, Neo4j и Ollama.
- Максимально изолировать внешние зависимости через mocks/stubs.

## Out of Scope

- Реальные запросы в PostgreSQL, Neo4j, Ollama.
- Полноценные e2e tests через docker-compose.
- Проверка SQL корректности на живой БД.
- Тесты ETL-воркера из `worker/`.

## Предлагаемая структура тестов

- `tests/test_query_classifier.py`
- `tests/test_search_service.py`
- `tests/test_postgres_store_helpers.py`
- `tests/test_embedder.py`
- `tests/test_dependencies_and_routers.py`
- `tests/test_app.py`

## Общие test doubles

Нужны лёгкие stubs/mocks для:

- `PostgresSearchStore`
- `GraphContextStore`
- `QueryEmbedder`
- `QueryClassifier`
- `httpx.Client`
- `subprocess.run`

Базовый подход:

- Unit-тесты `SearchService` не должны создавать реальные store/embedder/graph clients.
- После создания `SearchService` зависимости лучше подменять mock-объектами.
- Для тестов `create_app()` и роутов достаточно подмены `app.state.search_service`.

## 1. QueryClassifier

Файл: `api/src/kb_api/services/query_classifier.py`

### Что проверять

- корректное включение веток `exact`, `lexical`, `semantic`, `ocr`, `code`, `image`, `graph`;
- корректные причины в `reasons`;
- уважение user flags из `SearchRequest`;
- уважение feature flags из `Settings`.

### Набор кейсов

1. Базовый текстовый запрос
- Вход: обычный однословный запрос без path/regex/code/OCR hints.
- Ожидание: `lexical=True`, остальные optional branches выключены, `reasons` содержит fallback-причину.

2. Multi-word semantic query
- Вход: запрос из двух и более слов.
- При `enable_embeddings=True` и `include_semantic=True` ожидается `semantic=True`.
- При `include_semantic=False` или `enable_embeddings=False` ожидается `semantic=False`.

3. Exact search по path-like query
- Вход: строка с `/`, `\` или именем файла вида `main.py`.
- При включённом feature flag ожидается `exact=True`.

4. Exact search по regex-like query
- Вход: запрос с `[]() * + ? |`.
- Ожидание: `exact=True` только если `include_exact=True` и `enable_exact_search=True`.

5. Code query
- Вход: `find function build_parser`, `dockerfile`, `module`, `.py`.
- Ожидание: `code=True`.

6. OCR query
- Вход: `scan`, `scanned`, `ocr`, `pdf`, `slide`, `screenshot`.
- Ожидание: `ocr=True`.

7. Image query
- Вход: `diagram`, `schema`, `picture`.
- При `include_image=True` и `enable_image_search=True` ожидается `image=True`.
- При отключённом feature flag ожидается `image=False`.

8. Graph context flag
- Ожидание: `graph=True` только если одновременно включены `include_graph_context` и `enable_graph_context`.

9. Комбинированный запрос
- Пример: `find function in src/main.py screenshot`.
- Ожидание: может одновременно включить `exact`, `code`, `ocr`, `semantic`, `graph`.
- Проверить, что `lexical=True` всегда.

10. Приоритет не нужен, только flags
- Зафиксировать, что классификатор не выключает `lexical`, даже если включены все остальные ветки.

## 2. SearchService.search

Файл: `api/src/kb_api/services/search_service.py`

Это главный unit-test surface.

### Что проверять

- правильный вызов retrieval branches по `SearchPlan`;
- корректный `top_k` c учётом `settings.max_top_k`;
- корректное поведение semantic branch;
- merge/dedupe/rerank;
- безопасную деградацию graph enrichment;
- корректную форму `SearchResponse`.

### Набор кейсов

1. Запускаются только ветки из плана
- Подменить `classifier.classify()` фиксированным планом.
- Проверить, что вызываются только соответствующие store methods.
- Например, при плане только `lexical=True` должен вызываться только `fts_search`.

2. `top_k` ограничивается `settings.max_top_k`
- Вход: `request.top_k > settings.max_top_k`.
- Ожидание: во все store calls идёт урезанное значение.

3. Filters пробрасываются в store
- Проверить, что `request.filters.model_dump()` передаётся в `fts_search`, `code_search`, `ocr_search`, `semantic_search`.

4. Semantic branch вызывает embedder
- При `plan.semantic=True` должен вызываться `embed_query`.
- Если embedder вернул embedding, вызывается `semantic_search`.

5. Semantic branch пропускается, если embedding отсутствует
- `embed_query()` возвращает `None`.
- Ожидание: `semantic_search()` не вызывается, исключения нет.

6. Exact branch не требует filters
- Проверить, что `exact_search()` вызывается только с `query` и `top_k`.

7. Graph enrichment включается только если `plan.graph=True` и есть merged hits
- Если hits пустые, `related_entities_by_source_path()` не должен вызываться.
- Если `plan.graph=False`, graph store не должен вызываться.

8. Ошибка graph enrichment не ломает search
- `related_entities_by_source_path()` бросает exception.
- Ожидание: `search()` возвращает результаты, а не падает.

9. `SearchResponse.total`
- Зафиксировать текущее поведение: `total == len(ranked)`, то есть число уже после rerank/top_k, а не общее число сырых совпадений.

10. Image plan пока не влияет на выполнение
- Если классификатор вернул `image=True`, `search()` не должен падать.
- Но никакая image-ветка не выполняется, потому что её нет в `SearchService`.
- Этот тест фиксирует текущую реализацию и поможет заметить изменение поведения позже.

## 3. SearchService._adapt_hits

### Что проверять

1. Channel boost применяется корректно
- `score` из raw row умножается на `CHANNEL_BOOSTS[channel]`.

2. Пустой или отсутствующий score
- При `score=None` итоговый score должен стать `0.0`.

3. Нормализация snippet
- `snippet.strip()` применяется.
- Слишком длинный snippet обрезается до 900 символов плюс многоточие.

4. Заполнение optional fields
- `title`, `source_type`, `page_number`, `chunk_index`, `symbol_name`, `symbol_kind`, `heading`, `language` корректно переносятся.

5. Значения по умолчанию
- Если `hit_kind` отсутствует, используется `"unknown"`.
- Если `source_path` отсутствует, подставляется пустая строка.
- `metadata` всегда создаётся как новый пустой dict.

## 4. SearchService._merge_hits

### Что проверять

1. Merge без дубликатов
- Если ключи различны, результаты сохраняются по score descending.

2. Dedupe по symbol key
- Два `symbol` hit с одинаковым `source_path`, `symbol_name`, `symbol_kind` должны схлопнуться в один.

3. Dedupe по chunk key
- Два chunk hit с одинаковым `source_path` и `chunk_index` должны схлопнуться.

4. Dedupe по page key
- Два page/ocr hit с одинаковым `source_path`, `page_number`, `hit_kind` должны схлопнуться.

5. Generic dedupe key
- Если нет `symbol_name`, `chunk_index`, `page_number`, используется generic key по `source_path`, `hit_kind`, префиксу snippet.

6. При коллизии сохраняется лучший score
- Если duplicate hit имеет больший score, итоговый объект получает больший score и channel этого hit.

7. Сохраняется список каналов
- При merge в `metadata["channels"]` должен копиться набор каналов без дублей.

8. Сохраняется более длинный snippet
- При дубликатах итоговый hit должен содержать более содержательный snippet.

9. Итог режется по `top_k`
- После merge возвращается не больше `top_k` элементов.

## 5. SearchService._apply_graph_context

### Что проверять

1. В graph store уходят только уникальные непустые `source_path`
- И только для первых 20 hit.

2. `related_entities` заполняются по `source_path`
- Для hit без записей должен остаться пустой список.

3. Score boost ограничен сверху
- `0.05 * len(entities)` применяется, но максимум `0.15`.

4. Ошибка graph store безопасно гасится
- Метод не должен бросать exception наружу.

## 6. SearchService._rerank

### Что проверять

1. Основная сортировка по score
- Более высокий score выигрывает.

2. Exact channel имеет tie-break преимущество
- При равном score hit с `channel == "exact"` должен быть выше.

3. Symbol hits имеют tie-break преимущество
- При равном score hit с `symbol_name` должен быть выше.

4. Related entities участвуют в tie-break
- При прочих равных hit с большим числом `related_entities` должен быть выше.

5. Итог ограничивается `top_k`

## 7. SearchService._dedupe_key

### Что проверять

1. Формат key для symbol hit
2. Формат key для chunk hit
3. Формат key для page hit
4. Формат generic key
5. Использование первых 120 символов snippet в generic key

## 8. SearchService.readiness и close

### Что проверять

1. `readiness()` при включённом graph context
- Возвращает `postgres=self.store.ping()` и `neo4j=self.graph.ping()`.

2. `readiness()` при выключённом graph context
- Возвращает `neo4j=True` без вызова `graph.ping()`.

3. `close()` закрывает `graph` и `embedder`
- Проверить вызовы `close()`.

4. `close()` не закрывает `store`
- Это текущее поведение, его стоит зафиксировать отдельным тестом.

## 9. QueryEmbedder

Файл: `api/src/kb_api/services/embedder.py`

### Что проверять

1. При `enable_embeddings=False` метод возвращает `None` и не делает HTTP call.

2. Корректный POST в Ollama
- Проверить URL `/api/embeddings` и payload с `model` и `prompt`.

3. Успешный ответ с embedding list
- Возвращается список `float`.

4. Некорректный ответ без embedding
- Возвращается `None`.

5. `close()` вызывает `client.close()`.

6. HTTP status error не проглатывается
- `raise_for_status()` должен пробрасывать exception наружу.

## 10. PostgresSearchStore helper methods

Файл: `api/src/kb_api/storage/postgres.py`

Здесь unit-тесты стоит держать только на pure/helper logic, без реального PostgreSQL.

### `_document_filters`

1. Без фильтров возвращает пустой SQL и пустые params.
2. `source_types` формирует `ANY(%(source_types)s)`.
3. `path_prefixes` формируют OR-цепочку с отдельными параметрами.
4. `languages` формируют `coalesce(d.language, '') = ANY(...)`.
5. Все фильтры можно комбинировать одновременно.

### `_vector_literal`

1. Формирует pgvector literal в формате `[0.12345678,...]`.
2. Значения округляются до 8 знаков после запятой.

### `_parse_rg_line`

1. Корректный формат `path:line:snippet`.
2. Некорректный line number.
3. Строка без трёх частей.
4. Snippet очищается через `strip()`.

### `exact_search`

Только через mocks:

1. При `enable_exact_search=False` сразу возвращает пустой список.
2. Несуществующий `source_root` пропускается.
3. При `FileNotFoundError` от `rg` возвращается пустой список.
4. При `returncode` 0 парсит stdout в hits.
5. При `returncode` 1 корректно возвращает пустой или частичный результат без ошибки.
6. При `returncode` не из `(0, 1)` логирует warning и продолжает следующий root.
7. Итог режется по `top_k`.

## 11. GraphContextStore helper behavior

Файл: `api/src/kb_api/storage/neo4j_graph.py`

Без реального Neo4j.

### Что проверять

1. `related_entities_by_source_path([])` возвращает `{}` и не открывает session.
2. `ping()` возвращает `True`, если query вернула `1`.
3. `ping()` возвращает `False`, если драйвер бросил exception.
4. `related_entities_by_source_path()` преобразует rows в `dict[str, list[str]]`.
5. Пустой `entities` превращается в пустой список.
6. `close()` вызывает `driver.close()`.

## 12. FastAPI glue: dependencies, routers, app

### `dependencies.py`

1. `get_search_service()` возвращает `request.app.state.search_service`.

### `routers/health.py`

1. `GET /health/live` возвращает `{"status": "ok"}`.
2. `GET /health/ready` делегирует в `search_service.readiness()`.

### `routers/search.py`

1. `POST /search` делегирует в `search_service.search(request)`.
2. Response model сериализует `SearchResponse` без потерь.

### `app.py`

1. `create_app()` регистрирует `health_router` и `search_router`.
2. В lifespan создаётся `SearchService` и кладётся в `app.state.search_service`.
3. При завершении lifespan вызывается `service.close()`.
4. `setup_logging()` вызывается с `cfg.log_level`.

## Критичные edge cases, которые обязательно зафиксировать

- `search()` не должен падать, если graph enrichment недоступен.
- `search()` не должен вызывать semantic storage без embedding.
- `QueryClassifier` должен уважать feature flags, а не только содержимое query.
- Dedupe не должен терять информацию о каналах.
- Exact results не должны зависеть от filters.
- Текущее отсутствие image retrieval branch должно быть зафиксировано осознанно.

## Минимальный порядок реализации тестов

Если писать тесты поэтапно, оптимальная последовательность такая:

1. `QueryClassifier`
2. `SearchService.search`
3. `SearchService` helper methods
4. `QueryEmbedder`
5. `PostgresSearchStore` pure helpers
6. `FastAPI glue`

## Риски и замечания

- Часть текущего поведения может быть спорной, но тестами его лучше сначала зафиксировать, а потом менять осознанно.
- Особенно это относится к `SearchResponse.total`, отсутствию image execution branch и тому, что `close()` не трогает `PostgresSearchStore`.
- Если следующим шагом потребуется уже код тестов, лучше сначала создать базовые fixtures для `Settings`, `SearchHit` и stub-services, чтобы не размножать mocks вручную в каждом файле.
