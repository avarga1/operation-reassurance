"""
CLI entry point for operation-reassurance.

Usage:
  reassure ./src                        # full analysis, terminal output
  reassure ./src --only coverage        # single analyzer
  reassure ./src --output json          # JSON to stdout
  reassure ./src --output json -o report.json
  streamlit run reassure/gui/app.py     # GUI dashboard
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from reassure.analyzers.blast_radius import BlastRadiusAnalyzer
from reassure.analyzers.observability import ObservabilityAnalyzer
from reassure.analyzers.solid import SolidAnalyzer
from reassure.analyzers.test_coverage import CoverageAnalyzer
from reassure.plugin import Analyzer, load_analyzer

BUILTIN_ANALYZERS: list[Analyzer] = [
    CoverageAnalyzer(),
    ObservabilityAnalyzer(),
    SolidAnalyzer(),
    BlastRadiusAnalyzer(),
]
ANALYZER_NAMES = [a.name for a in BUILTIN_ANALYZERS]

console = Console()


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--only",
    type=click.Choice(ANALYZER_NAMES),
    multiple=True,
    help="Run only specific analyzers. Can be repeated.",
)
@click.option(
    "--output",
    "-f",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    show_default=True,
)
@click.option(
    "--out",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write JSON output to file (implies --output json).",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to .reassure.toml config file.",
)
@click.option("--show-passed", is_flag=True, default=False, help="Show covered symbols too.")
@click.option(
    "--base", default="main", show_default=True, help="Git base ref for blast_radius diff."
)
@click.version_option()
def main(
    path: Path,
    only: tuple[str, ...],
    output: str,
    out: Path | None,
    config: Path | None,
    show_passed: bool,
    base: str,
) -> None:
    """Analyze repo health at PATH using static CST/AST analysis."""
    from reassure.core.repo_walker import walk_repo

    # Inject base ref into blast_radius analyzer
    analyzers = [
        BlastRadiusAnalyzer(base=base) if isinstance(a, BlastRadiusAnalyzer) else a
        for a in BUILTIN_ANALYZERS
    ]
    if config:
        import toml

        cfg = toml.load(config)
        for dotted in cfg.get("analyzers", {}).get("custom", []):
            analyzers.append(load_analyzer(dotted))

    run_names = set(only) if only else {a.name for a in analyzers}

    with console.status(f"[bold cyan]Walking {path} …"):
        index = walk_repo(path)

    console.print(
        f"  [dim]{len(index.files)} files[/dim]  "
        f"[dim]{len(index.all_symbols)} symbols[/dim]  "
        f"[dim]{len(index.test_files)} test files[/dim]"
    )

    results: dict[str, Any] = {}

    for analyzer in analyzers:
        if analyzer.name not in run_names:
            continue

        with console.status(f"[cyan]Running {analyzer.name} …"):
            result = analyzer.analyze(index)

        if output == "terminal":
            analyzer.render_terminal(result, root=path)
        else:
            results[analyzer.name] = {
                "summary": result.summary,
                "issues": result.issues,
            }

    if output == "json" or out:
        payload = json.dumps(results, indent=2, default=str)
        if out:
            out.write_text(payload)
            console.print(f"[green]Written to {out}[/green]")
        else:
            sys.stdout.write(payload + "\n")


if __name__ == "__main__":
    main()
