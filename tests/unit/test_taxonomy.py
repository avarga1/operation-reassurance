"""Tests for reassure.analyzers.taxonomy."""

from pathlib import Path

from reassure.analyzers.taxonomy import (
    _FLUTTER_BLOC_RULES,
    _FLUTTER_RIVERPOD_RULES,
    TaxonomyAnalyzer,
    TaxonomyRule,
    _extract_imports_from_source,
    _matching_rules,
    analyze_taxonomy,
    check_file,
)
from reassure.core.repo_walker import FileRecord, RepoIndex

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_index(files: list[FileRecord]) -> RepoIndex:
    return RepoIndex(root=Path("/repo"), files=files)


def _dart_file(name: str, loc: int, source: str = "", is_test: bool = False) -> FileRecord:
    return FileRecord(
        path=Path(f"/repo/lib/{name}"),
        lang="dart",
        loc=loc,
        source=source,
        is_test=is_test,
    )


def _py_file(name: str, loc: int, source: str = "") -> FileRecord:
    return FileRecord(
        path=Path(f"/repo/src/{name}"),
        lang="python",
        loc=loc,
        source=source,
    )


# ── import extraction ─────────────────────────────────────────────────────────


class TestExtractImports:
    def test_dart_package_import(self):
        src = "import 'package:sqflite/sqflite.dart';\nimport 'package:flutter/material.dart';"
        result = _extract_imports_from_source(src, ".dart")
        assert "package:sqflite/sqflite.dart" in result
        assert "package:flutter/material.dart" in result

    def test_dart_relative_import(self):
        src = "import '../data/auth_repository.dart';"
        result = _extract_imports_from_source(src, ".dart")
        assert "../data/auth_repository.dart" in result

    def test_python_import(self):
        src = "from fastapi import APIRouter\nimport sqlalchemy"
        result = _extract_imports_from_source(src, ".py")
        assert "fastapi" in result
        assert "sqlalchemy" in result

    def test_rust_use(self):
        src = "use axum::Router;\nuse sqlx::Pool;"
        result = _extract_imports_from_source(src, ".rs")
        assert any("axum" in i for i in result)
        assert any("sqlx" in i for i in result)

    def test_typescript_from(self):
        src = "import { useState } from 'react';\nimport Router from 'next/router';"
        result = _extract_imports_from_source(src, ".ts")
        assert "react" in result
        assert "next/router" in result


# ── pattern matching ──────────────────────────────────────────────────────────


class TestPatternMatching:
    def test_page_dart_matches(self):
        rules = [TaxonomyRule(pattern="*_page.dart", purpose="test")]
        matches = _matching_rules(Path("login_page.dart"), rules)
        assert len(matches) == 1

    def test_no_match_for_unrelated_file(self):
        rules = [TaxonomyRule(pattern="*_page.dart", purpose="test")]
        matches = _matching_rules(Path("auth_repository.dart"), rules)
        assert matches == []

    def test_multiple_matching_rules(self):
        rules = [
            TaxonomyRule(pattern="*_page.dart", purpose="page"),
            TaxonomyRule(pattern="*.dart", purpose="any dart"),
        ]
        matches = _matching_rules(Path("login_page.dart"), rules)
        assert len(matches) == 2


# ── check_file (PreToolUse path) ──────────────────────────────────────────────


class TestCheckFile:
    def test_clean_page_passes(self):
        content = "import 'package:flutter/material.dart';\n" * 5 + "class LoginPage {}\n" * 10
        violations = check_file(Path("login_page.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert violations == []

    def test_page_over_loc_flagged(self):
        content = "// line\n" * 200  # 200 LOC > 150 limit
        violations = check_file(Path("login_page.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert any("LOC" in r for v in violations for r in v.reasons)

    def test_page_with_sqflite_import_flagged(self):
        content = "import 'package:sqflite/sqflite.dart';\nclass P {}\n"
        violations = check_file(Path("login_page.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert any("sqflite" in r for v in violations for r in v.reasons)

    def test_page_with_http_flagged(self):
        content = "import 'package:dio/dio.dart';\nclass P {}\n"
        violations = check_file(Path("home_page.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert any("dio" in r for v in violations for r in v.reasons)

    def test_repository_with_ui_import_flagged(self):
        content = "import 'package:flutter/material.dart';\nclass Repo {}\n"
        violations = check_file(Path("auth_repository.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert any("flutter/material.dart" in r for v in violations for r in v.reasons)

    def test_repository_clean_passes(self):
        content = "import 'package:sqflite/sqflite.dart';\nclass Repo {}\n"
        violations = check_file(Path("auth_repository.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert violations == []

    def test_unmatched_file_never_flagged(self):
        content = "import 'package:sqflite/sqflite.dart';\n" * 500
        violations = check_file(Path("main.dart"), content, _FLUTTER_RIVERPOD_RULES)
        assert violations == []


# ── analyze_taxonomy (full index) ─────────────────────────────────────────────


class TestAnalyzeTaxonomy:
    def test_phi_page_pattern_violation(self):
        """Simulates phi_page.dart: 1664 LOC with sqflite imports."""
        source = "import 'package:sqflite/sqflite.dart';\nclass P {}\n"
        f = _dart_file("phi_page.dart", loc=1664, source=source)
        index = _make_index([f])
        report = analyze_taxonomy(index, _FLUTTER_RIVERPOD_RULES)

        assert report.has_issues
        v = report.violations[0]
        assert any("1664" in r for r in v.reasons)
        assert any("sqflite" in r for r in v.reasons)

    def test_clean_file_no_violations(self):
        source = "import 'package:flutter/material.dart';\nclass P {}\n"
        f = _dart_file("login_page.dart", loc=100, source=source)
        index = _make_index([f])
        report = analyze_taxonomy(index, _FLUTTER_RIVERPOD_RULES)
        assert not report.has_issues

    def test_test_files_not_checked(self):
        """Test files should never be checked against taxonomy rules."""
        source = "import 'package:sqflite/sqflite.dart';\n" * 200
        f = _dart_file("login_page_test.dart", loc=500, source=source, is_test=True)
        index = _make_index([f])
        report = analyze_taxonomy(index, _FLUTTER_RIVERPOD_RULES)
        assert not report.has_issues

    def test_files_checked_count(self):
        f1 = _dart_file("login_page.dart", loc=50)
        f2 = _dart_file("auth_repository.dart", loc=50)
        f3 = _dart_file("main.dart", loc=10)  # no matching rule
        index = _make_index([f1, f2, f3])
        report = analyze_taxonomy(index, _FLUTTER_RIVERPOD_RULES)
        assert report.files_checked == 2  # page + repository matched, main.dart didn't

    def test_multiple_violations_same_file(self):
        """A page that's too long AND has a forbidden import."""
        source = "import 'package:sqflite/sqflite.dart';\nclass P {}\n"
        f = _dart_file("home_page.dart", loc=500, source=source)
        index = _make_index([f])
        report = analyze_taxonomy(index, _FLUTTER_RIVERPOD_RULES)
        assert len(report.violations) == 1
        assert len(report.violations[0].reasons) == 2  # LOC + sqflite


# ── TaxonomyAnalyzer (plugin protocol) ───────────────────────────────────────


class TestTaxonomyAnalyzer:
    def test_result_has_correct_name(self):
        analyzer = TaxonomyAnalyzer()
        index = _make_index([])
        result = analyzer.analyze(index)
        assert result.name == "taxonomy"

    def test_summary_includes_violation_count(self):
        source = "import 'package:sqflite/sqflite.dart';\n"
        f = _dart_file("home_page.dart", loc=500, source=source)
        index = _make_index([f])
        # Pass rules directly by patching root detection
        analyzer = TaxonomyAnalyzer.__new__(TaxonomyAnalyzer)
        analyzer._config_path = None

        # Monkeypatch _load_rules to return riverpod rules
        analyzer._load_rules = lambda root: _FLUTTER_RIVERPOD_RULES

        result = analyzer.analyze(index)
        assert "violation" in result.summary

    def test_issues_format(self):
        source = "import 'package:sqflite/sqflite.dart';\n"
        f = _dart_file("home_page.dart", loc=500, source=source)
        index = _make_index([f])
        analyzer = TaxonomyAnalyzer.__new__(TaxonomyAnalyzer)
        analyzer._load_rules = lambda root: _FLUTTER_RIVERPOD_RULES
        result = analyzer.analyze(index)

        assert len(result.issues) > 0
        issue = result.issues[0]
        assert "file" in issue
        assert "rule_pattern" in issue
        assert "reasons" in issue
        assert "message" in issue


# ── BLoC rules ────────────────────────────────────────────────────────────────


class TestBlocRules:
    def test_bloc_with_ui_import_flagged(self):
        content = "import 'package:flutter/material.dart';\nclass AuthBloc {}\n"
        violations = check_file(Path("auth_bloc.dart"), content, _FLUTTER_BLOC_RULES)
        assert len(violations) > 0

    def test_page_with_sqflite_flagged(self):
        content = "import 'package:sqflite/sqflite.dart';\nclass P {}\n"
        violations = check_file(Path("login_page.dart"), content, _FLUTTER_BLOC_RULES)
        assert len(violations) > 0

    def test_page_over_loc_flagged(self):
        content = "// x\n" * 100  # 100 LOC > 80 BLoC page limit
        violations = check_file(Path("login_page.dart"), content, _FLUTTER_BLOC_RULES)
        assert any("LOC" in r for v in violations for r in v.reasons)
