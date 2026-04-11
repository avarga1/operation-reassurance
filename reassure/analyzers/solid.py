"""
SOLID / SoC health analyzer.

Detects structural code health issues using CST metrics:

  - God files:    too many LOC, functions, or classes in one file
  - God classes:  too many methods, likely violating SRP
  - God functions: high cyclomatic complexity (too many decision branches)
  - SoC violations: concern mixing — Widget + Repository co-located,
                    data-layer imports in view files, etc.

All thresholds are configurable. Circular import detection is planned
(see issue #23 — requires full import graph resolution).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult

# ── Archetypes — class name suffix → concern layer ───────────────────────────

_DART_ARCHETYPES: dict[str, str] = {
    "Widget": "ui",
    "Page": "ui",
    "Screen": "ui",
    "View": "ui",
    "Shell": "ui",
    "Dialog": "ui",
    "Sheet": "ui",
    "Bloc": "state",
    "Cubit": "state",
    "Notifier": "state",
    "Controller": "state",
    "Provider": "state",
    "ViewModel": "state",
    "Repository": "data",
    "DataSource": "data",
    "Adapter": "data",
    "Dao": "data",
    "Service": "service",
    "UseCase": "service",
    "Interactor": "service",
    "Client": "infra",
    "Api": "infra",
    "Cache": "infra",
}

_DART_DATA_IMPORTS = {"dio", "sqflite", "hive", "drift", "isar", "http", "chopper"}
_FLUTTER_UI_BASE = {"StatelessWidget", "StatefulWidget", "State", "HookWidget"}

# ── Branch keywords by language — used for cyclomatic complexity ──────────────
# Cyclomatic complexity = 1 + count of decision points in a function body.
# We use regex over source text (fast, language-agnostic enough for our purposes).
_BRANCH_PATTERNS: dict[str, re.Pattern[str]] = {
    "dart": re.compile(
        r"\b(if|else if|for|while|do|switch|case|catch|\?\?|&&|\|\|)\b|"
        r"\?(?!\?)[^:]*:",  # ternary ?
        re.MULTILINE,
    ),
    "python": re.compile(
        r"\b(if|elif|for|while|except|and|or|case)\b",
        re.MULTILINE,
    ),
    "rust": re.compile(
        r"\b(if|else if|for|while|loop|match|&&|\|\|)\b",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"\b(if|else if|for|while|switch|case|catch|\?\?|&&|\|\|)\b|"
        r"\?(?!\?)[^:]*:",
        re.MULTILINE,
    ),
    "javascript": re.compile(
        r"\b(if|else if|for|while|switch|case|catch|\?\?|&&|\|\|)\b|"
        r"\?(?!\?)[^:]*:",
        re.MULTILINE,
    ),
}
_DEFAULT_BRANCH_PATTERN = re.compile(r"\b(if|else if|for|while)\b", re.MULTILINE)


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class GodFile:
    file: FileRecord
    reasons: list[str]


@dataclass
class GodClass:
    symbol: Symbol
    method_count: int
    reasons: list[str]


@dataclass
class GodFunction:
    symbol: Symbol
    complexity: int


@dataclass
class SolidReport:
    god_files: list[GodFile] = field(default_factory=list)
    god_classes: list[GodClass] = field(default_factory=list)
    god_functions: list[GodFunction] = field(default_factory=list)
    soc_violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.god_files or self.god_classes or self.god_functions or self.soc_violations)


# ── Detection functions ───────────────────────────────────────────────────────


def detect_god_files(
    index: RepoIndex,
    god_file_loc: int = 500,
    god_file_functions: int = 20,
    god_file_classes: int = 5,
) -> list[GodFile]:
    """Flag files that exceed LOC, function count, or class count thresholds."""
    god_files: list[GodFile] = []

    for record in index.source_files:
        reasons: list[str] = []

        if record.loc > god_file_loc:
            reasons.append(f"{record.loc} LOC (threshold: {god_file_loc})")

        functions = [s for s in record.symbols if s.kind in ("function", "method")]
        if len(functions) > god_file_functions:
            reasons.append(f"{len(functions)} functions/methods (threshold: {god_file_functions})")

        classes = [s for s in record.symbols if s.kind == "class"]
        if len(classes) > god_file_classes:
            reasons.append(f"{len(classes)} classes (threshold: {god_file_classes})")

        if reasons:
            god_files.append(GodFile(file=record, reasons=reasons))

    return god_files


def detect_god_classes(
    index: RepoIndex,
    god_class_methods: int = 15,
) -> list[GodClass]:
    """Flag classes with too many methods — likely SRP violations."""
    god_classes: list[GodClass] = []

    for record in index.source_files:
        methods_by_class: dict[str, list[Symbol]] = defaultdict(list)
        class_symbols: dict[str, Symbol] = {}

        for sym in record.symbols:
            if sym.kind == "class":
                class_symbols[sym.name] = sym
            elif sym.kind == "method" and sym.parent_class:
                methods_by_class[sym.parent_class].append(sym)

        for class_name, methods in methods_by_class.items():
            if len(methods) >= god_class_methods:
                class_sym = class_symbols.get(class_name)
                if class_sym is None:
                    class_sym = Symbol(
                        name=class_name,
                        kind="class",
                        file=record.path,
                        line_start=methods[0].line_start,
                        line_end=methods[-1].line_end,
                        lang=record.lang,
                    )
                god_classes.append(
                    GodClass(
                        symbol=class_sym,
                        method_count=len(methods),
                        reasons=[f"{len(methods)} methods (threshold: {god_class_methods})"],
                    )
                )

    return god_classes


def compute_cyclomatic_complexity(symbol: Symbol, source: str) -> int:
    """
    Cyclomatic complexity = 1 + number of decision points in the function body.

    Uses regex over the symbol's source slice — fast and language-agnostic.
    Decision points: if/elif/else-if, for, while, case, catch, &&, ||, ternary.
    """
    lines = source.splitlines()
    # Extract just the function's lines (line numbers are 1-based)
    start = max(symbol.line_start - 1, 0)
    end = min(symbol.line_end, len(lines))
    body = "\n".join(lines[start:end])

    pattern = _BRANCH_PATTERNS.get(symbol.lang, _DEFAULT_BRANCH_PATTERN)
    return 1 + len(pattern.findall(body))


def detect_god_functions(
    index: RepoIndex,
    max_complexity: int = 10,
) -> list[GodFunction]:
    """Flag functions whose cyclomatic complexity exceeds the threshold."""
    god_functions: list[GodFunction] = []

    for record in index.source_files:
        if record.source is None:
            continue

        for sym in record.symbols:
            if sym.kind not in ("function", "method"):
                continue
            if sym.line_end <= sym.line_start:
                continue  # no body to analyze

            complexity = compute_cyclomatic_complexity(sym, record.source)
            if complexity > max_complexity:
                god_functions.append(GodFunction(symbol=sym, complexity=complexity))

    return god_functions


def detect_soc_violations(index: RepoIndex) -> list[dict[str, Any]]:
    """
    Detect files mixing multiple concern layers.

    Two signals:
    1. Archetype co-residence — file contains classes from 2+ distinct layers.
    2. UI archetype + data-layer imports.
    """
    violations: list[dict[str, Any]] = []

    for record in index.source_files:
        if record.lang != "dart":
            continue

        class_symbols = [s for s in record.symbols if s.kind == "class"]
        if not class_symbols:
            continue

        archetype_layers: dict[str, str] = {}
        for sym in class_symbols:
            for suffix, layer in _DART_ARCHETYPES.items():
                if sym.name.endswith(suffix):
                    archetype_layers[sym.name] = layer
                    break

        unique_layers = set(archetype_layers.values())

        if len(unique_layers) >= 2:
            layer_list = ", ".join(sorted(unique_layers))
            class_list = ", ".join(
                f"{name} ({layer})" for name, layer in sorted(archetype_layers.items())
            )
            violations.append(
                {
                    "file": record.path,
                    "reason": f"Multiple concern layers co-located ({layer_list}): {class_list}",
                    "type": "archetype_co_residence",
                    "layers": list(unique_layers),
                }
            )
            continue

        has_ui = any(layer == "ui" for layer in archetype_layers.values())
        if has_ui:
            if record.source is not None:
                source_text = record.source.lower()
            else:
                try:
                    source_text = record.path.read_text(errors="replace").lower()
                except OSError:
                    source_text = ""
            data_imports_found = [
                pkg for pkg in _DART_DATA_IMPORTS if f"package:{pkg}/" in source_text
            ]
            if data_imports_found:
                violations.append(
                    {
                        "file": record.path,
                        "reason": f"UI class imports data-layer packages: {', '.join(data_imports_found)}",
                        "type": "ui_data_import",
                        "imports": data_imports_found,
                    }
                )

    return violations


# ── Analyzer (plugin protocol) ────────────────────────────────────────────────


class SolidAnalyzer:
    name = "solid"
    description = (
        "Detects god files, god classes, high-complexity functions, and SoC violations "
        "via CST metrics. Flags LOC/function/method count violations and concern mixing."
    )

    def __init__(
        self,
        god_file_loc: int = 500,
        god_file_functions: int = 20,
        god_file_classes: int = 5,
        god_class_methods: int = 15,
        max_complexity: int = 10,
    ) -> None:
        self.god_file_loc = god_file_loc
        self.god_file_functions = god_file_functions
        self.god_file_classes = god_file_classes
        self.god_class_methods = god_class_methods
        self.max_complexity = max_complexity

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        god_files = detect_god_files(
            index,
            god_file_loc=self.god_file_loc,
            god_file_functions=self.god_file_functions,
            god_file_classes=self.god_file_classes,
        )
        god_classes = detect_god_classes(index, god_class_methods=self.god_class_methods)
        god_functions = detect_god_functions(index, max_complexity=self.max_complexity)
        soc_violations = detect_soc_violations(index)

        report = SolidReport(
            god_files=god_files,
            god_classes=god_classes,
            god_functions=god_functions,
            soc_violations=soc_violations,
        )

        total = len(god_files) + len(god_classes) + len(god_functions) + len(soc_violations)
        summary = (
            f"{total} issues — "
            f"{len(god_files)} god files, "
            f"{len(god_classes)} god classes, "
            f"{len(god_functions)} complex functions, "
            f"{len(soc_violations)} SoC violations"
        )

        issues: list[dict[str, Any]] = []
        for gf in god_files:
            issues.append({"type": "god_file", "file": str(gf.file.path), "reasons": gf.reasons})
        for gc in god_classes:
            issues.append({
                "type": "god_class",
                "symbol": gc.symbol.name,
                "file": str(gc.symbol.file),
                "line": gc.symbol.line_start,
                "method_count": gc.method_count,
                "reasons": gc.reasons,
            })
        for gfn in god_functions:
            issues.append({
                "type": "god_function",
                "symbol": gfn.symbol.name,
                "file": str(gfn.symbol.file),
                "line": gfn.symbol.line_start,
                "complexity": gfn.complexity,
            })
        for sv in soc_violations:
            issues.append({
                "type": "soc_violation",
                "file": str(sv["file"]),
                "reason": sv["reason"],
            })

        return AnalyzerResult(name=self.name, summary=summary, data=report, issues=issues)

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        report: SolidReport = result.data

        if not report.has_issues:
            console.print(Panel("[green]No SOLID issues found.[/green]", title="SOLID Health"))
            return

        if report.god_files:
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            table.add_column("File", style="cyan")
            table.add_column("Issues", style="yellow")
            for gf in sorted(report.god_files, key=lambda x: x.file.loc, reverse=True):
                try:
                    rel = gf.file.path.relative_to(root)
                except ValueError:
                    rel = gf.file.path
                table.add_row(str(rel), " · ".join(gf.reasons))
            console.print(Panel(table, title=f"God Files  {len(report.god_files)}"))

        if report.god_classes:
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            table.add_column("Class", style="cyan")
            table.add_column("File", style="dim")
            table.add_column("Methods", style="yellow", justify="right")
            for gc in sorted(report.god_classes, key=lambda x: x.method_count, reverse=True):
                try:
                    rel = gc.symbol.file.relative_to(root)
                except ValueError:
                    rel = gc.symbol.file
                table.add_row(gc.symbol.name, str(rel), str(gc.method_count))
            console.print(Panel(table, title=f"God Classes  {len(report.god_classes)}"))

        if report.god_functions:
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            table.add_column("Function", style="cyan")
            table.add_column("File:line", style="dim")
            table.add_column("Complexity", style="yellow", justify="right")
            for gfn in sorted(report.god_functions, key=lambda x: x.complexity, reverse=True):
                try:
                    rel = gfn.symbol.file.relative_to(root)
                except ValueError:
                    rel = gfn.symbol.file
                table.add_row(
                    gfn.symbol.name,
                    f"{rel}:{gfn.symbol.line_start}",
                    str(gfn.complexity),
                )
            console.print(Panel(table, title=f"Complex Functions  {len(report.god_functions)}"))

        if report.soc_violations:
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            table.add_column("File", style="cyan")
            table.add_column("Reason", style="yellow")
            for sv in report.soc_violations:
                try:
                    rel = sv["file"].relative_to(root)
                except ValueError:
                    rel = sv["file"]
                table.add_row(str(rel), sv["reason"])
            console.print(Panel(table, title=f"SoC Violations  {len(report.soc_violations)}"))
