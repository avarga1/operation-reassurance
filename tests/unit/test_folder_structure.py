"""Tests for reassure.analyzers.folder_structure."""

from pathlib import Path

import pytest

from reassure.analyzers.folder_structure import (
    FolderRule,
    FolderStructureAnalyzer,
    analyze_folder_structure,
    check_new_file,
    _matches_folder_pattern,
    _FLUTTER_RIVERPOD_FOLDER_RULES,
    _FLUTTER_BLOC_FOLDER_RULES,
)
from reassure.core.repo_walker import RepoIndex


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_tree(tmp_path: Path, structure: dict) -> Path:
    """
    Create a directory tree from a nested dict.
    Keys ending in '/' are directories; other values are file contents.
    Empty string value = empty file.
    """
    for name, content in structure.items():
        path = tmp_path / name
        if isinstance(content, dict):
            path.mkdir(parents=True, exist_ok=True)
            _make_tree(path, content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content or "")
    return tmp_path


def _index(root: Path) -> RepoIndex:
    return RepoIndex(root=root, files=[])


# ── pattern matching ──────────────────────────────────────────────────────────

class TestPatternMatching:
    def test_exact_match(self):
        assert _matches_folder_pattern("lib/pages", "lib/pages")

    def test_wildcard_segment(self):
        assert _matches_folder_pattern("lib/features/auth", "lib/features/*")
        assert _matches_folder_pattern("lib/features/dashboard", "lib/features/*")

    def test_wildcard_mid_path(self):
        assert _matches_folder_pattern("lib/features/auth/data", "lib/features/*/data")
        assert _matches_folder_pattern("lib/features/auth/presentation", "lib/features/*/presentation")

    def test_no_match_different_depth(self):
        assert not _matches_folder_pattern("lib/features/auth/data/extra", "lib/features/*/data")

    def test_no_match_wrong_prefix(self):
        assert not _matches_folder_pattern("src/pages", "lib/pages")

    def test_no_match_partial(self):
        assert not _matches_folder_pattern("lib/features", "lib/features/*")


# ── analyze_folder_structure ──────────────────────────────────────────────────

class TestAnalyzeFolderStructure:
    def test_flat_pages_dump_flagged(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/pages/login_page.dart": "",
            "lib/pages/home_page.dart": "",
            "lib/pages/profile_page.dart": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert report.has_issues
        folders = {str(v.folder) for v in report.violations}
        assert any("pages" in f for f in folders)

    def test_feature_missing_required_children(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/features/auth/presentation/login_screen.dart": "",
            # missing data/ and domain/
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert report.has_issues
        reasons = [r for v in report.violations for r in v.reasons]
        assert any("data" in r for r in reasons)
        assert any("domain" in r for r in reasons)

    def test_feature_with_all_children_passes(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/features/auth/data/auth_repository.dart": "",
            "lib/features/auth/domain/user_model.dart": "",
            "lib/features/auth/presentation/login_screen.dart": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        # auth/ folder itself should be clean (has all required children, no loose files)
        feature_violations = [
            v for v in report.violations
            if v.folder.name == "auth"
        ]
        assert feature_violations == []

    def test_feature_loose_files_flagged(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/features/auth/some_util.dart": "",  # loose file in feature root
            "lib/features/auth/data/auth_repository.dart": "",
            "lib/features/auth/domain/user_model.dart": "",
            "lib/features/auth/presentation/login_screen.dart": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        feature_violations = [v for v in report.violations if v.folder.name == "auth"]
        assert len(feature_violations) > 0
        assert any("loose" in r or "dump" in r for v in feature_violations for r in v.reasons)

    def test_presentation_over_limit_flagged(self, tmp_path):
        files = {f"lib/features/auth/presentation/screen_{i}.dart": "" for i in range(15)}
        files["lib/features/auth/data/repo.dart"] = ""
        files["lib/features/auth/domain/model.dart"] = ""
        _make_tree(tmp_path, files)
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        pres_violations = [v for v in report.violations if v.folder.name == "presentation"]
        assert len(pres_violations) > 0
        assert any("12" in r for v in pres_violations for r in v.reasons)

    def test_presentation_at_limit_passes(self, tmp_path):
        files = {f"lib/features/auth/presentation/screen_{i}.dart": "" for i in range(12)}
        files["lib/features/auth/data/repo.dart"] = ""
        files["lib/features/auth/domain/model.dart"] = ""
        _make_tree(tmp_path, files)
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        pres_violations = [v for v in report.violations if v.folder.name == "presentation"]
        assert pres_violations == []

    def test_core_over_limit_flagged(self, tmp_path):
        files = {f"lib/core/util_{i}.dart": "" for i in range(20)}
        _make_tree(tmp_path, files)
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        core_violations = [v for v in report.violations if v.folder.name == "core"]
        assert len(core_violations) > 0

    def test_unrelated_dirs_not_checked(self, tmp_path):
        _make_tree(tmp_path, {
            "backend/services/auth_service.py": "",
            "backend/services/user_service.py": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert not report.has_issues

    def test_empty_repo_no_violations(self, tmp_path):
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert not report.has_issues

    def test_folders_checked_count(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/pages/login_page.dart": "",
            "lib/core/constants.dart": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert report.folders_checked >= 2


# ── check_new_file (PreToolUse path) ─────────────────────────────────────────

class TestCheckNewFile:
    def test_writing_to_pages_blocked(self, tmp_path):
        pages = tmp_path / "lib" / "pages"
        pages.mkdir(parents=True)
        proposed = pages / "new_page.dart"
        violations = check_new_file(proposed, tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert len(violations) > 0
        assert any("dump" in r or "flat" in r for v in violations for r in v.reasons)

    def test_writing_to_feature_presentation_within_limit_passes(self, tmp_path):
        pres = tmp_path / "lib" / "features" / "auth" / "presentation"
        pres.mkdir(parents=True)
        # Only 3 existing files — well under the 12 limit
        for i in range(3):
            (pres / f"screen_{i}.dart").write_text("")
        proposed = pres / "new_screen.dart"
        violations = check_new_file(proposed, tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert violations == []

    def test_writing_to_feature_presentation_over_limit_blocked(self, tmp_path):
        pres = tmp_path / "lib" / "features" / "auth" / "presentation"
        pres.mkdir(parents=True)
        for i in range(12):
            (pres / f"screen_{i}.dart").write_text("")
        proposed = pres / "one_more_screen.dart"
        violations = check_new_file(proposed, tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert len(violations) > 0

    def test_unmatched_path_never_blocked(self, tmp_path):
        target = tmp_path / "lib" / "main.dart"
        violations = check_new_file(target, tmp_path, _FLUTTER_RIVERPOD_FOLDER_RULES)
        assert violations == []


# ── FolderStructureAnalyzer (plugin protocol) ─────────────────────────────────

class TestFolderStructureAnalyzer:
    def test_result_name(self, tmp_path):
        analyzer = FolderStructureAnalyzer.__new__(FolderStructureAnalyzer)
        analyzer._load_rules = lambda root: _FLUTTER_RIVERPOD_FOLDER_RULES
        index = _index(tmp_path)
        result = analyzer.analyze(index)
        assert result.name == "folder_structure"

    def test_issues_format(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/pages/login_page.dart": "",
            "lib/pages/home_page.dart": "",
        })
        analyzer = FolderStructureAnalyzer.__new__(FolderStructureAnalyzer)
        analyzer._load_rules = lambda root: _FLUTTER_RIVERPOD_FOLDER_RULES
        index = _index(tmp_path)
        result = analyzer.analyze(index)
        assert len(result.issues) > 0
        issue = result.issues[0]
        assert "folder" in issue
        assert "rule_pattern" in issue
        assert "reasons" in issue
        assert "message" in issue

    def test_summary_includes_violation_count(self, tmp_path):
        _make_tree(tmp_path, {"lib/pages/p.dart": ""})
        analyzer = FolderStructureAnalyzer.__new__(FolderStructureAnalyzer)
        analyzer._load_rules = lambda root: _FLUTTER_RIVERPOD_FOLDER_RULES
        result = analyzer.analyze(_index(tmp_path))
        assert "violation" in result.summary


# ── BLoC rules ────────────────────────────────────────────────────────────────

class TestBlocFolderRules:
    def test_bloc_feature_missing_required_children(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/features/auth/view/login_page.dart": "",
            # missing bloc/ and data/
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_BLOC_FOLDER_RULES)
        assert report.has_issues
        reasons = [r for v in report.violations for r in v.reasons]
        assert any("bloc" in r for r in reasons)
        assert any("data" in r for r in reasons)

    def test_bloc_feature_complete_passes(self, tmp_path):
        _make_tree(tmp_path, {
            "lib/features/auth/bloc/auth_bloc.dart": "",
            "lib/features/auth/data/auth_repository.dart": "",
            "lib/features/auth/view/login_page.dart": "",
        })
        report = analyze_folder_structure(tmp_path, _FLUTTER_BLOC_FOLDER_RULES)
        feature_violations = [v for v in report.violations if v.folder.name == "auth"]
        assert feature_violations == []
