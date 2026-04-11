"""Unit tests for the test coverage analyzer and reference extractor."""

from pathlib import Path

from reassure.analyzers.test_coverage import (
    CoverageReport,
    SymbolCoverage,
    _collect_references,
    analyze_coverage,
)
from reassure.classifiers.test_type import TestType
from reassure.core.parser import parse_source
from reassure.core.repo_walker import walk_repo
from reassure.core.symbol_map import Symbol

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_repo"


# ── Reference extraction ─────────────────────────────────────────────────────


class TestCollectReferences:
    def _refs(self, source: str) -> set[str]:
        tree = parse_source(source, "python")
        refs: set[str] = set()
        _collect_references(tree.root_node, source, refs)
        return refs

    def test_plain_import(self):
        assert "sqlalchemy" in self._refs("import sqlalchemy")

    def test_from_import(self):
        refs = self._refs("from src.auth.service import AuthService, login")
        assert "AuthService" in refs
        assert "login" in refs

    def test_call_identifier(self):
        refs = self._refs("AuthService()")
        assert "AuthService" in refs

    def test_method_call(self):
        refs = self._refs("svc.login('admin', 'secret')")
        assert "login" in refs

    def test_chained_calls(self):
        refs = self._refs("AuthService().logout(1)")
        assert "AuthService" in refs
        assert "logout" in refs

    def test_multiple_imports(self):
        src = "from auth import Login, Logout, Reset"
        refs = self._refs(src)
        assert "Login" in refs
        assert "Logout" in refs
        assert "Reset" in refs


# ── Full analyzer against fixture repo ───────────────────────────────────────


class TestAnalyzeCoverage:
    def setup_method(self):
        self.index = walk_repo(FIXTURE)
        # Build classifications from the fixture test files
        from reassure.classifiers.test_type import classify_test_file

        self.classifications = {
            f.path: classify_test_file(f.path, list(f.imports), []) for f in self.index.test_files
        }

    def test_finds_source_symbols(self):
        names = [s.name for s in self.index.all_symbols]
        assert "AuthService" in names
        assert "login" in names
        assert "reset_password" in names

    def test_login_is_covered(self):
        report = analyze_coverage(self.index, self.classifications)
        login_cov = next(s for s in report.symbols if s.symbol.name == "login")
        assert not login_cov.is_uncovered

    def test_reset_password_is_uncovered(self):
        report = analyze_coverage(self.index, self.classifications)
        reset = next(s for s in report.symbols if s.symbol.name == "reset_password")
        assert reset.is_uncovered

    def test_coverage_pct_is_partial(self):
        report = analyze_coverage(self.index, self.classifications)
        assert 0 < report.coverage_pct < 100

    def test_uncovered_list_not_empty(self):
        report = analyze_coverage(self.index, self.classifications)
        assert len(report.uncovered) > 0


# ── SymbolCoverage properties ─────────────────────────────────────────────────


class TestSymbolCoverage:
    def _sym(self):
        return Symbol(
            name="foo",
            kind="function",
            file=Path("src/foo.py"),
            line_start=1,
            line_end=5,
            lang="python",
        )

    def test_uncovered_when_no_tests(self):
        sc = SymbolCoverage(symbol=self._sym())
        assert sc.is_uncovered
        assert sc.total_tests == 0

    def test_covered_when_has_tests(self):
        sc = SymbolCoverage(
            symbol=self._sym(),
            tests_by_type={TestType.UNIT: [Path("tests/test_foo.py")]},
        )
        assert not sc.is_uncovered
        assert sc.total_tests == 1

    def test_has_unit_tests(self):
        sc = SymbolCoverage(
            symbol=self._sym(),
            tests_by_type={TestType.UNIT: [Path("tests/test_foo.py")]},
        )
        assert sc.has_unit_tests


# ── CoverageReport properties ─────────────────────────────────────────────────


class TestCoverageReport:
    def _sym(self, name: str):
        return Symbol(
            name=name,
            kind="function",
            file=Path("src/foo.py"),
            line_start=1,
            line_end=5,
            lang="python",
        )

    def test_coverage_pct_all_covered(self):
        symbols = [
            SymbolCoverage(
                symbol=self._sym("a"),
                tests_by_type={TestType.UNIT: [Path("t.py")]},
            )
        ]
        report = CoverageReport(symbols=symbols)
        assert report.coverage_pct == 100.0

    def test_coverage_pct_none_covered(self):
        symbols = [SymbolCoverage(symbol=self._sym("a"))]
        report = CoverageReport(symbols=symbols)
        assert report.coverage_pct == 0.0

    def test_unit_only_detection(self):
        symbols = [
            SymbolCoverage(
                symbol=self._sym("a"),
                tests_by_type={TestType.UNIT: [Path("t.py")]},
            )
        ]
        report = CoverageReport(symbols=symbols)
        assert len(report.unit_only) == 1
