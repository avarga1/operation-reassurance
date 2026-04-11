"""
Unit tests for the SOLID / SoC health analyzer.

Fixtures are intentionally bad files in tests/fixtures/dart/ and
tests/fixtures/python/ — annotated with REASSURE comments describing
exactly what each file should trigger.

Clean fixtures (clean_file.dart, clean_module.py) must NOT trigger anything —
they guard against false positives.
"""

from pathlib import Path

import pytest

from reassure.analyzers.solid import (
    SolidAnalyzer,
    detect_god_classes,
    detect_god_files,
    detect_soc_violations,
)
from reassure.core.repo_walker import walk_repo

DART_FIXTURES = Path(__file__).parent.parent / "fixtures" / "dart"
PYTHON_FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


# ── Fixtures walked into a RepoIndex ─────────────────────────────────────────


def _dart_available() -> bool:
    try:
        from reassure.core.parser import parse_file

        result = parse_file(DART_FIXTURES / "clean_file.dart")
        return result is not None and len(result[0].root_node.children) > 0
    except Exception:
        return False


_DART_SKIP = pytest.mark.skipif(
    not _dart_available(), reason="tree-sitter-dart grammar not available"
)


@pytest.fixture(scope="module")
def dart_index():
    if not _dart_available():
        pytest.skip("tree-sitter-dart grammar not available")
    return walk_repo(DART_FIXTURES)


@pytest.fixture(scope="module")
def python_index():
    return walk_repo(PYTHON_FIXTURES)


# ── God file detection ────────────────────────────────────────────────────────


class TestGodFileDetection:
    def test_god_file_dart_is_flagged(self, dart_index):
        god_files = detect_god_files(dart_index, god_file_loc=500, god_file_functions=20)
        flagged = [gf.file.path.name for gf in god_files]
        assert "god_file.dart" in flagged

    def test_clean_dart_file_not_flagged(self, dart_index):
        god_files = detect_god_files(dart_index, god_file_loc=500, god_file_functions=20)
        flagged = [gf.file.path.name for gf in god_files]
        assert "clean_file.dart" not in flagged

    def test_soc_violation_file_not_flagged_as_god_by_default(self, dart_index):
        # soc_violation.dart is small (< 500 LOC) — should not be a god file
        god_files = detect_god_files(dart_index, god_file_loc=500, god_file_functions=20)
        flagged = [gf.file.path.name for gf in god_files]
        assert "soc_violation.dart" not in flagged

    def test_god_file_python_is_flagged(self, python_index):
        god_files = detect_god_files(python_index, god_file_loc=100, god_file_functions=20)
        flagged = [gf.file.path.name for gf in god_files]
        assert "god_class.py" in flagged

    def test_clean_python_not_flagged(self, python_index):
        god_files = detect_god_files(python_index, god_file_loc=500, god_file_functions=20)
        flagged = [gf.file.path.name for gf in god_files]
        assert "clean_module.py" not in flagged

    def test_god_file_has_reasons(self, dart_index):
        god_files = detect_god_files(dart_index, god_file_loc=500, god_file_functions=20)
        gf = next(gf for gf in god_files if gf.file.path.name == "god_file.dart")
        assert len(gf.reasons) > 0


# ── God class detection ───────────────────────────────────────────────────────


class TestGodClassDetection:
    def test_user_manager_is_god_class(self, python_index):
        god_classes = detect_god_classes(python_index, god_class_methods=15)
        flagged = [gc.symbol.name for gc in god_classes]
        assert "UserManager" in flagged

    def test_dashboard_shell_state_is_god_class(self, dart_index):
        god_classes = detect_god_classes(dart_index, god_class_methods=15)
        flagged = [gc.symbol.name for gc in god_classes]
        # _DashboardShellState has 15+ methods
        assert any("DashboardShell" in name or "State" in name for name in flagged)

    def test_password_hasher_not_god_class(self, python_index):
        god_classes = detect_god_classes(python_index, god_class_methods=15)
        flagged = [gc.symbol.name for gc in god_classes]
        assert "PasswordHasher" not in flagged

    def test_user_avatar_not_god_class(self, dart_index):
        god_classes = detect_god_classes(dart_index, god_class_methods=15)
        flagged = [gc.symbol.name for gc in god_classes]
        assert "UserAvatar" not in flagged

    def test_god_class_has_method_count(self, python_index):
        god_classes = detect_god_classes(python_index, god_class_methods=15)
        um = next(gc for gc in god_classes if gc.symbol.name == "UserManager")
        assert um.method_count > 15


# ── SoC violation detection ───────────────────────────────────────────────────


class TestSoCViolations:
    def test_soc_violation_dart_flagged(self, dart_index):
        violations = detect_soc_violations(dart_index)
        flagged = [v["file"] for v in violations]
        assert any("soc_violation.dart" in str(f) for f in flagged)

    def test_god_file_dart_flagged_for_soc(self, dart_index):
        # god_file.dart mixes Widget + Repository + Service — should flag
        violations = detect_soc_violations(dart_index)
        flagged = [v["file"] for v in violations]
        assert any("god_file.dart" in str(f) for f in flagged)

    def test_clean_dart_not_flagged_for_soc(self, dart_index):
        violations = detect_soc_violations(dart_index)
        flagged = [v["file"] for v in violations]
        assert not any("clean_file.dart" in str(f) for f in flagged)

    def test_violation_has_reason(self, dart_index):
        violations = detect_soc_violations(dart_index)
        soc = next(v for v in violations if "soc_violation.dart" in str(v["file"]))
        assert "reason" in soc
        assert len(soc["reason"]) > 0


# ── Full analyzer (plugin protocol) ──────────────────────────────────────────


class TestSolidAnalyzer:
    def test_analyzer_name(self):
        assert SolidAnalyzer().name == "solid"

    def test_analyzer_returns_result(self, dart_index):
        result = SolidAnalyzer().analyze(dart_index)
        assert result.name == "solid"
        assert result.summary is not None

    def test_analyzer_finds_issues(self, dart_index):
        result = SolidAnalyzer().analyze(dart_index)
        assert len(result.issues) > 0

    def test_clean_only_index_has_no_issues(self):
        # Build an index from only the clean files
        from reassure.core.parser import detect_language, parse_file
        from reassure.core.repo_walker import FileRecord, RepoIndex
        from reassure.core.symbol_map import extract_symbols

        clean_dart = DART_FIXTURES / "clean_file.dart"
        lang = detect_language(clean_dart)
        result = parse_file(clean_dart)
        assert result is not None
        tree, source = result
        symbols = extract_symbols(tree, source, clean_dart, lang)
        record = FileRecord(path=clean_dart, lang=lang, symbols=symbols, loc=source.count("\n") + 1)
        index = RepoIndex(root=DART_FIXTURES, files=[record])

        analysis = SolidAnalyzer().analyze(index)
        assert len(analysis.issues) == 0
