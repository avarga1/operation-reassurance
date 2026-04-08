"""
CLI entry point for operation-reassurance.

Usage:
  reassure ./src                        # full analysis, terminal output
  reassure ./src --only coverage        # single analyzer
  reassure ./src --output json          # JSON to stdout
  reassure ./src --output json -o report.json
  reassure ./src --config .reassure.toml
  streamlit run reassure/gui/app.py     # GUI dashboard
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

ANALYZERS = ["coverage", "observability", "dead_code", "solid", "metrics"]
console = Console()


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--only",
    type=click.Choice(ANALYZERS),
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
@click.version_option()
def main(
    path: Path,
    only: tuple[str, ...],
    output: str,
    out: Path | None,
    config: Path | None,
    show_passed: bool,
) -> None:
    """Analyze repo health at PATH using static CST/AST analysis."""
    from reassure.analyzers.observability import analyze_observability
    from reassure.analyzers.test_coverage import analyze_coverage
    from reassure.classifiers.test_type import classify_test_file
    from reassure.core.repo_walker import walk_repo
    from reassure.output.terminal import render_coverage, render_observability

    run = set(only) if only else {"coverage", "observability"}

    with console.status(f"[bold cyan]Walking {path} …"):
        index = walk_repo(path)

    console.print(
        f"  [dim]{len(index.files)} files[/dim]  "
        f"[dim]{len(index.all_symbols)} symbols[/dim]  "
        f"[dim]{len(index.test_files)} test files[/dim]"
    )

    results: dict[str, Any] = {}

    if "coverage" in run:
        classifications = {
            f.path: classify_test_file(f.path, list(f.imports), []) for f in index.test_files
        }
        report = analyze_coverage(index, classifications)

        if output == "terminal":
            render_coverage(report, show_passed=show_passed, root=path)
        else:
            results["coverage"] = _coverage_to_dict(report)

    if "observability" in run:
        obs_report = analyze_observability(index)
        if output == "terminal":
            render_observability(obs_report, root=path)
        else:
            results["observability"] = {
                "dark_pct": obs_report.dark_pct,
                "dark_functions": obs_report.dark_functions,
                "total_functions": obs_report.total_functions,
                "dark_modules": [str(p) for p in obs_report.dark_module_paths],
                "gaps": [
                    {"name": g.symbol.name, "file": str(g.symbol.file), "line": g.symbol.line_start}
                    for g in obs_report.gaps
                ],
            }

    if output == "json" or out:
        payload = json.dumps(results, indent=2, default=str)
        if out:
            out.write_text(payload)
            console.print(f"[green]Written to {out}[/green]")
        else:
            sys.stdout.write(payload + "\n")


def _coverage_to_dict(report: "CoverageReport") -> dict[str, Any]:  # noqa: F821
    return {
        "coverage_pct": report.coverage_pct,
        "total_symbols": report.total_symbols,
        "covered_symbols": report.covered_symbols,
        "uncovered": [
            {
                "name": sc.symbol.name,
                "kind": sc.symbol.kind,
                "file": str(sc.symbol.file),
                "line_start": sc.symbol.line_start,
            }
            for sc in report.uncovered
        ],
    }


if __name__ == "__main__":
    main()
