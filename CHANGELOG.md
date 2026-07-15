# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Release workflow (`.github/workflows/release.yml`) for building platform-specific tarballs and creating GitHub Releases
- Installer shell tests (`tests/test_install.sh`) — 74 tests, 119 assertions covering argument parsing, platform detection, path computation, checksum verification, metadata writing, and input validation
- Install metadata schema alignment: installer now writes `install_type` field (matching `ainews_config.paths` expectations)

### Changed
- Updated release checklist with release workflow and installer test validation steps
- Updated AGENTS.md with release workflow architecture and installer test documentation

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
