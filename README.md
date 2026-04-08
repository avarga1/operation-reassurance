# operation-reassurance

**Repo health observatory. CST/AST-powered, no runtime required.**

[![CI](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml/badge.svg)](https://github.com/avarga1/operation-reassurance/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/avarga1/operation-reassurance/branch/main/graph/badge.svg)](https://codecov.io/gh/avarga1/operation-reassurance)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Static analysis tool that tells you the actual health of your codebase without running a single test.

```
$ reassure ./src

Test Coverage
  AuthService.login         unit:2  integration:1  e2e:0
  AuthService.resetPassword unit:0  integration:0  e2e:0   ⚠ NO TESTS
  UserController.delete     unit:0  integration:0  e2e:0   ⚠ NO TESTS

Observability
  db/queries.py             ← entire module has zero logging or tracing  ⚠

Dead Code
  utils/legacy.py::parse_v1    never referenced anywhere  (high confidence)

SOLID Health
  api/routes.py             503 LOC, 24 functions  ⚠ GOD FILE
  UserService               18 methods             ⚠ GOD CLASS

Coverage: 4/6 symbols (66%)  |  2 god files  |  1 dead symbol
```

---

## What it analyzes

| Analyzer | What it finds |
|---|---|
| **Test Coverage** | Per-symbol test matrix — unit / integration / e2e / smoke / security |
| **Observability** | Functions with no logging, tracing, or metrics instrumentation |
| **Dead Code** | Symbols defined but never referenced anywhere in the repo |
| **SOLID Health** | God files, god classes, god functions, circular imports |
| **Metrics** | LOC, complexity, churn hotspots (git-aware) |

## How it works

Uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source and test files into concrete syntax trees, then:

1. **Extracts symbols** — every function, method, and class with location + metadata
2. **Extracts test references** — what each test file imports and calls
3. **Classifies test types** — unit vs integration vs e2e via path, import, and marker heuristics
4. **Resolves coverage** — maps source symbols to the tests that reference them
5. **Detects structural issues** — god files, dead code, dark modules

No test execution required. No coverage.py. No instrumentation.

## Supported languages

Python · Rust · TypeScript · JavaScript · Dart *(more via tree-sitter grammars)*

## Install

```bash
pip install operation-reassurance
```

Or from source:

```bash
git clone https://github.com/avarga1/operation-reassurance
cd operation-reassurance
poetry install
```

## Usage

```bash
# Full analysis
reassure ./src

# Single analyzer
reassure ./src --only coverage
reassure ./src --only solid

# JSON output (for CI)
reassure ./src --output json -o report.json

# Streamlit dashboard
streamlit run reassure/gui/app.py
```

## Configuration

Copy `.reassure.toml.example` to `.reassure.toml` in your repo root:

```toml
[thresholds]
god_file_loc = 500
god_class_methods = 15
max_cyclomatic_complexity = 10

[test_types]
integration = ["integration", "test_integration"]
e2e = ["e2e", "playwright"]
```

## Status

Early development. Core analyzers are being built out. Contributions welcome.

| Component | Status |
|---|---|
| Parser / language detection | ✅ |
| Repo walker | ✅ |
| Python symbol extraction | 🔨 in progress |
| Test type classifier | 🔨 in progress |
| Test coverage analyzer | 📋 planned |
| Observability analyzer | 📋 planned |
| Dead code analyzer | 📋 planned |
| SOLID analyzer | 📋 planned |
| Terminal renderer | 📋 planned |
| Streamlit GUI | 📋 planned |

## License

MIT
