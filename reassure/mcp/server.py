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

from reassure.analyzers.observability import ObservabilityAnalyzer
from reassure.analyzers.taxonomy import (
    TaxonomyAnalyzer,
    _detect_default_rules,
    _rules_from_toml,
    check_file,
)
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
    TaxonomyAnalyzer(),
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
    name="check_taxonomy",
    description=(
        "Check whether a proposed file write violates taxonomy rules for this repo. "
        "Call this BEFORE writing to any file. Returns violations with the message to show "
        "if the write should be blocked. Returns empty list if the write is clean."
    ),
)
def check_taxonomy(path: str, proposed_content: str) -> dict:
    """
    path            — absolute path of the file being written (may not exist yet)
    proposed_content — the full content you are about to write
    """
    file_path = Path(path).expanduser().resolve()

    # Find repo root by walking up to find .reassure.toml or pubspec.yaml / Cargo.toml
    root = _find_repo_root(file_path)
    toml_path = root / ".reassure.toml" if root else None

    if toml_path and toml_path.exists():
        rules = _rules_from_toml(toml_path)
    elif root:
        rules = _detect_default_rules(root)
    else:
        rules = _detect_default_rules(file_path.parent)

    violations = check_file(file_path, proposed_content, rules)

    if not violations:
        return {"blocked": False, "violations": []}

    return {
        "blocked": True,
        "violations": [
            {
                "file": str(v.file),
                "rule_pattern": v.rule.pattern,
                "purpose": v.rule.purpose,
                "reasons": v.reasons,
                "message": v.rule.message,
            }
            for v in violations
        ],
    }


def _find_repo_root(start: Path) -> Path | None:
    """Walk up from start looking for .reassure.toml, pubspec.yaml, Cargo.toml, or pyproject.toml."""
    markers = {".reassure.toml", "pubspec.yaml", "Cargo.toml", "pyproject.toml", ".git"}
    current = start if start.is_dir() else start.parent
    for _ in range(10):
        if any((current / m).exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


if __name__ == "__main__":
    mcp.run()
