# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-05-06

### Added

- Initial release
- AI-powered news aggregation and newsletter platform
- RSS source ingestion and article discovery
- LLM-powered pipeline: select → research → write → edit
- Configurable newsletter generation with multiple LLM providers (Ollama, OpenAI, Anthropic, Google Gemini)
- Admin dashboard with subscriber management
- Public newsletter subscription and archive
- Celery task queue for asynchronous processing
- SQLite WAL mode database with Alembic migrations
- Security headers via Flask-Talisman
- Rate limiting via Flask-Limiter with Redis backend
- Docker and bare-metal deployment options
- Comprehensive documentation (quickstart, deployment, security, configuration, development)
- CI/CD pipeline with linting, testing, and Docker Hub deployment
