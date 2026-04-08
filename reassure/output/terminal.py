"""
Rich terminal renderer.

Renders all analyzer reports to the terminal using rich tables, panels,
and color-coded output. Each section is a separate render function so
CLI callers can pick what to show.
"""

from rich.console import Console
from rich.text import Text

from reassure.analyzers.dead_code import DeadCodeReport
from reassure.analyzers.metrics import RepoMetrics
from reassure.analyzers.observability import ObservabilityReport
from reassure.analyzers.solid import SolidReport
from reassure.analyzers.test_coverage import CoverageReport

console = Console()


def render_summary(
    coverage: CoverageReport,
    observability: ObservabilityReport,
    dead_code: DeadCodeReport,
    solid: SolidReport,
    metrics: RepoMetrics,
) -> None:
    """Render a full repo health summary to the terminal."""
    # TODO: implement
    # Print header panel, then each section
    raise NotImplementedError


def render_coverage(report: CoverageReport, show_passed: bool = False) -> None:
    """
    Render test coverage report.

    Shows per-symbol coverage matrix with test type columns.
    Highlights uncovered symbols in red, unit-only in yellow.
    """
    # TODO: implement
    # Table: Symbol | File | unit | integration | e2e | smoke | security
    raise NotImplementedError


def render_observability(report: ObservabilityReport) -> None:
    """Render observability gap report — dark functions and modules."""
    # TODO: implement
    raise NotImplementedError


def render_dead_code(report: DeadCodeReport) -> None:
    """Render dead code candidates grouped by confidence level."""
    # TODO: implement
    raise NotImplementedError


def render_solid(report: SolidReport) -> None:
    """
    Render SOLID / SoC health issues.

    Sections: god files, god classes, god functions, circular imports.
    """
    # TODO: implement
    raise NotImplementedError


def render_metrics(metrics: RepoMetrics) -> None:
    """Render structural metrics: LOC breakdown, language distribution, churn hotspots."""
    # TODO: implement
    raise NotImplementedError


def _status_badge(covered: bool) -> Text:
    return Text("✓", style="green bold") if covered else Text("✗", style="red bold")
