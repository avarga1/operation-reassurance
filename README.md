# operation-reassurance

**Structural memory for LLM code generation.**

[![CI](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml/badge.svg)](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

LLMs are great at writing code. They're blind to the codebase they're writing into.

Every session starts fresh — no memory of what's already there, what's tested, what's instrumented, what's coupled to what. So you get god files, uncovered code, dark functions, and duplicate logic. Not because the model is bad. Because it can't see.

**Reassure gives it eyes.**

```
without reassure:           with reassure:
─────────────────           ─────────────────────────────────────
"here's 900 lines,          get_symbol_map()   → 82 symbols, 400 tokens
 good luck"                 get_dark_modules() → 13 files, zero instrumentation
                            get_blast_radius() → "touch _loadManifest, 6 things break"
```

Static CST/AST analysis. No runtime. No instrumentation. Always current — unlike READMEs.

---

## What it does

```
$ reassure ./src

  14 files  224 symbols  1 test files

╭── Test Coverage  0.0%  (0/224 symbols) ──────────────────╮
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
```

| Analyzer | What it finds |
|---|---|
| **Test Coverage** | Per-symbol test matrix — unit / integration / e2e / smoke / security |
| **Observability** | Functions with no logging, tracing, or metrics (excludes `debugPrint`/`print`) |
| **Dead Code** | Symbols defined but never referenced anywhere *(coming soon)* |
| **SOLID Health** | God files, god classes, cyclomatic complexity *(coming soon)* |
| **Async Correctness** | Unawaited futures, missing error paths *(coming soon)* |

---

## MCP server — LLM-native

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

| Tool | Description |
|---|---|
| `coverage` | Full coverage report — which symbols have no tests |
| `observability` | Which functions have zero production instrumentation |
| `get_symbol_map` | Every named symbol in the repo, file:line, filterable by language |
| `get_dark_modules` | Files where every public function is dark |
| `get_uncovered_symbols` | Public symbols with no test coverage |
| `list_analyzers` | List available analyzers |

The LLM calls these before touching your code. Knows what's covered, what's dark, what's coupled. Makes changes that don't regress.

---

## How it works

Uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source files into concrete syntax trees, then:

1. **Extracts symbols** — every function, method, and class with location + metadata
2. **Extracts test references** — what each test file imports and calls
3. **Classifies test types** — unit vs integration vs e2e via path, import, and marker heuristics
4. **Resolves coverage** — maps source symbols to the tests that reference them
5. **Detects structural issues** — dark modules, uncovered symbols, god files

No test execution. No coverage.py. No instrumentation. Same input = same output, every time.

---

## Supported languages

Python · Rust · TypeScript · JavaScript · Dart *(more via tree-sitter grammars)*

---

## Install

```bash
git clone https://github.com/avarga1/operation-reassurance
cd operation-reassurance
pip install -e .
```

## Usage

```bash
# Terminal analysis
reassure ./src

# Single analyzer
reassure ./src --only coverage
reassure ./src --only observability

# JSON output (CI)
reassure ./src --output json -o report.json

# GUI dashboard
make gui

# MCP server (stdio)
python3 -m reassure.mcp.server
```

## Plugin protocol

Any analyzer can be dropped in and auto-registers as a CLI flag + MCP tool:

```python
from reassure.plugin import Analyzer, AnalyzerResult
from reassure.core.repo_walker import RepoIndex
from pathlib import Path

class MyAnalyzer:
    name = "my_analyzer"
    description = "Checks something interesting."

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        ...

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        ...
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
| Python / Rust / TS / JS / Dart symbol extraction | ✅ |
| Test type classifier (unit/integration/e2e/smoke/security) | ✅ |
| Test coverage analyzer | ✅ |
| Observability analyzer | ✅ |
| Plugin protocol | ✅ |
| MCP server (6 tools) | ✅ |
| Rich terminal renderer | ✅ |
| Streamlit GUI | ✅ |
| CI (Python 3.11–3.14) | ✅ |
| Dead code analyzer | 🔨 planned |
| SOLID / god file detector | 🔨 planned |
| Cyclomatic complexity | 🔨 planned |
| Async correctness (unawaited futures) | 🔨 planned |
| CST compression (context budget optimizer) | 🔨 planned |
| Pre/post generation hooks | 🔨 planned |
| Auto-refactor: split-file | 🔨 planned |

---

## Open core

The core analyzers, MCP server, CLI, and plugin protocol are MIT licensed and free forever.

The semantic memory layer — combining structural CST analysis with embeddings and LLM-generated summaries for full symbol context — is part of a closed platform built on top of this foundation.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labeled [`good first issue`](https://github.com/avarga1/operation-reassurance/issues?q=label%3A%22good+first+issue%22).

## License

MIT
