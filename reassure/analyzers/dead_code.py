"""
Dead code analyzer.

Finds public symbols that are defined but never referenced anywhere in the repo.

Strategy:
  1. Build a definition set: all public, non-dunder symbol names in source files
  2. Build a reference set: all identifier tokens across ALL files (source + test)
  3. Dead candidates = definition_set - reference_set - entry_points
  4. Assign confidence based on symbol visibility and type

Caveats (documented, not silently ignored):
  - Dynamic dispatch (__getattr__, getattr(obj, name)) is not resolved
  - Entry points (main, CLI handlers) should be whitelisted via entry_points param
  - Dunder methods are excluded by default
  - Symbols used only via string-based reflection won't be detected as live
  - Private symbols (_prefix) are checked but reported as "medium" confidence
  - Test symbols are excluded from the dead-check but included in the reference set
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult

# Regex to extract all bare identifiers from source text.
# We use a broad pattern — anything that looks like a name — then intersect
# with our definition set. Over-inclusive is fine; it only reduces false positives.
_IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

# Default entry point names — always considered live regardless of references
_DEFAULT_ENTRY_POINTS = frozenset({
    "main",
    "app",
    "run",
    "handler",
    "create_app",
    "make_app",
    "setup",
    "teardown",
    "pytest_configure",
    "pytest_sessionstart",
})


@dataclass
class DeadSymbol:
    symbol: Symbol
    confidence: str  # "high" | "medium" | "low"
    caveat: str | None  # reason confidence isn't high


@dataclass
class DeadCodeReport:
    dead: list[DeadSymbol]
    total_symbols: int
    files_checked: int

    @property
    def high_confidence(self) -> list[DeadSymbol]:
        return [d for d in self.dead if d.confidence == "high"]

    @property
    def has_issues(self) -> bool:
        return bool(self.dead)


def analyze_dead_code(
    index: RepoIndex,
    entry_points: list[str] | None = None,
    min_confidence: str = "medium",
) -> DeadCodeReport:
    """
    Find symbols defined in source files but never referenced anywhere.

    entry_points: symbol names always treated as live (roots).
    min_confidence: "high" | "medium" | "low" — filter results below this level.
    """
    roots = _DEFAULT_ENTRY_POINTS | set(entry_points or [])
    refs_by_file = _build_reference_set(index)

    # Build cross-file reference set: all tokens except those only in the defining file
    # A name is "referenced" if it appears in at least one file OTHER than its own.
    # This prevents def site tokens from masking dead symbols.
    all_refs_except_self: dict[Path, set[str]] = {}
    all_files = list(refs_by_file.keys())
    for path in all_files:
        cross = set()
        for other_path, other_refs in refs_by_file.items():
            if other_path != path:
                cross |= other_refs
        all_refs_except_self[path] = cross

    dead: list[DeadSymbol] = []
    all_source_symbols: list[Symbol] = []

    for record in index.source_files:
        cross_refs = all_refs_except_self.get(record.path, set())

        for sym in record.symbols:
            # Dunders are never dead — they're protocol methods
            if _is_dunder(sym.name):
                continue
            # Only check functions, methods, and classes
            if sym.kind not in ("function", "method", "class"):
                continue

            all_source_symbols.append(sym)

            # Skip entry points
            if sym.name in roots:
                continue

            # Skip if referenced in any OTHER file
            if sym.name in cross_refs:
                continue

            # Assign confidence
            confidence, caveat = _assign_confidence(sym)

            if _confidence_rank(confidence) < _confidence_rank(min_confidence):
                continue

            dead.append(DeadSymbol(symbol=sym, confidence=confidence, caveat=caveat))

    return DeadCodeReport(
        dead=dead,
        total_symbols=len(all_source_symbols),
        files_checked=len(index.source_files),
    )


def _build_reference_set(index: RepoIndex) -> dict[Path, set[str]]:
    """
    Return a mapping of file path → identifiers found in that file's source.

    We track per-file so we can exclude a symbol's own definition file from
    its reference check (a function appearing only in its own def is still dead).
    """
    by_file: dict[Path, set[str]] = {}

    for record in index.files:  # all files, including tests
        source = record.source
        if source is None:
            try:
                source = record.path.read_text(errors="replace")
            except OSError:
                continue

        by_file[record.path] = {m.group(1) for m in _IDENTIFIER_RE.finditer(source)}

    return by_file


def _assign_confidence(sym: Symbol) -> tuple[str, str | None]:
    """
    Return (confidence, caveat) for a dead symbol.

    high   — public function/class, no ambiguity
    medium — private (_prefix), could be accessed dynamically
    low    — method on a class, could be called via polymorphism
    """
    if sym.kind == "method":
        return "low", "Methods may be called via polymorphism or dynamic dispatch"

    if sym.name.startswith("_"):
        return "medium", "Private symbol — could be accessed via getattr() or reflection"

    if not sym.is_public:
        return "medium", "Non-public symbol"

    return "high", None


def _confidence_rank(confidence: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(confidence, 0)


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


# ── Analyzer (plugin protocol) ────────────────────────────────────────────────


class DeadCodeAnalyzer:
    name = "dead_code"
    description = (
        "Finds public symbols (functions, classes) defined in source files but never "
        "referenced anywhere in the codebase. High-confidence results are safe to delete."
    )

    def __init__(
        self,
        entry_points: list[str] | None = None,
        min_confidence: str = "medium",
    ) -> None:
        self._entry_points = entry_points
        self._min_confidence = min_confidence

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        report = analyze_dead_code(
            index,
            entry_points=self._entry_points,
            min_confidence=self._min_confidence,
        )

        issues: list[dict[str, Any]] = [
            {
                "symbol": d.symbol.name,
                "kind": d.symbol.kind,
                "file": str(d.symbol.file),
                "line": d.symbol.line_start,
                "confidence": d.confidence,
                "caveat": d.caveat,
            }
            for d in report.dead
        ]

        high = len(report.high_confidence)
        total_dead = len(report.dead)
        summary = (
            f"{total_dead} dead symbols "
            f"({high} high-confidence) "
            f"of {report.total_symbols} total "
            f"({report.files_checked} files)"
        )
        if total_dead == 0:
            summary = f"No dead code found ({report.total_symbols} symbols, {report.files_checked} files)"

        return AnalyzerResult(name=self.name, summary=summary, data=report, issues=issues)

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()
        report: DeadCodeReport = result.data

        if not report.has_issues:
            console.print(
                Panel(
                    Text("No dead code found ✓", style="bold green"),
                    title=f"Dead Code  ({report.total_symbols} symbols checked)",
                )
            )
            return

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Symbol", style="bold", min_width=20, no_wrap=True)
        table.add_column("Kind", style="dim", width=8)
        table.add_column("File:line", style="dim", no_wrap=True)
        table.add_column("Confidence", width=10)

        _CONF_STYLE = {"high": "red", "medium": "yellow", "low": "dim"}

        for ds in sorted(
            report.dead,
            key=lambda d: (_confidence_rank(d.confidence) * -1, d.symbol.name),
        ):
            try:
                rel = ds.symbol.file.relative_to(root)
            except ValueError:
                rel = ds.symbol.file

            table.add_row(
                ds.symbol.name,
                ds.symbol.kind,
                f"{rel}:{ds.symbol.line_start}",
                Text(ds.confidence, style=_CONF_STYLE.get(ds.confidence, "")),
            )

        high_count = len(report.high_confidence)
        title_text = Text()
        title_text.append("Dead Code  ")
        title_text.append(f"{len(report.dead)} symbols", style="bold red")
        if high_count:
            title_text.append(f"  ({high_count} high-confidence)", style="dim")

        console.print(Panel(table, title=str(title_text)))
