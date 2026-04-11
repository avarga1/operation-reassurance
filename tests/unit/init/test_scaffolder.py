"""Tests for reassure.init.scaffolder."""

import pytest

from reassure.init.detector import StackProfile
from reassure.init.scaffolder import install_rules, list_templates, scaffold


class TestListTemplates:
    def test_flutter_riverpod_pg_present(self):
        templates = list_templates()
        assert "flutter-riverpod-pg" in templates

    def test_partials_not_listed(self):
        templates = list_templates()
        assert "_partials" not in templates


class TestScaffold:
    def test_creates_target_directory(self, tmp_path):
        target = tmp_path / "my_app"
        scaffold("flutter-riverpod-pg", target, project_name="my_app")
        assert target.is_dir()

    def test_renders_project_name_in_pubspec(self, tmp_path):
        target = tmp_path / "cool_app"
        scaffold("flutter-riverpod-pg", target, project_name="cool_app")
        pubspec = target / "pubspec.yaml"
        assert pubspec.exists()
        assert "cool_app" in pubspec.read_text()

    def test_renders_pascal_case_in_main(self, tmp_path):
        target = tmp_path / "my-cool-app"
        scaffold("flutter-riverpod-pg", target, project_name="my-cool-app")
        main_dart = target / "lib" / "main.dart"
        assert main_dart.exists()
        assert "MyCoolApp" in main_dart.read_text()

    def test_reassure_toml_written(self, tmp_path):
        target = tmp_path / "my_app"
        scaffold("flutter-riverpod-pg", target, project_name="my_app")
        toml_path = target / ".reassure.toml"
        assert toml_path.exists()
        content = toml_path.read_text()
        assert "flutter-riverpod-pg" in content
        assert "*_screen.dart" in content

    def test_mcp_json_written(self, tmp_path):
        target = tmp_path / "my_app"
        scaffold("flutter-riverpod-pg", target, project_name="my_app")
        assert (target / ".mcp.json").exists()

    def test_claude_md_written(self, tmp_path):
        target = tmp_path / "my_app"
        scaffold("flutter-riverpod-pg", target, project_name="my_app")
        claude_md = target / "CLAUDE.md"
        assert claude_md.exists()
        assert "my_app" in claude_md.read_text()

    def test_no_tmpl_extension_in_output(self, tmp_path):
        target = tmp_path / "my_app"
        created = scaffold("flutter-riverpod-pg", target, project_name="my_app")
        for path in created:
            assert not path.name.endswith(".tmpl"), f"Found .tmpl in output: {path}"

    def test_raises_on_existing_target_without_overwrite(self, tmp_path):
        target = tmp_path / "my_app"
        target.mkdir()
        with pytest.raises(FileExistsError):
            scaffold("flutter-riverpod-pg", target, project_name="my_app")

    def test_overwrite_flag_replaces_target(self, tmp_path):
        target = tmp_path / "my_app"
        scaffold("flutter-riverpod-pg", target, project_name="my_app")
        scaffold("flutter-riverpod-pg", target, project_name="my_app", overwrite=True)
        assert target.is_dir()

    def test_unknown_template_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No template found"):
            scaffold("nonexistent-stack", tmp_path / "x", project_name="x")


class TestInstallRules:
    def test_writes_reassure_toml_to_existing_project(self, tmp_path):
        profile = StackProfile(
            frontend="flutter",
            state_management="riverpod",
            database="postgres",
            template_key="flutter-riverpod-pg",
        )
        dest = install_rules(profile, tmp_path)
        assert dest == tmp_path / ".reassure.toml"
        assert dest.exists()
        assert "flutter-riverpod-pg" in dest.read_text()

    def test_unknown_profile_raises(self, tmp_path):
        profile = StackProfile(description="something weird")
        with pytest.raises(ValueError, match="unknown stack"):
            install_rules(profile, tmp_path)
