"""Tests for reassure.analyzers.solid."""

from pathlib import Path

import pytest

from reassure.analyzers.solid import (
    GodFile,
    GodFunction,
    SolidAnalyzer,
    compute_cyclomatic_complexity,
    detect_god_classes,
    detect_god_files,
    detect_god_functions,
    detect_soc_violations,
)
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol


# ── helpers ───────────────────────────────────────────────────────────────────


def _sym(
    name: str,
    kind: str = "function",
    line_start: int = 1,
    line_end: int = 10,
    parent_class: str | None = None,
    lang: str = "python",
    is_public: bool = True,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=Path(f"/repo/src/{name}.py"),
        line_start=line_start,
        line_end=line_end,
        lang=lang,
        parent_class=parent_class,
        is_public=is_public,
    )


def _record(
    path: str,
    symbols: list[Symbol],
    loc: int = 10,
    lang: str = "python",
    source: str | None = None,
) -> FileRecord:
    return FileRecord(
        path=Path(path),
        lang=lang,
        symbols=symbols,
        loc=loc,
        is_test=False,
        source=source,
    )


def _index(*records: FileRecord, root: Path = Path("/repo")) -> RepoIndex:
    return RepoIndex(root=root, files=list(records))


# ── god file detection ────────────────────────────────────────────────────────


class TestGodFileDetection:
    def test_high_loc_flagged(self):
        rec = _record("/repo/src/big.py", [], loc=600)
        report = detect_god_files(_index(rec), god_file_loc=500)
        assert any(gf.file.path.name == "big.py" for gf in report)

    def test_clean_file_not_flagged(self):
        rec = _record("/repo/src/small.py", [], loc=50)
        report = detect_god_files(_index(rec), god_file_loc=500)
        assert report == []

    def test_many_functions_flagged(self):
        syms = [_sym(f"fn_{i}", kind="function") for i in range(25)]
        rec = _record("/repo/src/bloat.py", syms, loc=100)
        report = detect_god_files(_index(rec), god_file_loc=500, god_file_functions=20)
        assert any(gf.file.path.name == "bloat.py" for gf in report)

    def test_reasons_populated(self):
        rec = _record("/repo/src/big.py", [], loc=600)
        report = detect_god_files(_index(rec), god_file_loc=500)
        gf = next(g for g in report if g.file.path.name == "big.py")
        assert len(gf.reasons) > 0
        assert "LOC" in gf.reasons[0]

    def test_threshold_boundary_at_limit_not_flagged(self):
        # exactly at threshold — not flagged (threshold is exclusive upper bound)
        rec = _record("/repo/src/exact.py", [], loc=500)
        report = detect_god_files(_index(rec), god_file_loc=500)
        assert report == []

    def test_threshold_boundary_over_limit_flagged(self):
        # one over threshold — flagged
        rec = _record("/repo/src/over.py", [], loc=501)
        report = detect_god_files(_index(rec), god_file_loc=500)
        assert any(gf.file.path.name == "over.py" for gf in report)


# ── god class detection ───────────────────────────────────────────────────────


class TestGodClassDetection:
    def test_many_methods_flagged(self):
        methods = [_sym(f"method_{i}", kind="method", parent_class="BigClass") for i in range(20)]
        cls = _sym("BigClass", kind="class")
        rec = _record("/repo/src/big_class.py", [cls] + methods)
        report = detect_god_classes(_index(rec), god_class_methods=15)
        assert any(gc.symbol.name == "BigClass" for gc in report)

    def test_small_class_not_flagged(self):
        methods = [_sym(f"m_{i}", kind="method", parent_class="SmallClass") for i in range(5)]
        cls = _sym("SmallClass", kind="class")
        rec = _record("/repo/src/small_class.py", [cls] + methods)
        report = detect_god_classes(_index(rec), god_class_methods=15)
        assert report == []

    def test_method_count_in_reasons(self):
        methods = [_sym(f"m_{i}", kind="method", parent_class="Fat") for i in range(20)]
        cls = _sym("Fat", kind="class")
        rec = _record("/repo/src/fat.py", [cls] + methods)
        report = detect_god_classes(_index(rec), god_class_methods=15)
        gc = next(g for g in report if g.symbol.name == "Fat")
        assert gc.method_count == 20
        assert "20 methods" in gc.reasons[0]


# ── cyclomatic complexity ─────────────────────────────────────────────────────


class TestCyclomaticComplexity:
    def test_simple_function_is_1(self):
        sym = _sym("simple", line_start=1, line_end=3)
        source = "def simple():\n    return 42\n"
        assert compute_cyclomatic_complexity(sym, source) == 1

    def test_if_adds_1(self):
        sym = _sym("check", line_start=1, line_end=4)
        source = "def check(x):\n    if x > 0:\n        return True\n    return False\n"
        cc = compute_cyclomatic_complexity(sym, source)
        assert cc >= 2  # 1 base + 1 if

    def test_multiple_branches(self):
        sym = _sym("complex_fn", line_start=1, line_end=10)
        source = (
            "def complex_fn(x, y):\n"
            "    if x > 0:\n"
            "        for i in range(x):\n"
            "            if y:\n"
            "                pass\n"
            "    while x > 0:\n"
            "        x -= 1\n"
            "    return x\n"
        )
        cc = compute_cyclomatic_complexity(sym, source)
        assert cc >= 5

    def test_dart_branches(self):
        sym = Symbol(
            name="build",
            kind="method",
            file=Path("/repo/lib/widget.dart"),
            line_start=1,
            line_end=8,
            lang="dart",
        )
        source = (
            "Widget build(BuildContext context) {\n"
            "  if (isLoading) {\n"
            "    return CircularProgressIndicator();\n"
            "  } else if (hasError) {\n"
            "    return ErrorWidget();\n"
            "  }\n"
            "  return child;\n"
            "}\n"
        )
        cc = compute_cyclomatic_complexity(sym, source)
        assert cc >= 3


# ── god function detection ────────────────────────────────────────────────────


class TestGodFunctionDetection:
    def test_high_complexity_flagged(self):
        source = "\n".join(
            ["def complex():"]
            + [f"    if x_{i}: pass" for i in range(15)]
            + ["    return True"]
        )
        sym = _sym("complex", line_start=1, line_end=len(source.splitlines()))
        rec = _record("/repo/src/complex.py", [sym], source=source)
        report = detect_god_functions(_index(rec), max_complexity=10)
        assert any(gf.symbol.name == "complex" for gf in report)

    def test_simple_function_not_flagged(self):
        source = "def simple():\n    return 42\n"
        sym = _sym("simple", line_start=1, line_end=2)
        rec = _record("/repo/src/simple.py", [sym], source=source)
        report = detect_god_functions(_index(rec), max_complexity=10)
        assert report == []

    def test_complexity_reported(self):
        source = "\n".join(
            ["def fn():"] + [f"    if x_{i}: pass" for i in range(15)] + ["    return True"]
        )
        sym = _sym("fn", line_start=1, line_end=len(source.splitlines()))
        rec = _record("/repo/src/fn.py", [sym], source=source)
        report = detect_god_functions(_index(rec), max_complexity=10)
        gf = next(g for g in report if g.symbol.name == "fn")
        assert gf.complexity > 10


# ── SoC violations ────────────────────────────────────────────────────────────


class TestSoCViolations:
    def test_mixed_archetypes_flagged(self):
        syms = [
            _sym("HomeScreen", kind="class", lang="dart"),
            _sym("UserRepository", kind="class", lang="dart"),
        ]
        rec = _record("/repo/lib/home.dart", syms, lang="dart")
        violations = detect_soc_violations(_index(rec))
        assert len(violations) > 0
        assert any("archetype_co_residence" == v["type"] for v in violations)

    def test_single_archetype_not_flagged(self):
        syms = [_sym("HomeScreen", kind="class", lang="dart")]
        rec = _record("/repo/lib/home.dart", syms, lang="dart")
        violations = detect_soc_violations(_index(rec))
        assert violations == []

    def test_python_skipped(self):
        syms = [_sym("HomeWidget", kind="class", lang="python")]
        rec = _record("/repo/src/home.py", syms, lang="python")
        violations = detect_soc_violations(_index(rec))
        assert violations == []


# ── SolidAnalyzer (plugin) ────────────────────────────────────────────────────


class TestSolidAnalyzer:
    def test_analyzer_name(self):
        assert SolidAnalyzer().name == "solid"

    def test_clean_index_no_issues(self):
        rec = _record("/repo/src/clean.py", [_sym("do_thing")], loc=50)
        result = SolidAnalyzer().analyze(_index(rec))
        assert "0 issues" in result.summary

    def test_god_file_appears_in_issues(self):
        rec = _record("/repo/src/bloat.py", [], loc=600)
        result = SolidAnalyzer(god_file_loc=500).analyze(_index(rec))
        assert any(i["type"] == "god_file" for i in result.issues)

    def test_god_function_appears_in_issues(self):
        source = "\n".join(
            ["def fn():"] + [f"    if x_{i}: pass" for i in range(15)] + ["    return True"]
        )
        sym = _sym("fn", line_start=1, line_end=len(source.splitlines()))
        rec = _record("/repo/src/fn.py", [sym], source=source)
        result = SolidAnalyzer(max_complexity=5).analyze(_index(rec))
        assert any(i["type"] == "god_function" for i in result.issues)

    def test_summary_format(self):
        result = SolidAnalyzer().analyze(RepoIndex(root=Path("/repo"), files=[]))
        assert "god files" in result.summary
        assert "god classes" in result.summary
