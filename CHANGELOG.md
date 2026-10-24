# Changelog
All notable changes are listed here. Format: Keep a Changelog, Semantic Versioning.

## [0.2.0] - Phase 2 - 2026-10-24
### Added
- **Security & Permission Engine (`nexusd/permissions/`)**:
  - Three-tier authorization policy engine (`engine.py`) with `allow`, `confirm`, and `deny` levels.
  - Policy configuration file (`config/policy.yaml`) supporting default fallback and wildcard prefixes (e.g. `network.*`).
  - Strict parameter security guard intercepting directory traversal attacks (`..`), sensitive system file access (`/etc/shadow`, `/boot`, etc.), and destructive commands (`mkfs`, `format`, `rm -rf /`).
  - Dynamic rule configuration and policy introspection methods.
- **Tools Execution Layer (`nexusd/tools/`)**:
  - Central tool registry and dispatcher (`__init__.py`) exposing structured tool catalog and unified execution.
  - `files.py`: Read, write, list, search, move, delete, and zip directories with path sandboxing and byte bounds.
  - `apps.py`: Platform-aware app launcher, process termination, and running process inspection (supporting Android Termux and desktop Linux).
  - `network.py`: Socket connectivity checker, local IP info, stream-safe download with file size limits, and system notification dispatch.
  - `packages.py`: Package query, installation, and repository update across `apt`, `pkg`, `pacman`, and `dnf` with strict package name regex sanitization.
- **Persistent SQLite Memory Store (`nexusd/memory/`)**:
  - SQLite persistence store (`store.py`) at `nexusd/memory/nexus.db`.
  - Facts key-value store with category grouping for user preferences and device profile.
  - Conversational history recording intent, generated plan, tool invocations, provider, and execution outcome.
  - Lightweight, dependency-free semantic and keyword relevance search.
- **REST API (`nexusd/api.py`)**:
  - New endpoints: `GET /tools`, `GET /permissions`, `POST /permissions/check`, `POST /tool/execute`.
  - Memory endpoints: `GET /memory/facts`, `POST /memory/facts`, `DELETE /memory/facts/<key>`, `GET /memory/search`, `GET /memory/history`.
  - Tool execution hook in `POST /intent` with automatic structured tool call extraction, confirmation gating, and audit logging.
- **Natural Language CLI Terminal (`cli/nexus.py`)**:
  - Added `--tools` flag to inspect all registered tools.
  - Added `--facts` flag to view stored context and user preferences.
  - Added interactive security guard prompt for actions requiring confirmation (`[y/N]`).
- **Test Suite (`tests/`)**:
  - Added comprehensive test suites: `test_permissions.py`, `test_tools.py`, `test_memory.py`, and `test_api_phase2.py` (total 49 tests passing).

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
