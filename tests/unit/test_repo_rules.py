"""Tests for reassure.analyzers.repo_rules."""

from pathlib import Path

import pytest

from reassure.analyzers.repo_rules import (
    PRESETS,
    RepoRule,
    RepoRulesAnalyzer,
    analyze_repo_rules,
    check_content,
    list_presets,
    _matches_glob,
)
from reassure.core.repo_walker import FileRecord, RepoIndex


# ── helpers ───────────────────────────────────────────────────────────────────


def _index(root: Path, files: list[tuple[str, str, bool]]) -> RepoIndex:
    """Build a RepoIndex from (rel_path, source, is_test) tuples."""
    records = []
    for rel, source, is_test in files:
        p = root / rel
        records.append(
            FileRecord(
                path=p,
                lang="dart" if rel.endswith(".dart") else "python",
                loc=source.count("\n") + 1,
                source=source,
                is_test=is_test,
            )
        )
    return RepoIndex(root=root, files=records)


# ── glob matching ─────────────────────────────────────────────────────────────


class TestGlobMatching:
    def test_exact(self):
        assert _matches_glob("lib/main.dart", "lib/main.dart")

    def test_wildcard_extension(self):
        assert _matches_glob("lib/main.dart", "**/*.dart")
        assert _matches_glob("lib/src/auth/login_screen.dart", "**/*.dart")

    def test_prefix_glob(self):
        assert _matches_glob("lib/src/auth.dart", "lib/**/*.dart")
        assert not _matches_glob("test/auth_test.dart", "lib/**/*.dart")

    def test_star_star_matches_deep(self):
        assert _matches_glob("lib/features/auth/data/repo.dart", "lib/**/*.dart")

    def test_no_match(self):
        assert not _matches_glob("test/auth_test.py", "lib/**/*.dart")


# ── check_content (PreToolUse path) ──────────────────────────────────────────


class TestCheckContent:
    def test_print_in_lib_flagged(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/auth.dart"),
            "void doThing() {\n  print('debug');\n}\n",
            rules,
            root=Path("/repo"),
        )
        assert any(v.rule.name == "no-print-in-prod" for v in violations)

    def test_print_in_test_not_flagged(self):
        """lib/**/*.dart pattern should not match test/ files."""
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("test/auth_test.dart"),
            "print('in test');\n",
            rules,
            root=Path("/repo"),
        )
        assert violations == []

    def test_mock_data_flagged(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/data/repo.dart"),
            "final user = MockData(id: '1');\n",
            rules,
            root=Path("/repo"),
        )
        assert any(v.rule.name == "no-inline-mock-data" for v in violations)

    def test_hardcoded_url_flagged(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/services/api.dart"),
            "final url = 'https://api.example.com/v1';\n",
            rules,
            root=Path("/repo"),
        )
        assert any(v.rule.name == "no-hardcoded-urls" for v in violations)

    def test_localhost_flagged(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/services/api.dart"),
            "final base = 'http://localhost:3000';\n",
            rules,
            root=Path("/repo"),
        )
        assert any(v.rule.name == "no-localhost" for v in violations)

    def test_todo_is_warning_not_error(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/auth.dart"),
            "// TODO: fix this later\n",
            rules,
            root=Path("/repo"),
        )
        todo = [v for v in violations if v.rule.name == "no-todo-in-prod"]
        assert len(todo) > 0
        assert all(v.rule.severity == "warning" for v in todo)

    def test_clean_content_no_violations(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("lib/auth.dart"),
            "class AuthService {\n  void login() {}\n}\n",
            rules,
            root=Path("/repo"),
        )
        assert violations == []

    def test_line_number_correct(self):
        rules = PRESETS["flutter"]
        content = "class A {}\n\nprint('oops');\n\nclass B {}\n"
        violations = check_content(Path("lib/a.dart"), content, rules, root=Path("/repo"))
        assert violations[0].line == 3

    def test_unmatched_file_never_flagged(self):
        rules = PRESETS["flutter"]
        violations = check_content(
            Path("pubspec.yaml"),
            "print('anything')\nMockData()\n",
            rules,
            root=Path("/repo"),
        )
        assert violations == []


# ── analyze_repo_rules (full index) ──────────────────────────────────────────


class TestAnalyzeRepoRules:
    def test_detects_print_in_lib(self, tmp_path):
        index = _index(
            tmp_path,
            [("lib/auth.dart", "void f() { print('x'); }\n", False)],
        )
        report = analyze_repo_rules(index, PRESETS["flutter"])
        assert report.has_errors
        assert any(m.rule.name == "no-print-in-prod" for m in report.matches)

    def test_test_files_skipped(self, tmp_path):
        index = _index(
            tmp_path,
            [("test/auth_test.dart", "print('in test');\n", True)],
        )
        report = analyze_repo_rules(index, PRESETS["flutter"])
        assert not report.has_issues

    def test_multiple_violations_different_rules(self, tmp_path):
        source = "print('x');\nfinal url = 'https://api.example.com';\n"
        index = _index(tmp_path, [("lib/api.dart", source, False)])
        report = analyze_repo_rules(index, PRESETS["flutter"])
        rule_names = {m.rule.name for m in report.matches}
        assert "no-print-in-prod" in rule_names
        assert "no-hardcoded-urls" in rule_names

    def test_files_checked_count(self, tmp_path):
        index = _index(
            tmp_path,
            [
                ("lib/a.dart", "void a() {}\n", False),
                ("lib/b.dart", "void b() {}\n", False),
                ("test/a_test.dart", "test stuff\n", True),
            ],
        )
        report = analyze_repo_rules(index, PRESETS["flutter"])
        assert report.files_checked == 2  # test file excluded

    def test_errors_vs_warnings_split(self, tmp_path):
        source = "print('x');\n// TODO: fix\n"
        index = _index(tmp_path, [("lib/a.dart", source, False)])
        report = analyze_repo_rules(index, PRESETS["flutter"])
        assert len(report.errors) >= 1
        assert len(report.warnings) >= 1

    def test_python_bare_except_flagged(self, tmp_path):
        index = _index(
            tmp_path,
            [("src/auth.py", "try:\n    pass\nexcept:\n    pass\n", False)],
        )
        report = analyze_repo_rules(index, PRESETS["python"])
        assert any(m.rule.name == "no-bare-except" for m in report.matches)

    def test_rust_unwrap_flagged(self, tmp_path):
        index = _index(
            tmp_path,
            [("src/main.rs", "let x = something().unwrap();\n", False)],
        )
        report = analyze_repo_rules(index, PRESETS["rust"])
        assert any(m.rule.name == "no-unwrap-in-prod" for m in report.matches)


# ── RepoRulesAnalyzer (plugin protocol) ──────────────────────────────────────


class TestRepoRulesAnalyzer:
    def test_result_name(self, tmp_path):
        analyzer = RepoRulesAnalyzer.__new__(RepoRulesAnalyzer)
        analyzer._load_rules = lambda root: PRESETS["flutter"]
        index = RepoIndex(root=tmp_path, files=[])
        result = analyzer.analyze(index)
        assert result.name == "repo_rules"

    def test_issues_format(self, tmp_path):
        source = "print('x');\n"
        index = _index(tmp_path, [("lib/a.dart", source, False)])
        analyzer = RepoRulesAnalyzer.__new__(RepoRulesAnalyzer)
        analyzer._load_rules = lambda root: PRESETS["flutter"]
        result = analyzer.analyze(index)
        assert len(result.issues) > 0
        issue = result.issues[0]
        assert "file" in issue
        assert "line" in issue
        assert "rule" in issue
        assert "severity" in issue
        assert "message" in issue

    def test_summary_clean(self, tmp_path):
        index = RepoIndex(root=tmp_path, files=[])
        analyzer = RepoRulesAnalyzer.__new__(RepoRulesAnalyzer)
        analyzer._load_rules = lambda root: PRESETS["flutter"]
        result = analyzer.analyze(index)
        assert "clean" in result.summary


# ── presets ───────────────────────────────────────────────────────────────────


class TestPresets:
    def test_all_presets_present(self):
        p = list_presets()
        assert "flutter" in p
        assert "python" in p
        assert "rust" in p
        assert "general" in p

    def test_each_preset_has_rules(self):
        for name, rules in PRESETS.items():
            assert len(rules) > 0, f"Preset '{name}' is empty"

    def test_all_rules_have_name_and_pattern(self):
        for preset_name, rules in PRESETS.items():
            for rule in rules:
                assert rule.name, f"Rule in {preset_name} has no name"
                assert rule.pattern, f"Rule '{rule.name}' has no pattern"
                assert rule.forbidden_content, f"Rule '{rule.name}' has no forbidden_content"
