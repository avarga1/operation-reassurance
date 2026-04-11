"""
Unit tests for reassure.analyzers.duplication.

Uses synthetic RepoIndex / FileRecord / Symbol objects — no real file I/O
needed for the core logic tests.  The subtree-detection tests do require a
real CST (via parse_file), so they parse tiny in-memory-written temp files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from reassure.analyzers.duplication import (
    DuplicationAnalyzer,
    _find_clone_groups,
    _find_duplicate_subtrees,
    _fingerprint,
    _normalize_body,
)
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sym(
    name: str,
    file: str,
    kind: str = "function",
    line_start: int = 1,
    line_end: int = 5,
    lang: str = "python",
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=Path(file),
        line_start=line_start,
        line_end=line_end,
        lang=lang,
        is_public=not name.startswith("_"),
    )


def _record(
    path: str,
    symbols: list[Symbol],
    source: str = "",
    is_test: bool = False,
    lang: str = "python",
) -> FileRecord:
    return FileRecord(
        path=Path(path),
        lang=lang,
        symbols=symbols,
        loc=source.count("\n") + 1,
        is_test=is_test,
        source=source,
    )


def _index(*records: FileRecord, root: Path = Path("/repo")) -> RepoIndex:
    return RepoIndex(root=root, files=list(records))


# ── TestNormalization ─────────────────────────────────────────────────────────


class TestNormalization:
    def test_identifiers_replaced(self):
        result = _normalize_body("def foo(x):\n    return x + 1\n")
        assert "__ID__" in result
        assert "foo" not in result
        assert "x" not in result

    def test_comments_stripped(self):
        result = _normalize_body("# this is a comment\npass\n")
        assert "comment" not in result

    def test_whitespace_collapsed(self):
        result = _normalize_body("a   =   b\n\n\nc = d")
        assert "  " not in result  # no double spaces

    def test_same_structure_different_names_equal_fingerprint(self):
        body_a = "def compute_total(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n"
        body_b = "def sum_values(vals):\n    acc = 0\n    for val in vals:\n        acc += val\n    return acc\n"
        assert _fingerprint(_normalize_body(body_a)) == _fingerprint(_normalize_body(body_b))

    def test_different_structure_different_fingerprint(self):
        body_a = "def a(x):\n    return x * 2\n"
        body_b = "def b(x):\n    return x + x + x\n"
        assert _fingerprint(_normalize_body(body_a)) != _fingerprint(_normalize_body(body_b))


# ── TestCloneDetection ────────────────────────────────────────────────────────


class TestCloneDetection:
    # Shared body shape: a loop accumulator
    _BODY_A = (
        "def compute_total(items):\n"
        "    result = 0\n"
        "    for item in items:\n"
        "        result += item\n"
        "    return result\n"
    )
    _BODY_B = (
        "def sum_values(vals):\n"
        "    acc = 0\n"
        "    for val in vals:\n"
        "        acc += val\n"
        "    return acc\n"
    )

    def test_identical_body_in_two_files_detected(self):
        sym_a = _sym("compute_total", "/repo/src/a.py", line_start=1, line_end=5)
        sym_b = _sym("sum_values", "/repo/src/b.py", line_start=1, line_end=5)
        rec_a = _record("/repo/src/a.py", [sym_a], source=self._BODY_A)
        rec_b = _record("/repo/src/b.py", [sym_b], source=self._BODY_B)
        groups, _ = _find_clone_groups(_index(rec_a, rec_b))
        assert len(groups) == 1
        clone_names = {sym.name for sym in groups[0].symbols}
        assert "compute_total" in clone_names
        assert "sum_values" in clone_names

    def test_different_body_functions_not_clones(self):
        body_a = "def foo(x):\n    return x * 2\n"
        body_b = "def bar(x, y):\n    return x + y + 100\n"
        sym_a = _sym("foo", "/repo/src/a.py", line_start=1, line_end=2)
        sym_b = _sym("bar", "/repo/src/b.py", line_start=1, line_end=2)
        rec_a = _record("/repo/src/a.py", [sym_a], source=body_a)
        rec_b = _record("/repo/src/b.py", [sym_b], source=body_b)
        groups, _ = _find_clone_groups(_index(rec_a, rec_b))
        assert len(groups) == 0

    def test_same_file_clones_not_reported(self):
        """Two identical-body functions in the SAME file don't count — need 2+ files."""
        body = (
            "def first(items):\n"
            "    result = 0\n"
            "    for item in items:\n"
            "        result += item\n"
            "    return result\n"
            "\n"
            "def second(vals):\n"
            "    acc = 0\n"
            "    for val in vals:\n"
            "        acc += val\n"
            "    return acc\n"
        )
        sym_a = _sym("first", "/repo/src/a.py", line_start=1, line_end=5)
        sym_b = _sym("second", "/repo/src/a.py", line_start=7, line_end=11)
        rec = _record("/repo/src/a.py", [sym_a, sym_b], source=body)
        groups, _ = _find_clone_groups(_index(rec))
        assert len(groups) == 0

    def test_private_symbol_skipped(self):
        body_a = "def _compute(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n"
        body_b = "def _sum(vals):\n    acc = 0\n    for val in vals:\n        acc += val\n    return acc\n"
        sym_a = _sym("_compute", "/repo/src/a.py", line_start=1, line_end=5)
        sym_b = _sym("_sum", "/repo/src/b.py", line_start=1, line_end=5)
        rec_a = _record("/repo/src/a.py", [sym_a], source=body_a)
        rec_b = _record("/repo/src/b.py", [sym_b], source=body_b)
        groups, _ = _find_clone_groups(_index(rec_a, rec_b))
        assert len(groups) == 0

    def test_normalization_same_structure_different_names(self):
        """Core invariant: structural equality despite name differences."""
        norm_a = _normalize_body(self._BODY_A)
        norm_b = _normalize_body(self._BODY_B)
        assert norm_a == norm_b

    def test_total_symbols_counted(self):
        sym_a = _sym("foo", "/repo/src/a.py", line_start=1, line_end=3)
        sym_b = _sym("bar", "/repo/src/b.py", line_start=1, line_end=3)
        rec_a = _record("/repo/src/a.py", [sym_a], source="def foo(x):\n    pass\n")
        rec_b = _record("/repo/src/b.py", [sym_b], source="def bar(x):\n    pass\n")
        _, total = _find_clone_groups(_index(rec_a, rec_b))
        assert total == 2


# ── TestSubtreeDetection ──────────────────────────────────────────────────────


class TestSubtreeDetection:
    """
    These tests write tiny Python files to a temp dir so that parse_file can
    build a real CST.  We use a repeated 5-line block that should be flagged.
    """

    _REPEATED_BLOCK = """\
x = (
    alpha
    + beta
    + gamma
    + delta
)
"""

    def _make_source(self, prefix: str = "") -> str:
        return f"{prefix}\n{self._REPEATED_BLOCK}"

    def test_five_line_block_in_three_files_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths: list[Path] = []
            for i in range(3):
                p = root / f"mod_{i}.py"
                p.write_text(self._make_source(f"# file {i}"))
                paths.append(p)

            records = [
                FileRecord(
                    path=p,
                    lang="python",
                    symbols=[],
                    loc=10,
                    is_test=False,
                    source=p.read_text(),
                )
                for p in paths
            ]
            index = RepoIndex(root=root, files=records)
            subtrees = _find_duplicate_subtrees(index, min_lines=4, min_occurrences=3)
            # At least one duplicate should span all three files
            assert len(subtrees) > 0
            all_files = {path for ds in subtrees for path, _, _ in ds.occurrences}
            assert len(all_files) >= 2

    def test_two_line_block_not_detected(self):
        """Blocks shorter than min_lines should never be reported."""
        two_liner = "x = 1\ny = 2\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths: list[Path] = []
            for i in range(3):
                p = root / f"mod_{i}.py"
                p.write_text(two_liner)
                paths.append(p)

            records = [
                FileRecord(
                    path=p,
                    lang="python",
                    symbols=[],
                    loc=2,
                    is_test=False,
                    source=p.read_text(),
                )
                for p in paths
            ]
            index = RepoIndex(root=root, files=records)
            # min_lines=4 means 2-line nodes are ignored
            subtrees = _find_duplicate_subtrees(index, min_lines=4, min_occurrences=3)
            # The 2-line block itself must NOT appear (may have larger nodes detected)
            two_liner_fp = _fingerprint(two_liner.strip())
            flagged_fps = {ds.fingerprint for ds in subtrees}
            # We only care that the tiny block is not the culprit
            # (larger wrappers like the module node will be identical — that's ok)
            assert two_liner_fp not in flagged_fps

    def test_test_files_excluded_from_subtree_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths: list[Path] = []
            for i in range(3):
                p = root / f"test_mod_{i}.py"
                p.write_text(self._make_source(f"# test {i}"))
                paths.append(p)

            # Mark all as test files
            records = [
                FileRecord(
                    path=p,
                    lang="python",
                    symbols=[],
                    loc=10,
                    is_test=True,  # <-- test file
                    source=p.read_text(),
                )
                for p in paths
            ]
            index = RepoIndex(root=root, files=records)
            subtrees = _find_duplicate_subtrees(index, min_lines=4, min_occurrences=3)
            assert len(subtrees) == 0

    def test_missing_source_handled_gracefully(self):
        """Records with no source and non-existent path don't crash."""
        rec = FileRecord(
            path=Path("/nonexistent/mod.py"),
            lang="python",
            symbols=[],
            loc=0,
            is_test=False,
            source=None,
        )
        index = RepoIndex(root=Path("/nonexistent"), files=[rec])
        # Should not raise
        subtrees = _find_duplicate_subtrees(index, min_lines=4, min_occurrences=3)
        assert isinstance(subtrees, list)


# ── TestDuplicationAnalyzer ───────────────────────────────────────────────────


class TestDuplicationAnalyzer:
    def test_analyzer_name(self):
        assert DuplicationAnalyzer().name == "duplication"

    def test_analyzer_description_not_empty(self):
        assert len(DuplicationAnalyzer().description) > 0

    def test_clean_index_has_no_issues(self):
        """Empty index → no issues, clean summary."""
        index = RepoIndex(root=Path("/repo"), files=[])
        result = DuplicationAnalyzer().analyze(index)
        assert result.name == "duplication"
        assert len(result.issues) == 0
        assert "No duplication" in result.summary

    def test_clone_issues_format(self):
        body_a = "def compute_total(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n"
        body_b = "def sum_values(vals):\n    acc = 0\n    for val in vals:\n        acc += val\n    return acc\n"
        sym_a = _sym("compute_total", "/repo/src/a.py", line_start=1, line_end=5)
        sym_b = _sym("sum_values", "/repo/src/b.py", line_start=1, line_end=5)
        rec_a = _record("/repo/src/a.py", [sym_a], source=body_a)
        rec_b = _record("/repo/src/b.py", [sym_b], source=body_b)
        result = DuplicationAnalyzer().analyze(_index(rec_a, rec_b))
        clone_issues = [i for i in result.issues if i["type"] == "clone"]
        assert len(clone_issues) == 1
        issue = clone_issues[0]
        assert "fingerprint" in issue
        assert "count" in issue
        assert "files" in issue
        assert "symbols" in issue
        assert "snippet" in issue
        assert issue["count"] == 2

    def test_summary_contains_clone_info(self):
        body_a = "def compute_total(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n"
        body_b = "def sum_values(vals):\n    acc = 0\n    for val in vals:\n        acc += val\n    return acc\n"
        sym_a = _sym("compute_total", "/repo/src/a.py", line_start=1, line_end=5)
        sym_b = _sym("sum_values", "/repo/src/b.py", line_start=1, line_end=5)
        rec_a = _record("/repo/src/a.py", [sym_a], source=body_a)
        rec_b = _record("/repo/src/b.py", [sym_b], source=body_b)
        result = DuplicationAnalyzer().analyze(_index(rec_a, rec_b))
        assert "clone" in result.summary.lower()

    def test_result_data_is_duplication_report(self):
        from reassure.analyzers.duplication import DuplicationReport

        result = DuplicationAnalyzer().analyze(RepoIndex(root=Path("/repo"), files=[]))
        assert isinstance(result.data, DuplicationReport)

    def test_clone_pct_zero_on_clean(self):
        from reassure.analyzers.duplication import DuplicationReport

        result = DuplicationAnalyzer().analyze(RepoIndex(root=Path("/repo"), files=[]))
        report: DuplicationReport = result.data
        assert report.clone_pct == 0.0
