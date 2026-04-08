# Changelog

All notable changes to this project will be documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### In Progress
- Python symbol extractor tests (#1) — contributor: @poojakaskare
- Test coverage resolver (#3)
- Rich terminal renderer (#4)
- Streamlit GUI dashboard (#5)

---

## [0.1.0] — 2026-04-08

Initial scaffold and first working analyzers.

### Added
- Project structure: `reassure/core`, `analyzers`, `classifiers`, `output`, `gui`
- `parser.py` — language detection + tree-sitter initialization (Python, Rust, TypeScript, JavaScript)
- `symbol_map.py` — Python CST symbol extractor (functions, async functions, classes, methods, decorators, parent class tracking)
- `repo_walker.py` — repository file walker, `RepoIndex` + `FileRecord` dataclasses, test file heuristics
- `classifiers/test_type.py` — multi-signal test type classifier (unit/integration/e2e/smoke/security) via marker > path > import > fallback priority
- Analyzer stubs with full docstrings: `test_coverage`, `observability`, `dead_code`, `solid`, `metrics`
- Output stubs: `terminal.py` (rich), `json_export.py`
- `gui/app.py` — Streamlit dashboard shell
- `cli.py` — Click CLI entry point with all flags wired
- `.reassure.toml.example` — full configuration reference
- CI workflow (GitHub Actions) — test matrix Python 3.10/3.11/3.12, lint, self-analysis job
- `Makefile` — `make check`, `make test`, `make lint`, `make fix`
- 21 unit tests for test type classifier — all passing
