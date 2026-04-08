"""
Rich terminal renderer.

Renders all analyzer reports to the terminal using rich tables, panels,
and color-coded output. Each section is a separate render function so
CLI callers can pick what to show.
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reassure.analyzers.observability import ObservabilityReport
from reassure.analyzers.test_coverage import CoverageReport
from reassure.classifiers.test_type import TestType

console = Console()

_TYPE_LABELS: dict[TestType, str] = {
    TestType.UNIT: "unit",
    TestType.INTEGRATION: "integ",
    TestType.E2E: "e2e",
    TestType.SMOKE: "smoke",
    TestType.SECURITY: "sec",
    TestType.UNKNOWN: "?",
}


def render_coverage(
    report: CoverageReport, show_passed: bool = False, root: Path | None = None
) -> None:
    """
    Render test coverage report.

    Shows per-symbol coverage with test-type columns.
    Uncovered symbols in red, unit-only in yellow, fully covered in green.
    """
    pct = report.coverage_pct
    pct_color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
    title = Text()
    title.append("Test Coverage  ")
    title.append(f"{pct}%", style=f"bold {pct_color}")
    title.append(f"  ({report.covered_symbols}/{report.total_symbols} symbols)")

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Symbol", style="bold", min_width=20, no_wrap=True)
    table.add_column("Kind", style="dim", width=8, no_wrap=True)
    table.add_column("File:line", style="dim", no_wrap=True)
    for label in _TYPE_LABELS.values():
        table.add_column(label, justify="center", width=6)

    shown = 0
    for sc in sorted(
        report.symbols, key=lambda s: (s.is_uncovered, s.symbol.file, s.symbol.line_start)
    ):
        if not show_passed and not sc.is_uncovered:
            continue

        sym = sc.symbol
        row_style = (
            "red"
            if sc.is_uncovered
            else "yellow"
            if not sc.tests_by_type.get(TestType.INTEGRATION)
            and not sc.tests_by_type.get(TestType.E2E)
            else "green"
        )

        type_cells = []
        for test_type in _TYPE_LABELS:
            count = len(sc.tests_by_type.get(test_type, []))
            if count:
                type_cells.append(Text(str(count), style="green"))
            else:
                type_cells.append(Text("·", style="dim"))

        file_display = sym.file.relative_to(root) if root else sym.file
        table.add_row(
            Text(sym.name, style=row_style),
            sym.kind,
            f"{file_display}:{sym.line_start}",
            *type_cells,
        )
        shown += 1

    if shown == 0:
        console.print(Panel(Text("All symbols covered ✓", style="bold green"), title=str(title)))
        return

    console.print(Panel(table, title=str(title)))

    uncovered_count = len(report.uncovered)
    if uncovered_count:
        console.print(
            f"  [red]{uncovered_count} uncovered[/red]  "
            f"[yellow]{len(report.unit_only)} unit-only[/yellow]"
        )


def render_observability(report: ObservabilityReport, root: Path | None = None) -> None:
    """
    Render observability gap report.

    Dark modules (every function unobserved) listed first.
    Per-function gaps in a table grouped by file.
    """
    pct_obs = round(100 - report.dark_pct, 1)
    pct_color = "green" if pct_obs >= 80 else "yellow" if pct_obs >= 50 else "red"
    title = Text()
    title.append("Observability  ")
    title.append(f"{pct_obs}%", style=f"bold {pct_color}")
    title.append(
        f"  ({report.total_functions - report.dark_functions}/{report.total_functions} instrumented)"
    )

    if report.dark_module_paths:
        dark_list = "\n".join(
            f"  [red]✗[/red] {p.relative_to(root) if root else p}" for p in report.dark_module_paths
        )
        console.print(
            Panel(
                dark_list,
                title="[bold red]Dark Modules[/bold red] — zero instrumentation",
                border_style="red",
            )
        )

    if not report.gaps:
        console.print(
            Panel(Text("All public functions instrumented ✓", style="bold green"), title=str(title))
        )
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Function", style="bold red", min_width=24, no_wrap=True)
    table.add_column("Kind", style="dim", width=8, no_wrap=True)
    table.add_column("File:line", style="dim", no_wrap=True)

    for gap in sorted(report.gaps, key=lambda g: (g.symbol.file, g.symbol.line_start)):
        sym = gap.symbol
        file_display = sym.file.relative_to(root) if root else sym.file
        table.add_row(sym.name, sym.kind, f"{file_display}:{sym.line_start}")

    console.print(Panel(table, title=str(title)))
    console.print(
        f"  [red]{report.dark_functions} dark functions[/red]  [dim]{len(report.dark_module_paths)} dark modules[/dim]"
    )
