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

from reassure.analyzers.folder_structure import FolderStructureReport
from reassure.analyzers.observability import ObservabilityReport
from reassure.analyzers.taxonomy import TaxonomyReport
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


def render_taxonomy(report: TaxonomyReport, root: Path | None = None) -> None:
    """
    Render taxonomy violation report.

    Groups violations by file. Shows which rule was violated, why, and
    the message the LLM would see from the PreToolUse hook.
    """
    title = Text()
    title.append("Taxonomy  ")
    if report.violations:
        title.append(f"{len(report.violations)} violations", style="bold red")
    else:
        title.append("clean", style="bold green")
    title.append(
        f"  ({report.files_checked} files checked, {report.rules_applied} rules)",
        style="dim",
    )

    if not report.violations:
        console.print(
            Panel(Text("All files within taxonomy rules ✓", style="bold green"), title=str(title))
        )
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("File", style="bold red", min_width=30, no_wrap=True)
    table.add_column("Rule", style="dim", no_wrap=True)
    table.add_column("Violations", no_wrap=False)

    for v in sorted(report.violations, key=lambda x: str(x.file)):
        file_display = v.file.relative_to(root) if root and root in v.file.parents else v.file
        table.add_row(
            str(file_display),
            f"[dim]{v.rule.pattern}[/dim]\n[italic]{v.rule.purpose}[/italic]",
            "\n".join(f"[red]✗[/red] {r}" for r in v.reasons),
        )
        if v.rule.message:
            table.add_row("", "", f"[yellow italic]{v.rule.message}[/yellow italic]")

    console.print(Panel(table, title=str(title)))


def render_folder_structure(report: FolderStructureReport, root: Path | None = None) -> None:
    """Render folder structure violation report."""
    title = Text()
    title.append("Folder Structure  ")
    if report.violations:
        title.append(f"{len(report.violations)} violations", style="bold red")
    else:
        title.append("clean", style="bold green")
    title.append(
        f"  ({report.folders_checked} folders checked, {report.rules_applied} rules)",
        style="dim",
    )

    if not report.violations:
        console.print(
            Panel(
                Text("All folders within structure rules ✓", style="bold green"),
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
    table.add_column("Folder", style="bold red", min_width=30, no_wrap=True)
    table.add_column("Rule", style="dim", no_wrap=True)
    table.add_column("Violations", no_wrap=False)

    for v in sorted(report.violations, key=lambda x: str(x.folder)):
        try:
            folder_display = v.folder.relative_to(root) if root else v.folder
        except ValueError:
            folder_display = v.folder
        table.add_row(
            str(folder_display) + "/",
            f"[dim]{v.rule.pattern}[/dim]",
            "\n".join(f"[red]✗[/red] {r}" for r in v.reasons),
        )
        if v.rule.message:
            table.add_row("", "", f"[yellow italic]{v.rule.message}[/yellow italic]")

    console.print(Panel(table, title=str(title)))


def render_repo_rules(report, root: "Path | None" = None) -> None:  # type: ignore[type-arg]
    """Render repo rules violation report."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    title = Text()
    title.append("Repo Rules  ")
    issues = report.issues if hasattr(report, "issues") else []
    if issues:
        errors = [i for i in issues if i.get("severity") == "error"]
        warnings = [i for i in issues if i.get("severity") != "error"]
        title.append(
            f"{len(errors)} errors  {len(warnings)} warnings",
            style="bold red" if errors else "bold yellow",
        )
    else:
        title.append("clean", style="bold green")

    if not issues:
        console.print(Panel(Text("No rule violations ✓", style="bold green"), title=str(title)))
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    table.add_column("Severity", style="bold", no_wrap=True, width=8)
    table.add_column("Rule", no_wrap=True)
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Line", style="dim", no_wrap=True, width=5)
    table.add_column("Match", no_wrap=False)

    for issue in issues:
        sev = issue.get("severity", "warning")
        color = "red" if sev == "error" else "yellow"
        try:
            from pathlib import Path as _Path

            fp = _Path(issue.get("file", ""))
            file_display = str(fp.relative_to(root)) if root else str(fp)
        except ValueError:
            file_display = issue.get("file", "")
        table.add_row(
            f"[{color}]{sev}[/{color}]",
            issue.get("rule", ""),
            file_display,
            str(issue.get("line", "")),
            issue.get("matched", ""),
        )

    console.print(Panel(table, title=str(title)))
