"""
Analyzer plugin protocol.

Any object implementing `Analyzer` can be registered with the pipeline and
will automatically appear as a CLI flag, a terminal section, and (once the
MCP server lands) an LLM-callable tool.

Implementing a custom analyzer
-------------------------------

    from pathlib import Path
    from reassure.plugin import Analyzer, AnalyzerResult
    from reassure.core.repo_walker import RepoIndex

    class MyAnalyzer:
        name = "my_analyzer"
        description = "Checks something interesting about the repo."

        def analyze(self, index: RepoIndex) -> AnalyzerResult:
            # ... your logic here ...
            return AnalyzerResult(
                name=self.name,
                summary="3 issues found",
                data={"issues": [...]},
            )

        def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
            from rich.console import Console
            Console().print(result.summary)

Drop it in `.reassure.toml` and it will be picked up automatically:

    [analyzers]
    custom = ["mypackage.analyzers.MyAnalyzer"]
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from reassure.core.repo_walker import RepoIndex


@dataclass
class AnalyzerResult:
    """Uniform output envelope returned by every analyzer."""

    name: str
    summary: str  # one-line summary for CLI header + MCP response
    data: Any = None  # analyzer-specific report object (CoverageReport, etc.)
    issues: list[dict[str, Any]] = field(default_factory=list)
    # issues is a flat list used by MCP tools and JSON export:
    # [{"symbol": "login", "file": "src/auth.py", "line": 12, "reason": "..."}]


@runtime_checkable
class Analyzer(Protocol):
    """
    Protocol every built-in and custom analyzer must satisfy.

    `name`        — snake_case identifier; becomes the CLI --only flag value
                    and the MCP tool name.
    `description` — one sentence shown in --help and MCP tool descriptions.
    """

    name: str
    description: str

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        """Run the analyzer against a RepoIndex and return a result."""
        ...

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        """Render the result to stdout using Rich."""
        ...


def load_analyzer(dotted_path: str) -> Analyzer:
    """
    Import and instantiate an analyzer from a dotted class path.

    Example:  "mypackage.analyzers.MyAnalyzer"
    """
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    instance = cls()
    if not isinstance(instance, Analyzer):
        raise TypeError(f"{dotted_path} does not implement the Analyzer protocol")
    return instance
