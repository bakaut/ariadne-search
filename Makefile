SHELL := /bin/bash

.PHONY: up infra app down logs ps pull-model reindex force-upload

up:
	docker compose up -d --build

infra:
	docker compose up -d postgres neo4j ollama
	docker compose run --rm neo4j-init

app:
	docker compose up -d --build api worker

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

pull-model:
	docker compose exec ollama ollama pull $${KB_TEXT_EMBEDDING_MODEL:-embeddinggemma}

reindex:
	docker compose run --rm worker run-once

force-upload:
	./scripts/force-upload-knowledge.sh
