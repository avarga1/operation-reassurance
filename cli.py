"""
CLI entry point for operation-reassurance.

Usage:
  reassure ./src                        # full analysis, terminal output
  reassure ./src --only coverage        # single analyzer
  reassure ./src --output json          # JSON to stdout
  reassure ./src --output json -o report.json

  reassure init                         # scaffold a new project (interactive)
  reassure init --name my-app --path ./my-app --stack flutter-riverpod-pg
  reassure init --path ./existing-repo  # detect stack, install rules only
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from reassure.analyzers.observability import ObservabilityAnalyzer
from reassure.analyzers.taxonomy import TaxonomyAnalyzer
from reassure.analyzers.test_coverage import CoverageAnalyzer
from reassure.plugin import Analyzer, load_analyzer

BUILTIN_ANALYZERS: list[Analyzer] = [
    CoverageAnalyzer(),
    ObservabilityAnalyzer(),
    TaxonomyAnalyzer(),
]
ANALYZER_NAMES = [a.name for a in BUILTIN_ANALYZERS]

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """operation-reassurance — structural memory for LLM code generation."""


# ── analyse ───────────────────────────────────────────────────────────────────

@main.command("analyse")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--only",
    type=click.Choice(ANALYZER_NAMES),
    multiple=True,
    help="Run only specific analyzers. Can be repeated.",
)
@click.option(
    "--output", "-f",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    show_default=True,
)
@click.option(
    "--out", "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write JSON output to file (implies --output json).",
)
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to .reassure.toml config file.",
)
@click.option("--show-passed", is_flag=True, default=False, help="Show covered symbols too.")
def analyse(
    path: Path,
    only: tuple[str, ...],
    output: str,
    out: Path | None,
    config: Path | None,
    show_passed: bool,
) -> None:
    """Analyze repo health at PATH using static CST/AST analysis."""
    from reassure.core.repo_walker import walk_repo

    analyzers = list(BUILTIN_ANALYZERS)
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


# ── init ──────────────────────────────────────────────────────────────────────

@main.command("init")
@click.option("--name",  default=None, help="Project name.")
@click.option("--path",  "target", default=".", type=click.Path(path_type=Path), help="Destination directory.")
@click.option("--stack", default=None, help="Template key (e.g. flutter-riverpod-pg). Skip for interactive.")
@click.option("--rules-only", is_flag=True, default=False, help="Install .reassure.toml only, no scaffold.")
def init(
    name: str | None,
    target: Path,
    stack: str | None,
    rules_only: bool,
) -> None:
    """Scaffold a new project or install rules into an existing one."""
    from reassure.init.detector import KNOWN_TEMPLATES, detect
    from reassure.init.scaffolder import install_rules, list_templates, scaffold

    target = target.resolve()

    # ── detect existing stack ─────────────────────────────────────────────────
    profile = detect(target)

    if profile.warnings:
        for w in profile.warnings:
            console.print(f"  [yellow]⚠[/yellow]  {w}")

    # ── rules-only mode (existing project) ────────────────────────────────────
    if rules_only or (target.exists() and any(target.iterdir()) and not name):
        if profile.is_known:
            console.print(f"  [dim]Detected:[/dim] [bold]{profile.description}[/bold]")
            dest = install_rules(profile, target)
            console.print(f"  [green]✓[/green]  {dest.relative_to(target)} written")
        else:
            console.print(
                f"  [yellow]Could not detect a known stack at {target}.[/yellow]\n"
                "  Run [bold]reassure init --name <name> --stack <key>[/bold] to scaffold from scratch.\n"
                f"  Available stacks: {', '.join(list_templates())}"
            )
        return

    # ── new project scaffolding ───────────────────────────────────────────────
    if not name:
        name = click.prompt("  Project name")

    if not stack and profile.is_known:
        console.print(f"  [dim]Detected:[/dim] [bold]{profile.description}[/bold]")
        use_detected = click.confirm(f"  Use {profile.template_key}?", default=True)
        stack = profile.template_key if use_detected else None

    if not stack:
        choices = list_templates()
        console.print("  Available stacks:")
        for i, key in enumerate(choices, 1):
            label = KNOWN_TEMPLATES.get(key, key)
            console.print(f"    [bold]{i}[/bold]. {key}  [dim]{label}[/dim]")
        idx = click.prompt("  Pick a stack", type=click.IntRange(1, len(choices)))
        stack = choices[idx - 1]

    dest = target / name if target.name != name else target

    console.print(f"  Scaffolding [bold]{stack}[/bold] → {dest} …")
    created = scaffold(stack, dest, project_name=name)
    console.print(f"  [green]✓[/green]  {len(created)} files created")
    console.print()
    console.print("  Next steps:")
    console.print(f"    cd {dest}")
    console.print("    reassure analyse .")


if __name__ == "__main__":
    main()
