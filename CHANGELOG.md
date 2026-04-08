# Changelog

All notable changes to this project will be documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- MCP server — expose analyzers as LLM-callable tools (#7)
- Plugin protocol — extensible analyzer interface (#8)
- Next.js + shadcn/ui frontend — replace Streamlit (#9)
- Python symbol extractor tests (#1) — contributor: @poojakaskare

---

## [0.2.0] — 2026-04-08

### Added
- Dart support — tree-sitter-dart grammar, full class/method/function extractor with async detection
- Observability analyzer — detects dark functions and modules (zero production instrumentation); excludes `debugPrint`/`print` as dev-only; configurable per-language patterns for OTel, Sentry, Firebase, `package:logging`, structlog, tracing macros
- Rich terminal renderer — `render_coverage` and `render_observability` with color-coded tables, relative paths, dark module panels
- CLI wired end-to-end — `python3 cli.py <path>` runs coverage + observability by default; `--only` flag for single analyzers; `--show-passed` flag
- Streamlit GUI dashboard — overview metrics, language bar chart, coverage table with toggles, observability gaps with expandable dark function list
- `make gui` target
- Flutter/Dart generated dirs added to default ignore list (`.dart_tool`, `ephemeral`)

### Fixed
- Byte vs character offset bug in `_node_text` — multi-byte Unicode in source files (e.g. em dash in docstrings) caused garbled symbol names and reference extraction failures

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
