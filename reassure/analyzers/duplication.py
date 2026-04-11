"""
Duplication analyzer.

Detects two classes of copy-paste duplication:

  1. Structural clones — functions/methods whose body has the same CST shape
     after normalizing all identifiers to ``__ID__``.  Same logic, different
     names.  Closes issue #13.

  2. Repeated expression subtrees — verbatim CST subtrees (≥ min_lines lines)
     that appear min_occurrences or more times across 2+ files.  Catches
     BoxDecoration blocks copy-pasted 14 times, etc.  Closes issue #40.

Algorithm summary
-----------------
Clone detection
  • For every non-private function/method in source files that carries a body,
    extract the body text from ``FileRecord.source``.
  • Normalize: strip comments (# …  and // …), collapse whitespace, replace
    every identifier token with ``__ID__``.
  • SHA-256 (first 16 hex chars) the normalised text → fingerprint.
  • Groups with 2+ members spanning 2+ distinct files are clone groups.

Subtree detection
  • For every source file build/reuse the CST via ``parse_file``.
  • Walk every node; if ``end_line - start_line >= min_lines`` extract raw text.
  • SHA-256 (first 16 hex chars) → fingerprint.
  • Groups with count >= min_occurrences spanning 2+ files are duplicates.
  • Test files are excluded.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reassure.core.parser import parse_file, parse_source
from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult

# Regex that matches identifier tokens for normalization
_IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

# Strip single-line comments from Python (#) and C-style (//)
_COMMENT_RE = re.compile(r"(#[^\n]*|//[^\n]*)")


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class CloneGroup:
    fingerprint: str
    symbols: list[Symbol]
    snippet: str  # first 120 chars of normalized body


@dataclass
class DuplicateSubtree:
    fingerprint: str
    occurrences: list[tuple[Path, int, int]]  # (file, line_start, line_end)
    snippet: str  # first 120 chars of raw text


@dataclass
class DuplicationReport:
    clone_groups: list[CloneGroup] = field(default_factory=list)
    duplicate_subtrees: list[DuplicateSubtree] = field(default_factory=list)
    total_symbols: int = 0
    cloned_symbols: int = 0

    @property
    def clone_pct(self) -> float:
        if self.total_symbols == 0:
            return 0.0
        return round(100.0 * self.cloned_symbols / self.total_symbols, 1)

    @property
    def has_issues(self) -> bool:
        return bool(self.clone_groups or self.duplicate_subtrees)


# ── Normalization helpers ─────────────────────────────────────────────────────


def _normalize_body(text: str) -> str:
    """
    Produce a structurally comparable string from raw source text.

    Steps:
    1. Strip single-line comments
    2. Replace every identifier token with ``__ID__``
    3. Collapse runs of whitespace (spaces, tabs, newlines) to a single space
    4. Strip leading/trailing whitespace
    """
    text = _COMMENT_RE.sub("", text)
    text = _IDENTIFIER_RE.sub("__ID__", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fingerprint(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 of *text*."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


# ── Body extraction from symbol line ranges ───────────────────────────────────


def _body_text(sym: Symbol, source: str) -> str | None:
    """
    Return the source text for the lines occupied by *sym*.

    Uses ``sym.line_start`` / ``sym.line_end`` (1-based, inclusive) to slice
    the source.  Returns ``None`` if *source* is empty or line range is invalid.
    """
    if not source:
        return None
    lines = source.splitlines()
    # line numbers are 1-based, inclusive
    start = max(0, sym.line_start - 1)
    end = min(len(lines), sym.line_end)
    if start >= end:
        return None
    return "\n".join(lines[start:end])


# ── Clone detection ───────────────────────────────────────────────────────────


def _find_clone_groups(index: RepoIndex) -> tuple[list[CloneGroup], int]:
    """
    Return (clone_groups, total_eligible_symbols).

    Only public functions/methods with a non-trivial body are considered.
    """
    # Build a source lookup: path → source text
    source_by_path: dict[Path, str] = {}
    for record in index.source_files:
        if record.source:
            source_by_path[record.path] = record.source

    # fingerprint → list of (Symbol, normalized_snippet)
    groups: dict[str, list[tuple[Symbol, str]]] = defaultdict(list)
    total = 0

    for record in index.source_files:
        source = source_by_path.get(record.path, "")
        for sym in record.symbols:
            if sym.kind not in ("function", "method"):
                continue
            if sym.name.startswith("_"):
                continue  # skip private symbols

            total += 1

            body = _body_text(sym, source)
            if not body:
                continue

            normalized = _normalize_body(body)
            if len(normalized) < 10:
                # Trivially short — skip (e.g. `pass` or empty body)
                continue

            fp = _fingerprint(normalized)
            groups[fp].append((sym, normalized))

    clone_groups: list[CloneGroup] = []
    for fp, members in groups.items():
        if len(members) < 2:
            continue
        files = {sym.file for sym, _ in members}
        if len(files) < 2:
            continue
        syms = [sym for sym, _ in members]
        snippet = members[0][1][:120]
        clone_groups.append(CloneGroup(fingerprint=fp, symbols=syms, snippet=snippet))

    return clone_groups, total


# ── Subtree detection ─────────────────────────────────────────────────────────


def _walk_subtrees(
    node: Any,
    file_path: Path,
    lines: list[str],
    min_lines: int,
    groups: dict[str, list[tuple[Path, int, int, str]]],
) -> None:
    """Recursively walk a CST node, collecting subtrees with span >= min_lines."""
    start_line = node.start_point[0]  # 0-based
    end_line = node.end_point[0]  # 0-based inclusive
    span = end_line - start_line

    if span >= min_lines:
        snippet_lines = lines[start_line : end_line + 1]
        raw = "\n".join(snippet_lines)
        fp = _fingerprint(raw)
        groups[fp].append((file_path, start_line + 1, end_line + 1, raw[:120]))

    for child in node.children:
        _walk_subtrees(child, file_path, lines, min_lines, groups)


def _find_duplicate_subtrees(
    index: RepoIndex,
    min_lines: int = 4,
    min_occurrences: int = 3,
) -> list[DuplicateSubtree]:
    """
    Walk CST nodes across all source files and find repeated verbatim subtrees.

    Nodes whose span is ``< min_lines`` lines are skipped.  Groups must appear
    ``>= min_occurrences`` times across ``>= 2`` distinct files.
    """
    # fingerprint → list of (path, line_start, line_end, snippet)
    groups: dict[str, list[tuple[Path, int, int, str]]] = defaultdict(list)

    for record in index.source_files:
        # Never scan test files
        if record.is_test:
            continue

        source = record.source
        if not source:
            continue

        # Attempt to get a CST from cached source first, then fall back to
        # reading from disk (so synthetic records in tests work fine).
        tree = parse_source(source, record.lang)
        if tree is None:
            # lang may be unsupported or grammar unavailable; try disk path
            parse_result = parse_file(record.path)
            if parse_result is None:
                continue
            tree, _ = parse_result

        lines = source.splitlines()
        _walk_subtrees(tree.root_node, record.path, lines, min_lines, groups)

    result: list[DuplicateSubtree] = []
    for fp, occurrences in groups.items():
        if len(occurrences) < min_occurrences:
            continue
        files = {path for path, _, _, _ in occurrences}
        if len(files) < 2:
            continue
        snippet = occurrences[0][3]
        occ_tuples: list[tuple[Path, int, int]] = [
            (path, ls, le) for path, ls, le, _ in occurrences
        ]
        result.append(DuplicateSubtree(fingerprint=fp, occurrences=occ_tuples, snippet=snippet))

    return result


# ── Analyzer (plugin protocol) ────────────────────────────────────────────────


class DuplicationAnalyzer:
    name = "duplication"
    description = (
        "Finds copy-pasted function bodies (structural clones) and repeated expression subtrees."
    )

    def __init__(
        self,
        min_subtree_lines: int = 4,
        min_occurrences: int = 3,
    ) -> None:
        self._min_subtree_lines = min_subtree_lines
        self._min_occurrences = min_occurrences

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        clone_groups, total_symbols = _find_clone_groups(index)
        duplicate_subtrees = _find_duplicate_subtrees(
            index,
            min_lines=self._min_subtree_lines,
            min_occurrences=self._min_occurrences,
        )

        cloned_symbols = sum(len(cg.symbols) for cg in clone_groups)

        report = DuplicationReport(
            clone_groups=clone_groups,
            duplicate_subtrees=duplicate_subtrees,
            total_symbols=total_symbols,
            cloned_symbols=cloned_symbols,
        )

        total_issues = len(clone_groups) + len(duplicate_subtrees)
        if total_issues == 0:
            summary = f"No duplication found ({total_symbols} symbols checked)"
        else:
            summary = (
                f"{len(clone_groups)} clone group(s) "
                f"({cloned_symbols}/{total_symbols} symbols, {report.clone_pct}%), "
                f"{len(duplicate_subtrees)} repeated subtree(s)"
            )

        issues: list[dict[str, Any]] = []

        for cg in clone_groups:
            files = sorted({str(sym.file) for sym in cg.symbols})
            sym_names = [sym.name for sym in cg.symbols]
            issues.append(
                {
                    "type": "clone",
                    "fingerprint": cg.fingerprint,
                    "count": len(cg.symbols),
                    "files": files,
                    "symbols": sym_names,
                    "snippet": cg.snippet,
                }
            )

        for ds in duplicate_subtrees:
            files = sorted({str(path) for path, _, _ in ds.occurrences})
            issues.append(
                {
                    "type": "subtree",
                    "fingerprint": ds.fingerprint,
                    "count": len(ds.occurrences),
                    "files": files,
                    "snippet": ds.snippet,
                }
            )

        return AnalyzerResult(name=self.name, summary=summary, data=report, issues=issues)

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()
        report: DuplicationReport = result.data

        if not report.has_issues:
            console.print(
                Panel(
                    Text("No duplication found ✓", style="bold green"),
                    title=f"Duplication  ({report.total_symbols} symbols checked)",
                )
            )
            return

        # ── Clone groups ──────────────────────────────────────────────────────
        if report.clone_groups:
            table = Table(
                box=box.SIMPLE,
                show_header=True,
                header_style="bold cyan",
                expand=True,
            )
            table.add_column("Fingerprint", style="dim", width=18, no_wrap=True)
            table.add_column("Symbols", style="bold", min_width=20)
            table.add_column("Files", style="dim")
            table.add_column("#", justify="right", width=4)

            for cg in sorted(report.clone_groups, key=lambda g: len(g.symbols), reverse=True):
                sym_names = ", ".join(sym.name for sym in cg.symbols)
                files: list[str] = []
                for sym in cg.symbols:
                    try:
                        rel = sym.file.relative_to(root)
                    except ValueError:
                        rel = sym.file
                    files.append(str(rel))
                unique_files = ", ".join(sorted(set(files)))
                table.add_row(cg.fingerprint, sym_names, unique_files, str(len(cg.symbols)))

            title_text = Text()
            title_text.append("Structural Clones  ")
            title_text.append(f"{len(report.clone_groups)} group(s)", style="bold red")
            title_text.append(
                f"  {report.cloned_symbols}/{report.total_symbols} symbols ({report.clone_pct}%)",
                style="dim",
            )
            console.print(Panel(table, title=str(title_text)))

        # ── Repeated subtrees ─────────────────────────────────────────────────
        if report.duplicate_subtrees:
            table = Table(
                box=box.SIMPLE,
                show_header=True,
                header_style="bold cyan",
                expand=True,
            )
            table.add_column("Fingerprint", style="dim", width=18, no_wrap=True)
            table.add_column("Occurrences", justify="right", width=12)
            table.add_column("Files", style="dim")
            table.add_column("Snippet", style="dim", no_wrap=True)

            for ds in sorted(
                report.duplicate_subtrees, key=lambda d: len(d.occurrences), reverse=True
            ):
                files = sorted({str(_try_relative(path, root)) for path, _, _ in ds.occurrences})
                snippet = ds.snippet[:60].replace("\n", "↵")
                table.add_row(
                    ds.fingerprint,
                    str(len(ds.occurrences)),
                    ", ".join(files),
                    snippet,
                )

            title_text = Text()
            title_text.append("Repeated Subtrees  ")
            title_text.append(f"{len(report.duplicate_subtrees)} pattern(s)", style="bold yellow")
            console.print(Panel(table, title=str(title_text)))


def _try_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path
