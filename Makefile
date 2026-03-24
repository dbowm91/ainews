.PHONY: install dev stop test test-cov lint docker-build docker-up docker-down backup clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install dependencies
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt
	@test -f .env || (cp .env.example .env && echo "Created .env — edit it before running")

dev: ## Start local development (Flask + Celery)
	bash scripts/dev.sh

stop: ## Stop local development services
	bash scripts/dev.sh stop

test: ## Run tests
	bash scripts/test.sh

test-cov: ## Run tests with coverage
	bash scripts/test.sh --cov

lint: ## Run linter (ruff)
	.venv/bin/ruff check . --exclude .venv

lint-fix: ## Run linter with auto-fix
	.venv/bin/ruff check . --exclude .venv --fix

docker-build: ## Build Docker image
	docker compose build

docker-up: ## Start with Docker Compose
	docker compose up -d

docker-down: ## Stop Docker Compose
	docker compose down

docker-logs: ## View Docker logs
	docker compose logs -f

backup: ## Backup database
	bash scripts/backup.sh

clean: ## Remove generated files
	rm -rf __pycache__ .pytest_cache .ruff_cache htmlcov .pids instance/*.db instance/*.db-* *.pyc
