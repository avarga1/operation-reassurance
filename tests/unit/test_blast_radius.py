"""
Unit tests for the blast radius analyzer.

Tests the three core operations independently:
  1. parse_diff — unified diff text → {file: [(start, end)]}
  2. symbols_in_hunks — line range overlap against symbol map
  3. build_reference_graph — inverted call graph
  4. Full analyze_blast_radius against a controlled fixture index
"""

from pathlib import Path

from reassure.analyzers.blast_radius import (
    AffectedSymbol,
    BlastRadiusReport,
    analyze_blast_radius,
    parse_diff,
    symbols_in_hunks,
)
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol

FIXTURE_ROOT = Path("/repo")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sym(name: str, file: str, start: int, end: int, kind: str = "function") -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=FIXTURE_ROOT / file,
        line_start=start,
        line_end=end,
        lang="python",
        is_public=True,
    )


def _record(path: str, symbols: list[Symbol], loc: int = 100, source: str = "") -> FileRecord:
    return FileRecord(
        path=FIXTURE_ROOT / path,
        lang="python",
        symbols=symbols,
        loc=loc,
        source=source,
    )


# ── parse_diff ────────────────────────────────────────────────────────────────


class TestParseDiff:
    def test_single_hunk(self):
        diff = (
            "diff --git a/src/auth.py b/src/auth.py\n"
            "--- a/src/auth.py\n"
            "+++ b/src/auth.py\n"
            "@@ -10,5 +10,7 @@ class AuthService:\n"
            "+    new line\n"
        )
        result = parse_diff(diff, Path("/repo"))
        assert Path("/repo/src/auth.py") in result
        hunks = result[Path("/repo/src/auth.py")]
        assert len(hunks) == 1
        start, end = hunks[0]
        assert start == 10
        assert end == 16  # 10 + 7 - 1

    def test_multiple_files(self):
        diff = "+++ b/src/auth.py\n@@ -1,3 +1,4 @@\n+++ b/src/user.py\n@@ -5,2 +5,3 @@\n"
        result = parse_diff(diff, Path("/repo"))
        assert Path("/repo/src/auth.py") in result
        assert Path("/repo/src/user.py") in result

    def test_empty_diff(self):
        assert parse_diff("", Path("/repo")) == {}

    def test_deletion_only_hunk_skipped(self):
        # @@ -10,3 +10,0 @@ — count=0 means pure deletion, skip
        diff = "+++ b/src/auth.py\n@@ -10,3 +10,0 @@\n"
        result = parse_diff(diff, Path("/repo"))
        # File present but hunk has count=0, so no ranges
        assert result.get(Path("/repo/src/auth.py"), []) == []

    def test_single_line_hunk(self):
        # @@ -5 +5 @@ — no comma means count defaults to 1
        diff = "+++ b/src/auth.py\n@@ -5 +5 @@\n"
        result = parse_diff(diff, Path("/repo"))
        hunks = result.get(Path("/repo/src/auth.py"), [])
        assert hunks == [(5, 5)]


# ── symbols_in_hunks ──────────────────────────────────────────────────────────


class TestSymbolsInHunks:
    def _record_with(self, *symbols):
        return FileRecord(
            path=FIXTURE_ROOT / "src/auth.py",
            lang="python",
            symbols=list(symbols),
            loc=200,
        )

    def test_overlapping_symbol_returned(self):
        sym = _sym("login", "src/auth.py", 10, 30)
        record = self._record_with(sym)
        result = symbols_in_hunks(record, [(15, 20)])
        assert sym in result

    def test_non_overlapping_symbol_excluded(self):
        sym = _sym("login", "src/auth.py", 10, 20)
        record = self._record_with(sym)
        result = symbols_in_hunks(record, [(30, 40)])
        assert sym not in result

    def test_symbol_exactly_at_hunk_boundary(self):
        sym = _sym("login", "src/auth.py", 10, 20)
        record = self._record_with(sym)
        # hunk ends exactly at symbol start
        assert sym in symbols_in_hunks(record, [(5, 10)])
        # hunk starts exactly at symbol end
        assert sym in symbols_in_hunks(record, [(20, 30)])

    def test_symbol_spanning_multiple_hunks(self):
        sym = _sym("big_func", "src/auth.py", 1, 100)
        record = self._record_with(sym)
        result = symbols_in_hunks(record, [(10, 20), (50, 60)])
        assert sym in result
        # Only counted once despite matching two hunks
        assert result.count(sym) == 1

    def test_multiple_symbols_partial_overlap(self):
        s1 = _sym("login", "src/auth.py", 10, 30)
        s2 = _sym("logout", "src/auth.py", 50, 70)
        record = self._record_with(s1, s2)
        result = symbols_in_hunks(record, [(15, 20)])
        assert s1 in result
        assert s2 not in result

    def test_empty_hunks(self):
        sym = _sym("login", "src/auth.py", 10, 30)
        record = self._record_with(sym)
        assert symbols_in_hunks(record, []) == []


# ── analyze_blast_radius ──────────────────────────────────────────────────────


class TestAnalyzeBlastRadius:
    """
    Controlled fixture: auth.py defines `login`, user_page.py calls `login`.
    Diff touches auth.py:login. Expected: user_page._load shows up as a caller.
    """

    def _make_index(self) -> RepoIndex:
        login_sym = _sym("login", "src/auth.py", 10, 30)
        load_sym = _sym("_load", "src/user_page.py", 5, 20, kind="method")
        load_sym.parent_class = "UserPage"

        src_record = _record("src/auth.py", [login_sym], source="def login(): pass\n")
        # user_page.py calls login — its source references the name
        caller_record = _record(
            "src/user_page.py",
            [load_sym],
            source="from src.auth import login\ndef _load(): login()\n",
        )

        return RepoIndex(
            root=FIXTURE_ROOT,
            files=[src_record, caller_record],
        )

    def test_changed_symbol_found(self):
        index = self._make_index()
        hunks = {FIXTURE_ROOT / "src/auth.py": [(15, 20)]}
        report = analyze_blast_radius(index, hunks, base="main")
        changed_names = [a.symbol.name for a in report.affected_symbols]
        assert "login" in changed_names

    def test_no_changes_produces_empty_report(self):
        index = self._make_index()
        report = analyze_blast_radius(index, {}, base="main")
        assert report.affected_symbols == []
        assert report.total_callers == 0

    def test_report_base_is_set(self):
        index = self._make_index()
        report = analyze_blast_radius(index, {}, base="origin/dev")
        assert report.base == "origin/dev"

    def test_changed_files_recorded(self):
        index = self._make_index()
        path = FIXTURE_ROOT / "src/auth.py"
        report = analyze_blast_radius(index, {path: [(15, 20)]}, base="main")
        assert path in report.changed_files


# ── BlastRadiusReport properties ─────────────────────────────────────────────


class TestBlastRadiusReport:
    def _affected(self, uncovered_count: int, covered_count: int) -> AffectedSymbol:
        from reassure.analyzers.blast_radius import CallerRef

        sym = _sym("foo", "src/foo.py", 1, 10)
        callers = [
            CallerRef(
                symbol=_sym(f"caller_{i}", "src/bar.py", i, i + 5),
                file=FIXTURE_ROOT / "src/bar.py",
                is_covered=False,
            )
            for i in range(uncovered_count)
        ] + [
            CallerRef(
                symbol=_sym(f"covered_{i}", "src/baz.py", i, i + 5),
                file=FIXTURE_ROOT / "src/baz.py",
                is_covered=True,
            )
            for i in range(covered_count)
        ]
        return AffectedSymbol(symbol=sym, direct_callers=callers)

    def test_has_risk_when_uncovered_callers(self):
        report = BlastRadiusReport(
            base="main",
            changed_files=[],
            affected_symbols=[self._affected(uncovered_count=2, covered_count=1)],
        )
        assert report.has_risk

    def test_no_risk_when_all_covered(self):
        report = BlastRadiusReport(
            base="main",
            changed_files=[],
            affected_symbols=[self._affected(uncovered_count=0, covered_count=3)],
        )
        assert not report.has_risk

    def test_total_callers_count(self):
        report = BlastRadiusReport(
            base="main",
            changed_files=[],
            affected_symbols=[self._affected(uncovered_count=2, covered_count=1)],
        )
        assert report.total_callers == 3
        assert report.total_uncovered_callers == 2
