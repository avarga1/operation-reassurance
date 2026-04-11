"""
Blast radius analyzer.

Given a set of changed lines (from a git diff or explicit input), answers:

  1. Which symbols span those changed lines?
  2. Which source files reference those symbols (direct callers)?
  3. Transitive closure — callers of callers (configurable depth)?
  4. Of all affected symbols, which have no test coverage (the dangerous ones)?

The dangerous quadrant is blast radius × no coverage — callers that will
silently regress when you change the symbol they depend on.

Usage:
  # CLI — diff against a base branch
  reassure ./src --only blast_radius --base main

  # MCP tool
  get_blast_radius(path="/repo", base="main")

  # CI — fail if uncovered callers exist
  reassure ./src --only blast_radius --base main --output json | jq '.issues | length'
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reassure.analyzers.test_coverage import _collect_references, analyze_coverage
from reassure.classifiers.test_type import classify_test_file
from reassure.core.parser import parse_file
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class CallerRef:
    symbol: Symbol
    file: Path
    is_covered: bool


@dataclass
class AffectedSymbol:
    symbol: Symbol
    direct_callers: list[CallerRef] = field(default_factory=list)
    transitive_callers: list[CallerRef] = field(default_factory=list)

    @property
    def all_callers(self) -> list[CallerRef]:
        return self.direct_callers + self.transitive_callers

    @property
    def uncovered_callers(self) -> list[CallerRef]:
        return [c for c in self.all_callers if not c.is_covered]


@dataclass
class BlastRadiusReport:
    base: str  # git ref compared against (e.g. "main")
    changed_files: list[Path]
    affected_symbols: list[AffectedSymbol]

    @property
    def total_callers(self) -> int:
        return sum(len(a.all_callers) for a in self.affected_symbols)

    @property
    def total_uncovered_callers(self) -> int:
        return sum(len(a.uncovered_callers) for a in self.affected_symbols)

    @property
    def has_risk(self) -> bool:
        return self.total_uncovered_callers > 0


# ── Diff parsing ──────────────────────────────────────────────────────────────

# Matches: @@ -a,b +c,d @@ or @@ -a +c @@
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


def parse_diff(diff_text: str, repo_root: Path) -> dict[Path, list[tuple[int, int]]]:
    """
    Parse unified diff text → {absolute_path: [(start_line, end_line), ...]}

    Only captures added/modified hunks (+ side of the diff).
    """
    result: dict[Path, list[tuple[int, int]]] = defaultdict(list)
    current_file: Path | None = None

    for line in diff_text.splitlines():
        m = _FILE_RE.match(line)
        if m:
            current_file = (repo_root / m.group(1)).resolve()
            continue

        if current_file is None:
            continue

        m = _HUNK_RE.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                result[current_file].append((start, start + count - 1))

    return dict(result)


def get_diff(repo_root: Path, base: str) -> str:
    """Run `git diff <base>` and return the unified diff text."""
    result = subprocess.run(
        ["git", "diff", base],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_staged_diff(repo_root: Path) -> str:
    """Run `git diff --cached` for staged-only analysis."""
    result = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ── Symbol intersection ───────────────────────────────────────────────────────


def symbols_in_hunks(
    file_record: FileRecord,
    hunks: list[tuple[int, int]],
) -> list[Symbol]:
    """
    Return all symbols whose line range overlaps any changed hunk.
    Interval overlap: sym_start <= hunk_end AND sym_end >= hunk_start
    """
    changed: list[Symbol] = []
    for sym in file_record.symbols:
        for hunk_start, hunk_end in hunks:
            if sym.line_start <= hunk_end and sym.line_end >= hunk_start:
                changed.append(sym)
                break
    return changed


# ── Reference graph ───────────────────────────────────────────────────────────


def build_reference_graph(index: RepoIndex) -> dict[str, list[Symbol]]:
    """
    Build an inverted reference graph: symbol_name → [symbols that reference it].

    Walks every source file (not just test files), extracts all referenced names,
    and maps them back to the symbols that own those names.
    """
    # name → all symbols with that name (across all source files)
    name_to_symbols: dict[str, list[Symbol]] = defaultdict(list)
    for sym in index.all_symbols:
        name_to_symbols[sym.name].append(sym)

    # file → set of referenced names
    # Use cached source from FileRecord when available (avoids re-reading and
    # allows tests to pass in-memory FileRecords without real disk files).
    file_refs: dict[Path, set[str]] = {}
    for record in index.source_files:
        if record.source is not None:
            from reassure.core.parser import parse_source

            tree = parse_source(record.source, record.lang)
            if tree is None:
                file_refs[record.path] = set()
                continue
            refs: set[str] = set()
            _collect_references(tree.root_node, record.source, refs)
            file_refs[record.path] = refs
        else:
            parsed = parse_file(record.path)
            if parsed is None:
                file_refs[record.path] = set()
                continue
            tree, source = parsed
            refs = set()
            _collect_references(tree.root_node, source, refs)
            file_refs[record.path] = refs

    # symbol_name → [caller symbols]
    # A symbol S is a caller of T if S's file references T's name
    callers: dict[str, list[Symbol]] = defaultdict(list)

    for record in index.source_files:
        refs = file_refs.get(record.path, set())
        for ref_name in refs:
            if ref_name not in name_to_symbols:
                continue
            for target_sym in name_to_symbols[ref_name]:
                # Don't count self-reference (symbol calling itself within same file)
                if target_sym.file == record.path:
                    continue
                # All symbols defined in this file are potential callers
                for caller_sym in record.symbols:
                    callers[ref_name].append(caller_sym)
                break  # one entry per referencing file, not per symbol in that file

    return dict(callers)


def transitive_callers(
    start_symbols: list[Symbol],
    ref_graph: dict[str, list[Symbol]],
    depth: int = 2,
) -> dict[str, list[Symbol]]:
    """
    BFS over the reference graph to find callers at depth > 1.

    Returns {symbol_name: [transitive_caller_symbols]} for callers
    not already in the direct caller set.
    """
    direct_names = {s.name for s in start_symbols}
    visited: set[str] = set(direct_names)
    result: dict[str, list[Symbol]] = defaultdict(list)

    queue: deque[tuple[Symbol, int]] = deque((sym, 1) for sym in start_symbols)

    while queue:
        sym, current_depth = queue.popleft()
        if current_depth >= depth:
            continue

        for caller in ref_graph.get(sym.name, []):
            if caller.name not in visited:
                visited.add(caller.name)
                result[sym.name].append(caller)
                queue.append((caller, current_depth + 1))

    return dict(result)


# ── Coverage lookup ───────────────────────────────────────────────────────────


def build_coverage_set(index: RepoIndex) -> set[str]:
    """Return the set of symbol names that have at least one test."""
    classifications = {
        f.path: classify_test_file(f.path, list(f.imports), []) for f in index.test_files
    }
    report = analyze_coverage(index, classifications)
    return {sc.symbol.name for sc in report.symbols if not sc.is_uncovered}


# ── Core analysis ─────────────────────────────────────────────────────────────


def analyze_blast_radius(
    index: RepoIndex,
    diff_hunks: dict[Path, list[tuple[int, int]]],
    base: str = "unknown",
    transitive_depth: int = 2,
) -> BlastRadiusReport:
    """
    Core blast radius analysis.

    diff_hunks: output of parse_diff() — {abs_path: [(start, end), ...]}
    """
    # 1. Find all changed symbols
    changed_symbols: list[Symbol] = []
    file_map = {r.path: r for r in index.source_files}

    for path, hunks in diff_hunks.items():
        record = file_map.get(path)
        if record is None:
            continue
        changed_symbols.extend(symbols_in_hunks(record, hunks))

    # 2. Build reference graph + coverage set
    ref_graph = build_reference_graph(index)
    covered_names = build_coverage_set(index)

    # 3. Direct callers
    direct: dict[str, list[Symbol]] = {}
    for sym in changed_symbols:
        direct[sym.name] = ref_graph.get(sym.name, [])

    # 4. Transitive callers
    trans = transitive_callers(changed_symbols, ref_graph, depth=transitive_depth)

    # 5. Assemble results
    affected: list[AffectedSymbol] = []
    for sym in changed_symbols:
        direct_callers = [
            CallerRef(
                symbol=c,
                file=c.file,
                is_covered=c.name in covered_names,
            )
            for c in direct.get(sym.name, [])
        ]
        transitive_caller_syms = trans.get(sym.name, [])
        transitive_callers_list = [
            CallerRef(
                symbol=c,
                file=c.file,
                is_covered=c.name in covered_names,
            )
            for c in transitive_caller_syms
        ]
        affected.append(
            AffectedSymbol(
                symbol=sym,
                direct_callers=direct_callers,
                transitive_callers=transitive_callers_list,
            )
        )

    return BlastRadiusReport(
        base=base,
        changed_files=list(diff_hunks.keys()),
        affected_symbols=affected,
    )


# ── Analyzer (plugin protocol) ────────────────────────────────────────────────


class BlastRadiusAnalyzer:
    name = "blast_radius"
    description = (
        "Given a git diff, finds which symbols changed, who calls them, "
        "and which callers have no test coverage (the dangerous ones)."
    )

    def __init__(self, base: str = "main", transitive_depth: int = 2) -> None:
        self.base = base
        self.transitive_depth = transitive_depth

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        try:
            diff_text = get_diff(index.root, self.base)
        except subprocess.CalledProcessError as e:
            return AnalyzerResult(
                name=self.name,
                summary=f"git diff failed: {e}",
                issues=[],
            )

        if not diff_text.strip():
            return AnalyzerResult(
                name=self.name,
                summary=f"No changes vs {self.base}",
                issues=[],
            )

        diff_hunks = parse_diff(diff_text, index.root)
        report = analyze_blast_radius(
            index, diff_hunks, base=self.base, transitive_depth=self.transitive_depth
        )

        summary = (
            f"{len(report.affected_symbols)} symbols changed, "
            f"{report.total_callers} callers affected, "
            f"{report.total_uncovered_callers} with no test coverage"
        )

        issues: list[dict[str, Any]] = []
        for affected in report.affected_symbols:
            for caller in affected.uncovered_callers:
                issues.append(
                    {
                        "type": "uncovered_caller",
                        "changed_symbol": affected.symbol.name,
                        "changed_file": str(affected.symbol.file),
                        "caller": caller.symbol.name,
                        "caller_file": str(caller.file),
                        "caller_line": caller.symbol.line_start,
                        "reason": f"{caller.symbol.name} calls {affected.symbol.name} but has no tests",
                    }
                )

        return AnalyzerResult(name=self.name, summary=summary, data=report, issues=issues)

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        report: BlastRadiusReport = result.data

        if not report.affected_symbols:
            console.print(
                Panel(f"[green]No changed symbols vs {report.base}[/green]", title="Blast Radius")
            )
            return

        for affected in report.affected_symbols:
            sym = affected.symbol
            rel = sym.file.relative_to(root) if sym.file.is_relative_to(root) else sym.file

            table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            table.add_column("Caller", style="cyan")
            table.add_column("File", style="dim")
            table.add_column("Line", style="dim", justify="right")
            table.add_column("Coverage", justify="center")

            for caller in affected.direct_callers:
                crel = (
                    caller.file.relative_to(root)
                    if caller.file.is_relative_to(root)
                    else caller.file
                )
                cov = "[green]✓[/green]" if caller.is_covered else "[red]✗ DARK[/red]"
                table.add_row(caller.symbol.name, str(crel), str(caller.symbol.line_start), cov)

            for caller in affected.transitive_callers:
                crel = (
                    caller.file.relative_to(root)
                    if caller.file.is_relative_to(root)
                    else caller.file
                )
                cov = "[green]✓[/green]" if caller.is_covered else "[red]✗ DARK[/red]"
                table.add_row(
                    f"  {caller.symbol.name}",
                    str(crel),
                    str(caller.symbol.line_start),
                    cov,
                )

            risk = ""
            if affected.uncovered_callers:
                risk = f"  [red]⚠ {len(affected.uncovered_callers)} callers with no tests[/red]"

            title = (
                f"[bold]{sym.name}[/bold]  [dim]{rel}:{sym.line_start}–{sym.line_end}[/dim]{risk}"
            )
            console.print(Panel(table, title=title))
