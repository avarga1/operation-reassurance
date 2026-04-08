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

from pathlib import Path

import click

ANALYZERS = ["coverage", "observability", "dead_code", "solid", "metrics"]


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
@click.option("--show-passed", is_flag=True, default=False, help="Show clean files too.")
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
    # TODO: implement
    # 1. Load config from .reassure.toml (auto-detect if not specified)
    # 2. Walk repo → RepoIndex
    # 3. Run selected analyzers
    # 4. Render via terminal or json_export
    raise NotImplementedError


if __name__ == "__main__":
    main()
