"""Unit tests for the test type classifier."""

from pathlib import Path

from reassure.classifiers.test_type import (
    TestType,
    classify_all,
    classify_test_file,
)


class TestPathSignals:
    def test_unit_path(self):
        result = classify_test_file(Path("tests/unit/test_auth.py"), [], [])
        assert result.primary == TestType.UNIT

    def test_integration_path(self):
        result = classify_test_file(Path("tests/integration/test_db.py"), [], [])
        assert result.primary == TestType.INTEGRATION

    def test_e2e_path(self):
        result = classify_test_file(Path("tests/e2e/test_login_flow.py"), [], [])
        assert result.primary == TestType.E2E

    def test_end_to_end_path(self):
        result = classify_test_file(Path("tests/end_to_end/test_checkout.py"), [], [])
        assert result.primary == TestType.E2E

    def test_smoke_path(self):
        result = classify_test_file(Path("tests/smoke/test_health.py"), [], [])
        assert result.primary == TestType.SMOKE

    def test_security_path(self):
        result = classify_test_file(Path("tests/security/test_injection.py"), [], [])
        assert result.primary == TestType.SECURITY


class TestMarkerSignals:
    def test_integration_marker_wins_over_unit_path(self):
        # marker should beat path fragment
        result = classify_test_file(
            Path("tests/unit/test_db.py"),
            [],
            ["pytest.mark.integration"],
        )
        assert result.primary == TestType.INTEGRATION

    def test_e2e_marker(self):
        result = classify_test_file(Path("tests/test_flow.py"), [], ["pytest.mark.e2e"])
        assert result.primary == TestType.E2E

    def test_smoke_marker(self):
        result = classify_test_file(Path("tests/test_health.py"), [], ["pytest.mark.smoke"])
        assert result.primary == TestType.SMOKE

    def test_slow_marker_implies_integration(self):
        result = classify_test_file(Path("tests/test_heavy.py"), [], ["pytest.mark.slow"])
        assert result.primary == TestType.INTEGRATION


class TestImportSignals:
    def test_playwright_implies_e2e(self):
        result = classify_test_file(Path("tests/test_ui.py"), ["playwright"], [])
        assert result.primary == TestType.E2E

    def test_sqlalchemy_implies_integration(self):
        result = classify_test_file(Path("tests/test_repo.py"), ["sqlalchemy"], [])
        assert result.primary == TestType.INTEGRATION

    def test_boto3_implies_integration(self):
        result = classify_test_file(Path("tests/test_s3.py"), ["boto3"], [])
        assert result.primary == TestType.INTEGRATION

    def test_selenium_implies_e2e(self):
        result = classify_test_file(Path("tests/test_browser.py"), ["selenium"], [])
        assert result.primary == TestType.E2E

    def test_dotted_import_root_matched(self):
        # "sqlalchemy.orm" → root "sqlalchemy" should still match
        result = classify_test_file(Path("tests/test_orm.py"), ["sqlalchemy.orm"], [])
        assert result.primary == TestType.INTEGRATION


class TestFallback:
    def test_no_signals_falls_back_to_unit(self):
        result = classify_test_file(Path("tests/test_utils.py"), [], [])
        assert result.primary == TestType.UNIT
        assert "fallback:unit" in result.signals

    def test_unknown_imports_fall_back_to_unit(self):
        result = classify_test_file(Path("tests/test_math.py"), ["numpy", "pandas"], [])
        assert result.primary == TestType.UNIT


class TestSignalRecording:
    def test_path_signal_recorded(self):
        result = classify_test_file(Path("tests/integration/test_db.py"), [], [])
        assert any("integration" in s for s in result.signals)

    def test_import_signal_recorded(self):
        result = classify_test_file(Path("tests/test_ui.py"), ["playwright"], [])
        assert any("playwright" in s for s in result.signals)

    def test_marker_signal_recorded(self):
        result = classify_test_file(Path("tests/test_x.py"), [], ["pytest.mark.e2e"])
        assert any("e2e" in s for s in result.signals)


class TestClassifyAll:
    def test_batch_classification(self):
        files = [
            (Path("tests/unit/test_a.py"), [], []),
            (Path("tests/integration/test_b.py"), [], []),
            (Path("tests/test_c.py"), ["playwright"], []),
        ]
        results = classify_all(files)
        assert results[Path("tests/unit/test_a.py")].primary == TestType.UNIT
        assert results[Path("tests/integration/test_b.py")].primary == TestType.INTEGRATION
        assert results[Path("tests/test_c.py")].primary == TestType.E2E
