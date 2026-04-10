"""
Taxonomy analyzer.

Enforces file-pattern contracts — the rules that say:
  "*_page.dart is a UI scaffold, max 150 LOC, no DB imports"
  "*_repository.dart owns data access, no UI imports"

Rules are loaded from [[rules]] in .reassure.toml.
If no config is found, built-in default rulesets are applied based on
detected language/framework (Flutter/Riverpod, Flutter/BLoC, FastAPI, Axum).

Each violation includes:
  - which rule was broken
  - why (LoC limit, forbidden import, forbidden content)
  - the message to show the LLM (used by PreToolUse hook)
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.plugin import AnalyzerResult


@dataclass
class TaxonomyRule:
    pattern: str                          # glob, matched against filename
    purpose: str                          # human label ("UI scaffold — composes widgets")
    max_loc: int | None = None
    forbidden_imports: list[str] = field(default_factory=list)
    forbidden_content: list[str] = field(default_factory=list)
    message: str = ""                     # shown to LLM on violation


@dataclass
class TaxonomyViolation:
    file: Path
    rule: TaxonomyRule
    reasons: list[str]                    # ["exceeds 150 LOC (1664)", "forbidden import: sqflite"]


@dataclass
class TaxonomyReport:
    violations: list[TaxonomyViolation] = field(default_factory=list)
    rules_applied: int = 0
    files_checked: int = 0

    @property
    def has_issues(self) -> bool:
        return bool(self.violations)


# ── default rulesets ──────────────────────────────────────────────────────────

_FLUTTER_RIVERPOD_RULES: list[TaxonomyRule] = [
    TaxonomyRule(
        pattern="*_screen.dart",
        purpose="Route entry — composes widgets, wires providers",
        max_loc=150,
        forbidden_imports=["repository", "sqflite", "hive", "http", "dio", "supabase"],
        message="Screens compose widgets and read providers. Data access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_page.dart",
        purpose="Route entry — alias for screen",
        max_loc=150,
        forbidden_imports=["repository", "sqflite", "hive", "http", "dio", "supabase"],
        message="Pages compose widgets and read providers. Data access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_widget.dart",
        purpose="Reusable UI component",
        max_loc=120,
        forbidden_imports=["repository", "sqflite", "hive", "http", "dio"],
        message="Widgets are presentational. Pass data via constructor or ref.watch.",
    ),
    TaxonomyRule(
        pattern="*_provider.dart",
        purpose="Riverpod provider — state and business logic",
        max_loc=200,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart", "sqflite", "hive"],
        message="Providers hold logic, not UI. DB access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_notifier.dart",
        purpose="Riverpod Notifier — state machine",
        max_loc=200,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart", "sqflite", "hive"],
        message="Notifiers hold state logic. DB access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_repository.dart",
        purpose="Data access layer — owns all network and storage calls",
        max_loc=300,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart"],
        message="Repositories own data access. No UI imports allowed.",
    ),
    TaxonomyRule(
        pattern="*_model.dart",
        purpose="Pure data class",
        max_loc=150,
        forbidden_imports=["flutter/material.dart", "sqflite", "hive", "http", "dio"],
        message="Models are pure data. No UI or storage imports.",
    ),
]

_FLUTTER_BLOC_RULES: list[TaxonomyRule] = [
    TaxonomyRule(
        pattern="*_page.dart",
        purpose="Route entry — wires BLoC + View",
        max_loc=80,
        forbidden_imports=["repository", "sqflite", "hive", "http", "dio"],
        message="Pages wire a BLoC to a View. No logic or data access here.",
    ),
    TaxonomyRule(
        pattern="*_view.dart",
        purpose="Widget tree — reads BLoC state",
        max_loc=200,
        forbidden_imports=["repository", "sqflite", "hive", "http", "dio"],
        message="Views render BLoC state. No business logic or data access.",
    ),
    TaxonomyRule(
        pattern="*_bloc.dart",
        purpose="State machine — no UI, no direct DB",
        max_loc=300,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart", "sqflite", "hive"],
        message="Blocs manage state. DB access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_cubit.dart",
        purpose="Simplified BLoC",
        max_loc=200,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart", "sqflite", "hive"],
        message="Cubits manage state. DB access belongs in a repository.",
    ),
    TaxonomyRule(
        pattern="*_repository.dart",
        purpose="Data access layer",
        max_loc=300,
        forbidden_imports=["flutter/material.dart", "flutter/widgets.dart"],
        message="Repositories own data access. No UI imports allowed.",
    ),
    TaxonomyRule(
        pattern="*_model.dart",
        purpose="Pure data class",
        max_loc=150,
        forbidden_imports=["flutter/material.dart", "sqflite", "hive", "http", "dio"],
        message="Models are pure data. No UI or storage imports.",
    ),
]

_FASTAPI_RULES: list[TaxonomyRule] = [
    TaxonomyRule(
        pattern="*_router.py",
        purpose="HTTP handler — thin",
        max_loc=80,
        forbidden_imports=["sqlalchemy", "psycopg2", "psycopg", "asyncpg"],
        message="Routers call services. DB calls belong in a repository.",
    ),
    TaxonomyRule(
        pattern="*_service.py",
        purpose="Business logic",
        forbidden_imports=["fastapi", "httpx", "requests"],
        message="Services contain business logic. HTTP layer belongs in a router.",
    ),
    TaxonomyRule(
        pattern="*_repository.py",
        purpose="Data access only",
        forbidden_imports=["fastapi"],
        message="Repositories own data access. No HTTP framework imports.",
    ),
    TaxonomyRule(
        pattern="*_schema.py",
        purpose="Pydantic shapes — pure data",
        max_loc=150,
        forbidden_imports=["sqlalchemy", "fastapi.routing"],
        message="Schemas are pure data shapes. No DB or routing logic.",
    ),
]

_AXUM_RULES: list[TaxonomyRule] = [
    TaxonomyRule(
        pattern="*_handler.rs",
        purpose="HTTP handler — thin",
        forbidden_imports=["sqlx::query", "sqlx::pool", "Pool"],
        message="Handlers are thin. DB calls belong in a repository.",
    ),
    TaxonomyRule(
        pattern="*_service.rs",
        purpose="Business logic — no HTTP, no SQL",
        forbidden_imports=["axum::", "Request", "Response"],
        message="Services contain business logic. HTTP types belong in handlers.",
    ),
    TaxonomyRule(
        pattern="*_repository.rs",
        purpose="Data access only",
        forbidden_imports=["axum::"],
        message="Repositories own data access. No HTTP framework imports.",
    ),
]

# Map detected stack → default rules
_DEFAULT_RULESETS: dict[str, list[TaxonomyRule]] = {
    "flutter-riverpod": _FLUTTER_RIVERPOD_RULES,
    "flutter-bloc":     _FLUTTER_BLOC_RULES,
    "fastapi":          _FASTAPI_RULES,
    "axum":             _AXUM_RULES,
}


# ── analyzer ──────────────────────────────────────────────────────────────────

class TaxonomyAnalyzer:
    name = "taxonomy"
    description = (
        "Enforces file-pattern contracts — checks that *_page.dart files stay under "
        "their LoC limit and don't import DB/network packages, that repositories don't "
        "import UI packages, etc. Rules are loaded from [[rules]] in .reassure.toml, "
        "with built-in defaults for Flutter, FastAPI, and Axum."
    )

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        rules = self._load_rules(index.root)
        report = analyze_taxonomy(index, rules)

        issues = [
            {
                "file": str(v.file),
                "rule_pattern": v.rule.pattern,
                "purpose": v.rule.purpose,
                "reasons": v.reasons,
                "message": v.rule.message,
            }
            for v in report.violations
        ]

        return AnalyzerResult(
            name=self.name,
            summary=(
                f"{len(report.violations)} taxonomy violations "
                f"across {report.files_checked} files "
                f"({report.rules_applied} rules active)"
            ),
            data=report,
            issues=issues,
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from reassure.output.terminal import render_taxonomy
        render_taxonomy(result.data, root=root)

    def _load_rules(self, root: Path) -> list[TaxonomyRule]:
        config_path = self._config_path or root / ".reassure.toml"
        if config_path.exists():
            return _rules_from_toml(config_path)
        return _detect_default_rules(root)


# ── core logic ────────────────────────────────────────────────────────────────

def analyze_taxonomy(index: RepoIndex, rules: list[TaxonomyRule]) -> TaxonomyReport:
    report = TaxonomyReport(rules_applied=len(rules))
    checked: set[Path] = set()

    for file in index.source_files:
        matching = _matching_rules(file.path, rules)
        if not matching:
            continue

        checked.add(file.path)
        imports = _extract_imports(file)

        for rule in matching:
            reasons = _check_rule(file, rule, imports)
            if reasons:
                report.violations.append(TaxonomyViolation(
                    file=file.path,
                    rule=rule,
                    reasons=reasons,
                ))

    report.files_checked = len(checked)
    return report


def check_file(
    path: Path,
    proposed_content: str,
    rules: list[TaxonomyRule],
) -> list[TaxonomyViolation]:
    """
    Check a proposed file write against taxonomy rules without a full RepoIndex.
    Used by the PreToolUse hook and the `check_taxonomy` MCP tool.
    """
    matching = _matching_rules(path, rules)
    if not matching:
        return []

    loc = proposed_content.count("\n") + 1
    imports = _extract_imports_from_source(proposed_content, path.suffix)

    violations = []
    for rule in matching:
        reasons: list[str] = []

        if rule.max_loc and loc > rule.max_loc:
            reasons.append(f"exceeds {rule.max_loc} LOC ({loc} lines)")

        for forbidden in rule.forbidden_imports:
            if any(forbidden.lower() in imp.lower() for imp in imports):
                reasons.append(f"forbidden import: {forbidden}")

        for forbidden in rule.forbidden_content:
            if forbidden.lower() in proposed_content.lower():
                reasons.append(f"forbidden content: {forbidden}")

        if reasons:
            violations.append(TaxonomyViolation(file=path, rule=rule, reasons=reasons))

    return violations


# ── helpers ───────────────────────────────────────────────────────────────────

def _matching_rules(path: Path, rules: list[TaxonomyRule]) -> list[TaxonomyRule]:
    """Return all rules whose pattern matches the file's name."""
    name = path.name
    return [r for r in rules if fnmatch.fnmatch(name, r.pattern)]


def _check_rule(
    file: FileRecord,
    rule: TaxonomyRule,
    imports: list[str],
) -> list[str]:
    reasons: list[str] = []

    if rule.max_loc and file.loc > rule.max_loc:
        reasons.append(f"exceeds {rule.max_loc} LOC ({file.loc} lines)")

    for forbidden in rule.forbidden_imports:
        if any(forbidden.lower() in imp.lower() for imp in imports):
            reasons.append(f"forbidden import: {forbidden}")

    if rule.forbidden_content and file.source:
        for forbidden in rule.forbidden_content:
            if forbidden.lower() in file.source.lower():
                reasons.append(f"forbidden content: {forbidden}")

    return reasons


def _extract_imports(file: FileRecord) -> list[str]:
    if file.imports:
        return file.imports
    if file.source:
        return _extract_imports_from_source(file.source, file.path.suffix)
    return []


def _extract_imports_from_source(source: str, suffix: str) -> list[str]:
    """
    Extract import/use statements from source text.
    Returns a flat list of import strings (the raw import line content).
    """
    imports: list[str] = []
    suffix = suffix.lower()

    if suffix == ".dart":
        # import 'package:sqflite/sqflite.dart';
        # import 'package:flutter/material.dart';
        for m in re.finditer(r"""import\s+['"]([^'"]+)['"]""", source):
            imports.append(m.group(1))

    elif suffix == ".py":
        # import fastapi
        # from sqlalchemy import ...
        for m in re.finditer(r"""^(?:import|from)\s+([\w.]+)""", source, re.MULTILINE):
            imports.append(m.group(1))

    elif suffix == ".rs":
        # use axum::Router;
        # use sqlx::Pool;
        for m in re.finditer(r"""^use\s+([\w:]+)""", source, re.MULTILINE):
            imports.append(m.group(1))

    elif suffix in (".ts", ".tsx", ".js", ".jsx"):
        # import { x } from 'react'
        # import x from "next/router"
        for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", source):
            imports.append(m.group(1))

    return imports


def _rules_from_toml(path: Path) -> list[TaxonomyRule]:
    """Parse [[rules]] entries from a .reassure.toml file."""
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        return []

    taxonomy = cfg.get("taxonomy", {})
    if not taxonomy.get("enabled", True):
        return []

    raw_rules: list[dict[str, Any]] = cfg.get("rules", [])
    result: list[TaxonomyRule] = []

    for r in raw_rules:
        if "pattern" not in r:
            continue
        result.append(TaxonomyRule(
            pattern=r["pattern"],
            purpose=r.get("purpose", ""),
            max_loc=r.get("max_loc"),
            forbidden_imports=r.get("forbidden_imports", []),
            forbidden_content=r.get("forbidden_content", []),
            message=r.get("message", ""),
        ))

    # If no [[rules]] defined but stack is set, fall back to defaults
    if not result:
        stack = taxonomy.get("stack", "")
        defaults = _stack_to_default_rules(stack)
        result.extend(defaults)

    return result


def _detect_default_rules(root: Path) -> list[TaxonomyRule]:
    """
    Detect the project stack without a config file and return the matching default ruleset.
    Walks up from root to find config files (handles walking into lib/, src/, etc.).
    Falls back to empty list if stack is unknown.
    """
    # Sniff pubspec.yaml for Flutter — search up the tree and also one level down
    pubspec = _find_upward(root, "pubspec.yaml")
    if not pubspec:
        candidates = list(root.glob("*/pubspec.yaml"))
        pubspec = candidates[0] if candidates else None

    if pubspec and pubspec.exists():
        text = pubspec.read_text()
        if "flutter_riverpod" in text or "riverpod" in text:
            return _FLUTTER_RIVERPOD_RULES
        if "flutter_bloc" in text:
            return _FLUTTER_BLOC_RULES

    # Sniff pyproject.toml for FastAPI
    pyproject = _find_upward(root, "pyproject.toml")
    candidates = [c for c in [pyproject, *root.glob("*/pyproject.toml")] if c]
    for candidate in candidates:
        if candidate.exists():
            try:
                with open(candidate, "rb") as f:
                    data = tomllib.load(f)
                deps = set(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
                if "fastapi" in {d.lower() for d in deps}:
                    return _FASTAPI_RULES
            except Exception:
                pass

    # Sniff Cargo.toml for Axum
    cargo = _find_upward(root, "Cargo.toml")
    candidates = [c for c in [cargo, *root.glob("*/Cargo.toml")] if c]
    for candidate in candidates:
        if candidate.exists():
            try:
                with open(candidate, "rb") as f:
                    data = tomllib.load(f)
                if "axum" in data.get("dependencies", {}):
                    return _AXUM_RULES
            except Exception:
                pass

    return []


def _find_upward(start: Path, filename: str, max_levels: int = 6) -> Path | None:
    """Walk up the directory tree looking for a file by name."""
    current = start if start.is_dir() else start.parent
    for _ in range(max_levels):
        candidate = current / filename
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _stack_to_default_rules(stack: str) -> list[TaxonomyRule]:
    for key, rules in _DEFAULT_RULESETS.items():
        if key in stack:
            return rules
    return []
