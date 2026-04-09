# operation-reassurance

**Structural memory for LLM code generation.**

[![CI](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml/badge.svg)](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

LLMs are great at writing code. They're blind to the codebase they're writing into.

Every session starts fresh — no memory of what's already there, what's tested, what's instrumented, what's coupled. So you get god files, uncovered code, dark functions, and duplicate logic. Not because the model is bad. Because it can't see.

**Reassure gives it eyes.**

```
without reassure:           with reassure:
─────────────────           ──────────────────────────────────────────
"here's 900 lines,          get_symbol_map()    → 82 symbols, 400 tokens
 good luck"                 get_dark_modules()  → 13 files, zero instrumentation
                            get_blast_radius()  → "touch _loadManifest, 6 callers,
                                                   2 with no tests"
                            solid               → god file (1512 LOC, 3 concern layers)
```

Static CST/AST analysis. No runtime. No instrumentation. Same input = same output, always current.

---

## What it does

```
$ reassure ./src

  14 files  224 symbols  1 test files

╭── Test Coverage  12.0%  (27/224 symbols) ────────────────╮
│  AuthService.login         unit:2  integration:1          │
│  AuthService.resetPassword ✗ NO TESTS                     │
│  sqflite_adapter.execute   ✗ NO TESTS                     │
╰──────────────────────────────────────────────────────────╯

╭── Observability  0.0%  (0/82 instrumented) ──────────────╮
│  Dark modules (zero production instrumentation):          │
│  ✗ lib/boot/sqflite_adapter.dart                         │
│  ✗ lib/app/user_app_shell.dart                           │
│  ... 11 more                                              │
╰──────────────────────────────────────────────────────────╯

╭── SOLID Health ───────────────────────────────────────────╮
│  ✗ lib/views/dashboard_shell.dart  god file (1512 LOC)   │
│  ✗ lib/views/dashboard_shell.dart  SoC: UI + Data + Infra│
│  ✗ lib/services/auth_service.dart  god class (22 methods) │
╰──────────────────────────────────────────────────────────╯

╭── Blast Radius (vs main) ─────────────────────────────────╮
│  Changed: UserRepository.fetchUser  lib/data/repo.dart:34 │
│    DashboardShell._loadData   ✓ covered                   │
│    ProfilePage.init           ✗ DARK  ← risky             │
│    SearchBloc.query           ✗ DARK  ← risky             │
│  ⚠  2 callers affected with no test coverage              │
╰──────────────────────────────────────────────────────────╯
```

| Analyzer | What it finds |
|---|---|
| **Coverage** | Per-symbol test matrix — unit / integration / e2e / smoke / security |
| **Observability** | Functions with no logging, tracing, or metrics (excludes `debugPrint`/`print`) |
| **SOLID** | God files, god classes, SoC violations (concern mixing) |
| **Blast Radius** | Given a git diff — which symbols changed, who calls them, which callers have no tests |
| **Dead Code** | Symbols defined but never referenced *(planned)* |
| **Async Correctness** | Unawaited futures, missing error paths *(planned)* |

---

## Install

```bash
git clone https://github.com/avarga1/operation-reassurance
cd operation-reassurance
pip install -e .
```

---

## Usage

### Terminal

```bash
# Full analysis
reassure ./src

# Single analyzer
reassure ./src --only coverage
reassure ./src --only observability
reassure ./src --only solid
reassure ./src --only blast_radius          # diff vs main
reassure ./src --only blast_radius --base origin/dev

# JSON output (for CI or scripting)
reassure ./src --output json
reassure ./src --output json -o report.json
```

### GUI

```bash
# Start the backend (port 7474)
make api

# Start the frontend (port 5173, open http://localhost:5173)
make gui

# Or both at once
make dev
```

The GUI is a Vite + React app. Paste any repo path in the sidebar — it calls the FastAPI backend and renders all analyzers, including the blast radius dependency graph.

### MCP server — LLM-native

Drop `.mcp.json` in any repo and every MCP-compatible client (Claude Code, Cursor, Windsurf) gets these tools:

```json
{
  "mcpServers": {
    "reassure": {
      "command": "python3",
      "args": ["-m", "reassure.mcp.server"],
      "cwd": "/path/to/operation-reassurance",
      "env": { "PYTHONPATH": "/path/to/operation-reassurance" }
    }
  }
}
```

Or use the wrapper script for convenience:

```json
{
  "mcpServers": {
    "reassure": {
      "command": "/path/to/operation-reassurance/reassure-mcp"
    }
  }
}
```

| Tool | Description |
|---|---|
| `coverage` | Full coverage report — which symbols have no tests |
| `observability` | Which functions have zero production instrumentation |
| `solid` | God files, god classes, and SoC (concern mixing) violations |
| `get_blast_radius` | Given a base ref, which callers are affected and which have no tests |
| `get_symbol_map` | Every named symbol in the repo, file:line, filterable by language |
| `get_dark_modules` | Files where every public function is dark |
| `get_uncovered_symbols` | Public symbols with no test coverage |
| `list_analyzers` | List available analyzers |

The LLM calls these before touching your code. Knows what's covered, what's dark, what will break. Makes changes that don't regress.

---

## Configuration

Thresholds are configurable via `.reassure.toml` in the repo root (or from the GUI settings page):

```toml
[thresholds]
god_file_loc = 500          # lines of code per file
god_file_functions = 20     # functions/methods per file
god_file_classes = 5        # classes per file
god_class_methods = 15      # methods per class
blast_radius_depth = 2      # transitive caller depth

[ignore]
# Additional dirs to skip (on top of defaults)
patterns = ["generated/", "third_party/"]

[analyzers]
# Drop-in custom analyzers
custom = ["mypackage.analyzers.MyAnalyzer"]
```

---

## How it works

Uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source files into concrete syntax trees, then:

1. **Extracts symbols** — every function, method, and class with exact line ranges + metadata
2. **Extracts references** — what each file imports and calls
3. **Classifies tests** — unit vs integration vs e2e via path, import, and marker heuristics
4. **Resolves coverage** — maps source symbols to the tests that reference them
5. **Detects structural issues** — dark modules, god files, concern mixing
6. **Builds blast radius** — inverts the reference graph; given changed lines → which callers are affected × which have no tests

---

## Supported languages

Python · Rust · TypeScript · JavaScript · Dart *(more via tree-sitter grammars)*

---

## Plugin protocol

Any analyzer drops in and auto-registers as a CLI flag, MCP tool, and GUI page:

```python
from pathlib import Path
from reassure.plugin import Analyzer, AnalyzerResult
from reassure.core.repo_walker import RepoIndex

class MyAnalyzer:
    name = "my_analyzer"
    description = "Checks something interesting."

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        return AnalyzerResult(
            name=self.name,
            summary="3 issues found",
            issues=[{"file": "src/foo.py", "reason": "..."}],
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from rich.console import Console
        Console().print(result.summary)
```

Register in `.reassure.toml`:
```toml
[analyzers]
custom = ["mypackage.analyzers.MyAnalyzer"]
```

---

## Status

| Component | Status |
|---|---|
| Python / Dart symbol extraction | ✅ |
| Rust / TypeScript / JavaScript symbol extraction | ✅ (grammar loaded, extractor planned) |
| Test type classifier (unit/integration/e2e/smoke/security) | ✅ |
| Test coverage analyzer | ✅ |
| Observability analyzer | ✅ |
| SOLID / SoC analyzer (god files, god classes, concern mixing) | ✅ |
| Blast radius analyzer (change-scoped impact + coverage cross-ref) | ✅ |
| Plugin protocol | ✅ |
| MCP server (8 tools) | ✅ |
| Rich terminal renderer | ✅ |
| FastAPI backend | ✅ |
| TSX GUI (Vite + React, blast radius graph) | ✅ |
| CI (Python 3.11–3.14) | ✅ |
| Cyclomatic complexity | 🔨 planned |
| Dead code analyzer | 🔨 planned |
| Async correctness (unawaited futures) | 🔨 planned |
| CST compression (context budget optimizer) | 🔨 planned |
| PreToolUse hook (structural guardrails for LLM generation) | 🔨 planned |
| Similarity / clone detection (embedding-based) | 🔨 planned |
| Auto-refactor: split-file | 🔨 planned |

---

## Open core

The core analyzers, MCP server, CLI, GUI, and plugin protocol are MIT licensed and free forever.

The semantic memory layer — combining structural CST analysis with embeddings and LLM-generated summaries for full per-symbol context — is part of a closed platform built on top of this foundation.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labeled [`good first issue`](https://github.com/avarga1/operation-reassurance/issues?q=label%3A%22good+first+issue%22).

## License

MIT
