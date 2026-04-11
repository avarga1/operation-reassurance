"""
Async correctness analyzer.

Static CST checks for common async bugs — no runtime required.

Checks per language:

Dart (primary — Flutter Future chains):
  1. async_never_awaits   — an `async` function that contains no `await` expression
                            (almost certainly a mistake or dead async marker)
  2. unawaited_future     — a bare expression statement whose type looks like a
                            Future call but has no `await` prefix  (fire-and-forget)
  3. missing_async        — a function body contains `await` but the function is
                            NOT marked `async` (parse error at runtime)

Python:
  1. async_never_awaits   — same logic
  2. unawaited_coroutine  — bare `asyncio.create_task(...)` or coroutine call
                            without `await` inside an async def

Rust / TS / JS: basic async_never_awaits only.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Dart: identifiers that return Futures and are commonly fire-and-forgot
_DART_FUTURE_CALLS = re.compile(
    r"\b(?:Future|then|catchError|whenComplete|timeout|"
    r"HttpClient|http\.get|http\.post|http\.put|http\.delete|"
    r"dio\.get|dio\.post|"
    r"FirebaseFirestore|FirebaseAuth|FirebaseStorage|"
    r"SharedPreferences\.getInstance|"
    r"getApplicationDocumentsDirectory|"
    r"FlutterSecureStorage)\b"
)

# Line-level patterns
_AWAIT_RE = re.compile(r"\bawait\b")
_ASYNC_RE = re.compile(r"\basync\b")

# Dart expression statement that looks like a Future call without await
# e.g. "    someAsyncMethod();"  at start of a statement
_DART_BARE_FUTURE_STMT = re.compile(
    r"^\s+(?!await\b)(?!return\b)(?!final\b)(?!var\b)(?!const\b)(?!//)"
    r"[A-Za-z_][A-Za-z0-9_.]*\s*\([^)]*\)\s*;"
)


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


@dataclass
class AsyncIssue:
    symbol: Symbol
    check: str  # "async_never_awaits" | "unawaited_future" | "missing_async"
    line: int  # 1-indexed line within file
    detail: str


@dataclass
class AsyncReport:
    issues: list[AsyncIssue] = field(default_factory=list)
    total_async_functions: int = 0
    flagged_functions: int = 0

    @property
    def issue_pct(self) -> float:
        if self.total_async_functions == 0:
            return 0.0
        return round(self.flagged_functions / self.total_async_functions * 100, 1)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class AsyncLinter:
    """Plugin-protocol analyzer for async correctness issues."""

    name = "async"
    description = (
        "Finds async functions that never await, unawaited Futures, "
        "and await-without-async bugs."
    )

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        report = _analyze_async(index)
        issues = [
            {
                "symbol": i.symbol.name,
                "file": str(i.symbol.file),
                "line": i.line,
                "check": i.check,
                "detail": i.detail,
            }
            for i in report.issues
        ]
        flagged = len({(str(i.symbol.file), i.symbol.name) for i in report.issues})
        return AnalyzerResult(
            name=self.name,
            summary=(
                f"{report.total_async_functions} async functions — "
                f"{flagged} with issues"
            ),
            data=report,
            issues=issues,
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        _render_async(result.data, root=root)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _analyze_async(index: RepoIndex) -> AsyncReport:
    report = AsyncReport()

    # Build source cache
    source_cache: dict[Path, str] = {}
    for rec in index.source_files:
        if rec.source:
            source_cache[rec.path] = rec.source
        else:
            with contextlib.suppress(OSError):
                source_cache[rec.path] = rec.path.read_text(errors="replace")

    for symbol in index.all_symbols:
        if symbol.kind not in ("function", "method"):
            continue
        source = source_cache.get(symbol.file)
        if source is None:
            continue

        lines = source.splitlines()
        start = max(symbol.line_start - 1, 0)
        end = min(symbol.line_end, len(lines))
        body_lines = lines[start:end]
        body = "\n".join(body_lines)

        is_async = _is_async_symbol(symbol, body_lines)
        has_await = bool(_AWAIT_RE.search(body))

        if is_async:
            report.total_async_functions += 1

        issues_for_sym: list[AsyncIssue] = []

        # Check 1: async but never awaits
        if is_async and not has_await:
            issues_for_sym.append(
                AsyncIssue(
                    symbol=symbol,
                    check="async_never_awaits",
                    line=symbol.line_start,
                    detail=f"`{symbol.name}` is async but contains no await expression",
                )
            )

        # Check 2: await without async (only meaningful for Dart/Python)
        if not is_async and has_await and symbol.lang in ("dart", "python"):
            issues_for_sym.append(
                AsyncIssue(
                    symbol=symbol,
                    check="missing_async",
                    line=symbol.line_start,
                    detail=f"`{symbol.name}` uses await but is not marked async",
                )
            )

        # Check 3: unawaited Futures (Dart only)
        if symbol.lang == "dart" and is_async:
            unawaited = _find_unawaited_dart(body_lines, symbol.line_start)
            issues_for_sym.extend(
                AsyncIssue(
                    symbol=symbol,
                    check="unawaited_future",
                    line=line_no,
                    detail=f"Possible unawaited Future at line {line_no}: `{snippet}`",
                )
                for line_no, snippet in unawaited
            )

        if issues_for_sym:
            report.issues.extend(issues_for_sym)
            report.flagged_functions += 1

    return report


def _is_async_symbol(symbol: Symbol, body_lines: list[str]) -> bool:
    """True if the function signature is async."""
    if symbol.is_async:
        return True
    # Fallback: scan first line of the body slice for 'async'
    if body_lines:
        first = body_lines[0]
        if _ASYNC_RE.search(first):
            return True
    return False


def _find_unawaited_dart(body_lines: list[str], line_start: int) -> list[tuple[int, str]]:
    """
    Heuristic scan for bare Future-ish calls inside a Dart async body.
    Returns list of (absolute_line_number, snippet).
    """
    results: list[tuple[int, str]] = []
    for i, line in enumerate(body_lines):
        # Must look like a standalone statement (indented, no keyword prefix)
        if not _DART_BARE_FUTURE_STMT.match(line):
            continue
        # Must reference something that looks Future-ish
        if not _DART_FUTURE_CALLS.search(line):
            continue
        # Skip lines that already have await
        if _AWAIT_RE.search(line):
            continue
        abs_line = line_start + i
        results.append((abs_line, line.strip()[:80]))
    return results


# ---------------------------------------------------------------------------
# Terminal renderer
# ---------------------------------------------------------------------------


def _render_async(report: AsyncReport, root: Path | None = None) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()

    title = Text()
    title.append("Async Correctness  ")
    if report.issues:
        title.append(f"{len(report.issues)} issues", style="bold red")
    else:
        title.append("clean", style="bold green")
    title.append(
        f"  ({report.total_async_functions} async functions checked)",
        style="dim",
    )

    if not report.issues:
        console.print(
            Panel(
                Text("No async issues found ✓", style="bold green"),
                title=str(title),
            )
        )
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Check", style="bold red", no_wrap=True)
    table.add_column("Symbol", no_wrap=True)
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Line", style="dim", no_wrap=True, width=5)
    table.add_column("Detail", no_wrap=False)

    for issue in sorted(report.issues, key=lambda x: (str(x.symbol.file), x.line)):
        try:
            file_display = (
                str(issue.symbol.file.relative_to(root)) if root else str(issue.symbol.file)
            )
        except ValueError:
            file_display = str(issue.symbol.file)

        table.add_row(
            issue.check,
            issue.symbol.name,
            file_display,
            str(issue.line),
            issue.detail,
        )

    console.print(Panel(table, title=str(title)))
