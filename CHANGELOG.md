# Changelog
All notable changes are listed here. Format: Keep a Changelog, Semantic Versioning.

## [0.1.0] - Phase 1 - 2026-10-24
### Added
- **Core Daemon (`nexusd`)**:
  - Modular configuration loader (`nexusd/config.py`) supporting `config/nexus.yaml` and `NEXUS_*` environment overrides.
  - Failover LLM Router (`nexusd/router.py`) supporting local endpoints (Ollama/llama.cpp HTTP) and cloud providers (OpenAI, Anthropic) with zero-key exposure via `NEXUS_API_KEY`.
  - Append-only structured JSON-lines audit logger (`nexusd/audit.py`) writing to `logs/audit.log`.
  - Lightweight Flask HTTP API (`nexusd/api.py`) exposing `POST /intent`, `GET /status`, and `GET /audit`.
  - POSIX signal & graceful shutdown daemon runner (`nexusd/main.py`).
- **Natural Language CLI (`cli/nexus.py`)**:
  - Interactive REPL terminal prompt (`nexus> `).
  - One-shot execution flag (`--once "<intent>"`).
  - Model preference flags (`--local`, `--cloud`).
  - Daemon health check flag (`--status`).
- **Installation Scripts**:
  - `install/install-termux.sh`: Automated venv & dependency setup for Android Termux (proot-distro Debian ARM64).
  - `install/install-desktop.sh`: Automated venv & dependency setup for Debian/Ubuntu/Fedora/Arch Linux desktops.
- **Phase 2 Placeholders**:
  - Clean modular placeholders with strict TODO docstrings for `nexusd/tools/` (`files.py`, `apps.py`, `network.py`, `packages.py`).
  - Permission Engine stub (`nexusd/permissions/engine.py`).
  - Persistent SQLite Memory Store stub (`nexusd/memory/store.py`).
  - Phase 2 execution hook in `nexusd/api.py`.
- **Test Suite (`tests/`)**:
  - Pytest unit tests for router fallback, failover, missing key handling, and Anthropic formatting (`tests/test_router.py`).
  - Integration tests for REST endpoints and request validation (`tests/test_api.py`).

## [Unreleased]
### Added
- Initial project structure and documentation.
