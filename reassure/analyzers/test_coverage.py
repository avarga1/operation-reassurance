"""
Static test coverage analyzer.

For each source symbol, determines which test files reference it and
what type those tests are — without executing any code.

Resolution strategy:
  1. Direct name match: test file imports or calls `symbol.name`
  2. Class-level match: test file imports the parent class
  3. Fuzzy match: test file name mirrors source file name (test_foo.py → foo.py)

Output is a CoverageReport mapping each symbol to its test coverage.
"""

from dataclasses import dataclass, field
from pathlib import Path

from reassure.classifiers.test_type import TestClassification, TestType
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol


@dataclass
class SymbolCoverage:
    symbol: Symbol
    tests_by_type: dict[TestType, list[Path]] = field(default_factory=dict)

    @property
    def total_tests(self) -> int:
        return sum(len(v) for v in self.tests_by_type.values())

    @property
    def is_uncovered(self) -> bool:
        return self.total_tests == 0

    @property
    def has_unit_tests(self) -> bool:
        return bool(self.tests_by_type.get(TestType.UNIT))


@dataclass
class CoverageReport:
    symbols: list[SymbolCoverage]
    total_symbols: int
    covered_symbols: int

    @property
    def coverage_pct(self) -> float:
        if self.total_symbols == 0:
            return 100.0
        return round(self.covered_symbols / self.total_symbols * 100, 1)

    @property
    def uncovered(self) -> list[SymbolCoverage]:
        return [s for s in self.symbols if s.is_uncovered]

    @property
    def unit_only(self) -> list[SymbolCoverage]:
        """Symbols covered only by unit tests — no integration or e2e."""
        return [
            s
            for s in self.symbols
            if s.has_unit_tests
            and not any(k in s.tests_by_type for k in [TestType.INTEGRATION, TestType.E2E])
        ]


def analyze_coverage(
    index: RepoIndex,
    classifications: dict[Path, TestClassification],
) -> CoverageReport:
    """
    Build a CoverageReport for the full repo index.

    For each source symbol, finds all test files that reference it
    and groups them by test type.
    """
    # TODO: implement
    # 1. Build a lookup: test_file → set of symbol names it references
    #    (via import + call site analysis on the test CST)
    # 2. For each source symbol, find matching test files
    # 3. Group by TestType using the classifications map
    # 4. Build SymbolCoverage records
    raise NotImplementedError


def _build_test_reference_map(
    test_files: list[FileRecord],
) -> dict[Path, set[str]]:
    """
    For each test file, extract the set of symbol names it references.
    Uses import analysis + function call site extraction from the CST.
    """
    # TODO: implement
    # Walk test CST: collect imported names + all identifier nodes in call positions
    raise NotImplementedError
