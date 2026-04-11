"""Tests for reassure.analyzers.dead_code."""

from pathlib import Path

import pytest

from reassure.analyzers.dead_code import (
    DeadCodeAnalyzer,
    DeadCodeReport,
    _build_reference_set,
    _is_dunder,
    analyze_dead_code,
)
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol


# ── helpers ───────────────────────────────────────────────────────────────────


def _sym(
    name: str,
    kind: str = "function",
    line_start: int = 1,
    line_end: int = 5,
    is_public: bool = True,
    lang: str = "python",
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=Path(f"/repo/src/{name}.py"),
        line_start=line_start,
        line_end=line_end,
        lang=lang,
        is_public=is_public,
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


# ── _is_dunder ────────────────────────────────────────────────────────────────


class TestIsDunder:
    def test_dunder_detected(self):
        assert _is_dunder("__init__")
        assert _is_dunder("__str__")
        assert _is_dunder("__enter__")

    def test_public_not_dunder(self):
        assert not _is_dunder("my_function")
        assert not _is_dunder("MyClass")

    def test_single_underscore_not_dunder(self):
        assert not _is_dunder("_private")


# ── _build_reference_set ──────────────────────────────────────────────────────


class TestBuildReferenceSet:
    def test_names_from_source_collected(self):
        rec = _record("/repo/src/a.py", [], source="result = do_thing()\ndo_other()\n")
        refs_map = _build_reference_set(_index(rec))
        all_refs = set().union(*refs_map.values())
        assert "do_thing" in all_refs
        assert "do_other" in all_refs

    def test_test_file_refs_included(self):
        src = _record("/repo/src/auth.py", [], source="def login(): pass\n")
        test = _record(
            "/repo/tests/test_auth.py",
            [],
            source="from auth import login\nlogin()\n",
            is_test=True,
        )
        refs_map = _build_reference_set(_index(src, test))
        # login should appear in the test file's refs
        test_path = Path("/repo/tests/test_auth.py")
        assert "login" in refs_map[test_path]

    def test_empty_source_no_crash(self):
        rec = _record("/repo/src/empty.py", [], source="")
        refs_map = _build_reference_set(_index(rec))
        assert isinstance(refs_map, dict)


# ── analyze_dead_code ─────────────────────────────────────────────────────────


class TestAnalyzeDeadCode:
    def test_unreferenced_function_flagged(self):
        sym = _sym("orphan_fn")
        src = _record("/repo/src/util.py", [sym], source="def orphan_fn(): pass\n")
        # No other file references orphan_fn
        report = analyze_dead_code(_index(src))
        dead_names = [d.symbol.name for d in report.dead]
        assert "orphan_fn" in dead_names

    def test_referenced_function_not_flagged(self):
        sym = _sym("used_fn")
        src = _record("/repo/src/util.py", [sym], source="def used_fn(): pass\n")
        caller = _record("/repo/src/main.py", [], source="from util import used_fn\nused_fn()\n")
        report = analyze_dead_code(_index(src, caller))
        dead_names = [d.symbol.name for d in report.dead]
        assert "used_fn" not in dead_names

    def test_dunder_always_alive(self):
        sym = _sym("__init__", kind="method")
        src = _record("/repo/src/cls.py", [sym], source="def __init__(self): pass\n")
        report = analyze_dead_code(_index(src))
        dead_names = [d.symbol.name for d in report.dead]
        assert "__init__" not in dead_names

    def test_entry_points_always_alive(self):
        sym = _sym("main")
        src = _record("/repo/src/app.py", [sym], source="def main(): pass\n")
        report = analyze_dead_code(_index(src))
        dead_names = [d.symbol.name for d in report.dead]
        assert "main" not in dead_names

    def test_custom_entry_point_respected(self):
        sym = _sym("bootstrap")
        src = _record("/repo/src/app.py", [sym], source="def bootstrap(): pass\n")
        report = analyze_dead_code(_index(src), entry_points=["bootstrap"])
        dead_names = [d.symbol.name for d in report.dead]
        assert "bootstrap" not in dead_names

    def test_private_function_medium_confidence(self):
        sym = _sym("_internal", is_public=False)
        src = _record("/repo/src/util.py", [sym], source="def _internal(): pass\n")
        report = analyze_dead_code(_index(src), min_confidence="medium")
        dead = [d for d in report.dead if d.symbol.name == "_internal"]
        assert len(dead) == 1
        assert dead[0].confidence == "medium"

    def test_method_low_confidence(self):
        sym = _sym("orphan_method", kind="method")
        src = _record("/repo/src/cls.py", [sym], source="def orphan_method(self): pass\n")
        report = analyze_dead_code(_index(src), min_confidence="low")
        dead = [d for d in report.dead if d.symbol.name == "orphan_method"]
        assert len(dead) == 1
        assert dead[0].confidence == "low"

    def test_high_confidence_public_function(self):
        sym = _sym("truly_dead", is_public=True)
        src = _record("/repo/src/util.py", [sym], source="def truly_dead(): pass\n")
        report = analyze_dead_code(_index(src))
        dead = [d for d in report.dead if d.symbol.name == "truly_dead"]
        assert len(dead) == 1
        assert dead[0].confidence == "high"

    def test_total_symbols_count(self):
        syms = [_sym(f"fn_{i}") for i in range(5)]
        src = _record(
            "/repo/src/mod.py",
            syms,
            source="\n".join(f"def fn_{i}(): pass" for i in range(5)),
        )
        report = analyze_dead_code(_index(src))
        assert report.total_symbols == 5

    def test_empty_index_no_crash(self):
        report = analyze_dead_code(RepoIndex(root=Path("/repo"), files=[]))
        assert report.dead == []
        assert report.total_symbols == 0


# ── DeadCodeAnalyzer (plugin) ─────────────────────────────────────────────────


class TestDeadCodeAnalyzer:
    def test_analyzer_name(self):
        assert DeadCodeAnalyzer().name == "dead_code"

    def test_issues_format(self):
        sym = _sym("ghost_fn")
        src = _record("/repo/src/util.py", [sym], source="def ghost_fn(): pass\n")
        result = DeadCodeAnalyzer().analyze(_index(src))
        assert len(result.issues) > 0
        issue = result.issues[0]
        assert "symbol" in issue
        assert "kind" in issue
        assert "file" in issue
        assert "line" in issue
        assert "confidence" in issue

    def test_clean_summary(self):
        result = DeadCodeAnalyzer().analyze(RepoIndex(root=Path("/repo"), files=[]))
        assert "No dead code" in result.summary

    def test_dead_code_summary(self):
        sym = _sym("orphan")
        src = _record("/repo/src/util.py", [sym], source="def orphan(): pass\n")
        result = DeadCodeAnalyzer().analyze(_index(src))
        assert "dead" in result.summary.lower()
