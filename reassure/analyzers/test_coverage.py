"""
Static test coverage analyzer.

For each source symbol, determines which test files reference it and
what type those tests are — without executing any code.

Resolution strategy:
  1. Direct name match: test file imports or calls `symbol.name`
  2. Fuzzy match: test file name mirrors source file name (test_foo.py → foo.py)
"""

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from reassure.classifiers.test_type import TestClassification, TestType
from reassure.core.parser import parse_file
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol
from reassure.plugin import AnalyzerResult


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

    @property
    def total_symbols(self) -> int:
        return len(self.symbols)

    @property
    def covered_symbols(self) -> int:
        return sum(1 for s in self.symbols if not s.is_uncovered)

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


class CoverageAnalyzer:
    """Plugin-protocol wrapper for the test coverage analyzer."""

    name = "coverage"
    description = "Finds public symbols with no test coverage, grouped by test type."

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        from reassure.classifiers.test_type import classify_test_file

        classifications = {
            f.path: classify_test_file(f.path, list(f.imports), []) for f in index.test_files
        }
        report = analyze_coverage(index, classifications)
        issues = [
            {
                "symbol": sc.symbol.name,
                "file": str(sc.symbol.file),
                "line": sc.symbol.line_start,
                "reason": "no tests",
            }
            for sc in report.uncovered
        ]
        return AnalyzerResult(
            name=self.name,
            summary=f"{report.coverage_pct}% coverage — {len(report.uncovered)} uncovered symbols",
            data=report,
            issues=issues,
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from reassure.output.terminal import render_coverage

        render_coverage(result.data, root=root)


def analyze_coverage(
    index: RepoIndex,
    classifications: dict[Path, TestClassification],
) -> CoverageReport:
    """
    Build a CoverageReport for the full repo index.

    For each source symbol, finds all test files that reference it
    and groups them by test type.
    """
    reference_map = _build_test_reference_map(index.test_files)

    symbol_coverages = []
    for symbol in index.all_symbols:
        tests_by_type: dict[TestType, list[Path]] = {}

        for test_file, refs in reference_map.items():
            if not _symbol_is_referenced(symbol, refs, test_file):
                continue

            classification = classifications.get(test_file)
            test_type = classification.primary if classification else TestType.UNKNOWN
            tests_by_type.setdefault(test_type, []).append(test_file)

        symbol_coverages.append(SymbolCoverage(symbol=symbol, tests_by_type=tests_by_type))

    return CoverageReport(symbols=symbol_coverages)


def _symbol_is_referenced(symbol: Symbol, refs: set[str], test_file: Path) -> bool:
    """
    Check if a symbol is referenced by a test file.

    Uses two strategies:
    1. Direct: symbol name appears in the test file's reference set
    2. Fuzzy: test file name matches source file name (test_foo.py → foo.py)
    """
    # Direct name match
    if symbol.name in refs:
        return True

    # Fuzzy: test_auth_service.py covers auth/service.py
    stem = test_file.stem.lower().removeprefix("test_").removesuffix("_test")
    return bool(
        stem
        and stem in symbol.file.stem.lower()
        and symbol.file.stem.lower() in {r.lower() for r in refs}
    )


def _build_test_reference_map(test_files: list[FileRecord]) -> dict[Path, set[str]]:
    """
    For each test file, extract the set of symbol names it references.

    Collects:
    - Imported names (from x import Foo, Bar)
    - Top-level module imports (import sqlalchemy)
    - Direct call identifiers (AuthService(), svc.login())
    """
    result: dict[Path, set[str]] = {}

    for record in test_files:
        parsed = parse_file(record.path)
        if parsed is None:
            result[record.path] = set()
            continue

        tree, source = parsed
        refs: set[str] = set()
        _collect_references(tree.root_node, source, refs)
        result[record.path] = refs

    return result


def _collect_references(node: Node, source: str, refs: set[str]) -> None:
    """Recursively walk a CST node and collect all referenced identifiers."""
    if node.type == "import_statement":
        # import sqlalchemy  →  "sqlalchemy"
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                name = _first_identifier(child, source)
                if name:
                    refs.add(name)

    elif node.type == "import_from_statement":
        # from src.auth.service import AuthService, login
        # collect each imported name
        collecting = False
        for child in node.children:
            if child.type == "import":
                collecting = True
                continue
            if collecting and child.type in ("dotted_name", "aliased_import", "wildcard_import"):
                name = _first_identifier(child, source)
                if name:
                    refs.add(name)

    elif node.type == "call":
        # AuthService() or svc.login() — collect the callable name
        func = node.child_by_field_name("function")
        if func:
            if func.type == "identifier":
                refs.add(_node_text(func, source))
            elif func.type == "attribute":
                # svc.login → collect "login"
                attr = func.child_by_field_name("attribute")
                if attr:
                    refs.add(_node_text(attr, source))

    for child in node.children:
        _collect_references(child, source, refs)


def _first_identifier(node: Node, source: str) -> str | None:
    """Return the text of the first identifier child of a node."""
    if node.type == "identifier":
        return _node_text(node, source)
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return None


def _node_text(node: Node, source: str) -> str:
    """Extract node text using byte offsets (correct for multi-byte Unicode)."""
    return source.encode()[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
