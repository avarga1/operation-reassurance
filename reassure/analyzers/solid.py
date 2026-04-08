"""
SOLID / SoC health analyzer.

Detects structural code health issues using CST metrics:

  - God files:    too many LOC, functions, or classes in one file
  - God classes:  too many methods, likely violating SRP
  - God functions: high cyclomatic complexity (too many branches)
  - Coupling:     files importing too many unrelated modules
  - Circular imports: A imports B imports A (via dependency graph)
  - SoC violations: a single class touching too many distinct concern domains
                    (heuristic: import diversity score)

All thresholds are configurable via .reassure.toml [thresholds].
"""

from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol


@dataclass
class GodFile:
    file: FileRecord
    reasons: list[str]  # e.g. ["500+ LOC", "23 functions"]


@dataclass
class GodClass:
    symbol: Symbol
    method_count: int
    reasons: list[str]


@dataclass
class GodFunction:
    symbol: Symbol
    complexity: int  # cyclomatic complexity score


@dataclass
class CircularImport:
    cycle: list[Path]  # the import cycle path


@dataclass
class SolidReport:
    god_files: list[GodFile] = field(default_factory=list)
    god_classes: list[GodClass] = field(default_factory=list)
    god_functions: list[GodFunction] = field(default_factory=list)
    circular_imports: list[CircularImport] = field(default_factory=list)
    dependency_graph: nx.DiGraph | None = None

    @property
    def has_issues(self) -> bool:
        return any(
            [
                self.god_files,
                self.god_classes,
                self.god_functions,
                self.circular_imports,
            ]
        )


def analyze_solid(
    index: RepoIndex,
    god_file_loc: int = 500,
    god_file_functions: int = 20,
    god_class_methods: int = 15,
    max_complexity: int = 10,
) -> SolidReport:
    """
    Run all SOLID / SoC health checks against the repo index.
    Returns a SolidReport with all detected issues.
    """
    # TODO: implement
    # 1. detect_god_files: LOC + function count per file
    # 2. detect_god_classes: method count per class symbol
    # 3. detect_god_functions: cyclomatic complexity via branch node counting
    # 4. build_dependency_graph: file → imported files (via import statements)
    # 5. detect_circular_imports: nx.simple_cycles on the dependency graph
    raise NotImplementedError


def compute_cyclomatic_complexity(symbol: Symbol, source: str) -> int:
    """
    Compute cyclomatic complexity for a function symbol.

    Cyclomatic complexity = 1 + number of decision points (branches).
    Decision nodes: if, elif, for, while, case, except, and, or, ternary.
    """
    # TODO: implement
    # Walk the symbol's CST subtree, count branch nodes by type
    raise NotImplementedError


def build_dependency_graph(index: RepoIndex) -> nx.DiGraph:
    """
    Build a directed import graph across all source files.
    Node = file path. Edge A→B = A imports B.
    """
    # TODO: implement
    # Parse import statements from each file's CST
    # Resolve relative imports to absolute paths
    raise NotImplementedError
