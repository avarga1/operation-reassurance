"""Tests for reassure.init.detector."""

from pathlib import Path

from reassure.init.detector import detect

FIXTURES = Path(__file__).parent / "fixtures"


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write a dict of {relative_path: content} into a temp directory."""
    for rel, content in files.items():
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    return tmp_path


# ── Flutter detection ─────────────────────────────────────────────────────────

class TestFlutterDetection:
    def test_riverpod_detected(self, tmp_path):
        _make_repo(tmp_path, {"pubspec.yaml": (FIXTURES / "pubspec_riverpod.yaml").read_text()})
        profile = detect(tmp_path)
        assert profile.frontend == "flutter"
        assert profile.state_management == "riverpod"

    def test_bloc_detected(self, tmp_path):
        _make_repo(tmp_path, {"pubspec.yaml": (FIXTURES / "pubspec_bloc.yaml").read_text()})
        profile = detect(tmp_path)
        assert profile.frontend == "flutter"
        assert profile.state_management == "bloc"

    def test_pubspec_in_subdirectory(self, tmp_path):
        """Monorepo layout: frontend/pubspec.yaml"""
        _make_repo(tmp_path, {
            "frontend/pubspec.yaml": (FIXTURES / "pubspec_riverpod.yaml").read_text()
        })
        profile = detect(tmp_path)
        assert profile.frontend == "flutter"
        assert profile.state_management == "riverpod"

    def test_no_pubspec_is_not_flutter(self, tmp_path):
        profile = detect(tmp_path)
        assert profile.frontend is None


# ── Backend detection ─────────────────────────────────────────────────────────

class TestBackendDetection:
    def test_axum_detected(self, tmp_path):
        _make_repo(tmp_path, {"Cargo.toml": (FIXTURES / "cargo_axum.toml").read_text()})
        profile = detect(tmp_path)
        assert profile.backend == "axum"

    def test_fastapi_detected(self, tmp_path):
        _make_repo(tmp_path, {"pyproject.toml": (FIXTURES / "pyproject_fastapi.toml").read_text()})
        profile = detect(tmp_path)
        assert profile.backend == "fastapi"


# ── Database detection ────────────────────────────────────────────────────────

class TestDatabaseDetection:
    def test_postgres_via_cargo(self, tmp_path):
        _make_repo(tmp_path, {"Cargo.toml": (FIXTURES / "cargo_axum.toml").read_text()})
        profile = detect(tmp_path)
        assert profile.database == "postgres"

    def test_postgres_via_pyproject(self, tmp_path):
        _make_repo(tmp_path, {"pyproject.toml": (FIXTURES / "pyproject_fastapi.toml").read_text()})
        profile = detect(tmp_path)
        assert profile.database == "postgres"

    def test_postgres_via_docker_compose(self, tmp_path):
        _make_repo(tmp_path, {
            "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n"
        })
        profile = detect(tmp_path)
        assert profile.database == "postgres"


# ── Template key resolution ───────────────────────────────────────────────────

class TestTemplateKeyResolution:
    def test_flutter_riverpod_pg(self, tmp_path):
        _make_repo(tmp_path, {
            "pubspec.yaml": (FIXTURES / "pubspec_riverpod.yaml").read_text(),
            "Cargo.toml": "# no axum here\n[package]\nname = 'x'\nversion='0.1.0'\nedition='2021'\n[dependencies]\n",
            "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n",
        })
        profile = detect(tmp_path)
        # Flutter + Riverpod + Postgres → known template
        assert profile.frontend == "flutter"
        assert profile.state_management == "riverpod"
        assert profile.database == "postgres"
        assert profile.template_key == "flutter-riverpod-pg"
        assert profile.is_known is True

    def test_unknown_stack_has_no_template_key(self, tmp_path):
        profile = detect(tmp_path)
        assert profile.template_key is None
        assert profile.is_known is False

    def test_description_set_for_known_stack(self, tmp_path):
        _make_repo(tmp_path, {
            "pubspec.yaml": (FIXTURES / "pubspec_riverpod.yaml").read_text(),
            "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n",
        })
        profile = detect(tmp_path)
        assert "Riverpod" in profile.description or "riverpod" in profile.description.lower()


# ── Warnings ──────────────────────────────────────────────────────────────────

class TestWarnings:
    def test_getx_generates_warning(self, tmp_path):
        _make_repo(tmp_path, {
            "pubspec.yaml": (
                "name: app\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"
                "dependencies:\n  flutter:\n    sdk: flutter\n  get: ^4.6.0\n"
            )
        })
        profile = detect(tmp_path)
        assert any("GetX" in w for w in profile.warnings)
