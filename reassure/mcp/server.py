"""
MCP server for operation-reassurance.

Exposes every registered Analyzer as an LLM-callable tool.
Works with Claude Code, Cursor, Windsurf, and any MCP-compatible client.

Usage — add to your project's .mcp.json:

    {
      "mcpServers": {
        "reassure": {
          "command": "python3",
          "args": ["-m", "reassure.mcp.server"],
          "cwd": "/path/to/operation-reassurance"
        }
      }
    }

Or globally in ~/.claude/mcp.json for Claude Code.

Each Analyzer registered in BUILTIN_ANALYZERS automatically becomes a tool.
Custom analyzers can be added via .reassure.toml [analyzers] custom = [...].
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from reassure.analyzers.blast_radius import (
    BlastRadiusAnalyzer,
    analyze_blast_radius,
    get_diff,
    parse_diff,
)
from reassure.analyzers.observability import ObservabilityAnalyzer
from reassure.analyzers.solid import SolidAnalyzer
from reassure.analyzers.test_coverage import CoverageAnalyzer
from reassure.core.repo_walker import walk_repo
from reassure.plugin import Analyzer

mcp = FastMCP(
    "reassure",
    instructions=(
        "Repo health observatory. Use these tools to understand a codebase's "
        "test coverage, observability gaps, and structural health before making changes. "
        "Always call with an absolute path to the repo root."
    ),
)

BUILTIN_ANALYZERS: list[Analyzer] = [
    CoverageAnalyzer(),
    ObservabilityAnalyzer(),
    SolidAnalyzer(),
    BlastRadiusAnalyzer(),
]


def _register(analyzer: Analyzer) -> None:
    """Register one Analyzer as an MCP tool."""

    # Capture in closure
    _analyzer = analyzer

    @mcp.tool(name=_analyzer.name, description=_analyzer.description)
    def _tool(path: str) -> dict:
        """Run the analyzer against the repo at `path` and return structured results."""
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            return {"error": f"Not a directory: {path}"}
        index = walk_repo(root)
        result = _analyzer.analyze(index)
        return {
            "summary": result.summary,
            "issues": result.issues,
        }


for _a in BUILTIN_ANALYZERS:
    _register(_a)


@mcp.tool(
    name="list_analyzers", description="List all available reassure analyzers and what they check."
)
def list_analyzers() -> list[dict]:
    return [{"name": a.name, "description": a.description} for a in BUILTIN_ANALYZERS]


@mcp.tool(
    name="get_symbol_map",
    description="Return all named symbols (functions, classes, methods) found in a repo. Useful before writing tests or refactoring.",
)
def get_symbol_map(path: str, lang: str | None = None) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"error": f"Not a directory: {path}"}
    index = walk_repo(root)
    symbols = [
        {
            "name": s.name,
            "kind": s.kind,
            "file": str(s.file.relative_to(root)),
            "line": s.line_start,
            "lang": s.lang,
            "parent_class": s.parent_class,
            "is_public": s.is_public,
            "is_async": s.is_async,
        }
        for s in index.all_symbols
        if lang is None or s.lang == lang
    ]
    return {"total": len(symbols), "symbols": symbols}


@mcp.tool(
    name="get_dark_modules",
    description="Return files where every public function has zero production observability instrumentation.",
)
def get_dark_modules(path: str) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"error": f"Not a directory: {path}"}
    index = walk_repo(root)
    analyzer = ObservabilityAnalyzer()
    result = analyzer.analyze(index)
    return {
        "summary": result.summary,
        "dark_modules": [str(Path(p).relative_to(root)) for p in result.data.dark_module_paths],
    }


@mcp.tool(
    name="get_uncovered_symbols",
    description="Return public symbols that have no test coverage — no unit, integration, or e2e tests reference them.",
)
def get_uncovered_symbols(path: str) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"error": f"Not a directory: {path}"}
    index = walk_repo(root)
    analyzer = CoverageAnalyzer()
    result = analyzer.analyze(index)
    return {
        "summary": result.summary,
        "uncovered": result.issues,
    }


@mcp.tool(
    name="get_blast_radius",
    description=(
        "Given a repo path and a git base ref, returns which symbols changed, "
        "who calls them, and which callers have no test coverage. "
        "The uncovered_callers list is the dangerous part — those will regress silently."
    ),
)
def get_blast_radius(path: str, base: str = "main", transitive_depth: int = 2) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"error": f"Not a directory: {path}"}
    try:
        diff_text = get_diff(root, base)
    except Exception as e:
        return {"error": str(e)}
    if not diff_text.strip():
        return {"summary": f"No changes vs {base}", "affected_symbols": [], "uncovered_callers": []}

    index = walk_repo(root)
    diff_hunks = parse_diff(diff_text, root)
    report = analyze_blast_radius(index, diff_hunks, base=base, transitive_depth=transitive_depth)

    return {
        "summary": (
            f"{len(report.affected_symbols)} symbols changed, "
            f"{report.total_callers} callers, "
            f"{report.total_uncovered_callers} uncovered"
        ),
        "affected_symbols": [
            {
                "symbol": a.symbol.name,
                "file": str(a.symbol.file.relative_to(root)),
                "line_start": a.symbol.line_start,
                "line_end": a.symbol.line_end,
                "direct_callers": [
                    {
                        "name": c.symbol.name,
                        "file": str(c.file.relative_to(root)),
                        "covered": c.is_covered,
                    }
                    for c in a.direct_callers
                ],
                "transitive_callers": [
                    {
                        "name": c.symbol.name,
                        "file": str(c.file.relative_to(root)),
                        "covered": c.is_covered,
                    }
                    for c in a.transitive_callers
                ],
            }
            for a in report.affected_symbols
        ],
        "uncovered_callers": [
            {
                "changed_symbol": a.symbol.name,
                "caller": c.symbol.name,
                "caller_file": str(c.file.relative_to(root)),
            }
            for a in report.affected_symbols
            for c in a.uncovered_callers
        ],
    }


if __name__ == "__main__":
    mcp.run()
