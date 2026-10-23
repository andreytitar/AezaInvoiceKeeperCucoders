COMPOSE ?= docker compose


.PHONY: up up-mail down logs test seed openapi frontend-types ps restart clean

up:            ## Собрать и запустить (app, worker, db)
	$(COMPOSE) up --build -d
	@echo "Панель: http://localhost:$${APP_PORT:-8000}   Swagger: http://localhost:$${APP_PORT:-8000}/api/v1/docs"

down:          ## Остановить (данные сохраняются)
	$(COMPOSE) down

up-mail:       ## То же + Mailpit (http://localhost:8025); в .env SMTP_HOST=mailpit SMTP_PORT=1025 SMTP_SECURITY=none
	$(COMPOSE) --profile demo-mail up --build -d

logs:
	$(COMPOSE) logs -f app worker

ps:
	$(COMPOSE) ps

test:          ## Все тесты бэкенда на реальном PostgreSQL
	$(COMPOSE) --profile test build tests
	$(COMPOSE) --profile test run --rm tests

seed:          ## Идемпотентный сид демо-данных
	$(COMPOSE) exec app python -m app.seed

openapi:       ## Сгенерировать openapi/openapi.yml из кода
	$(COMPOSE) --profile test run --rm tests python -m app.openapi_dump /openapi/openapi.yml

frontend-types: ## TS-типы клиента из openapi.yml
	cd frontend && npx openapi-typescript ../openapi/openapi.yml -o src/api/schema.d.ts

clean:         ## Остановить и УДАЛИТЬ данные
	$(COMPOSE) down -v
