"""
Dead code analyzer.

Finds symbols that are defined but never referenced anywhere in the repo.

Strategy:
  1. Build a full symbol definition map (all functions, classes, methods)
  2. Build a full reference map (all identifier usages across all files)
  3. Symbols in definitions but not in references → dead code candidates

Caveats (documented, not silently ignored):
  - Dynamic dispatch (__getattr__, getattr(obj, name)) cannot be resolved statically
  - Entry points (main, CLI handlers, exported __all__) should be whitelisted
  - Dunder methods are excluded by default (__init__, __str__, etc.)
  - Public API symbols in libraries may be intentionally unused internally
"""

from dataclasses import dataclass

from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol


@dataclass
class DeadSymbol:
    symbol: Symbol
    confidence: str  # "high" | "medium" | "low"
    caveat: str | None  # reason confidence isn't high


@dataclass
class DeadCodeReport:
    dead: list[DeadSymbol]
    total_symbols: int

    @property
    def high_confidence(self) -> list[DeadSymbol]:
        return [d for d in self.dead if d.confidence == "high"]


def analyze_dead_code(
    index: RepoIndex,
    entry_points: list[str] | None = None,
) -> DeadCodeReport:
    """
    Find dead code across the repo.

    entry_points: symbol names to treat as roots (always considered alive),
    e.g. ["main", "app", "handler"]. Reads from .reassure.toml if not provided.
    """
    # TODO: implement
    # 1. _build_definition_set: all symbol names from index.source_files
    # 2. _build_reference_set: all identifiers used in call/import positions
    # 3. definition_set - reference_set - entry_points - dunders = candidates
    # 4. Assign confidence based on symbol type and visibility
    raise NotImplementedError


def _build_reference_set(index: RepoIndex) -> set[str]:
    """
    Walk all files (source + test) and collect every identifier that appears
    in a call, import, or attribute access position.
    """
    # TODO: implement CST walk for reference extraction
    raise NotImplementedError


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")
