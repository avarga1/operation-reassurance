"""
Test type classifier.

Given a test file's path and its parsed imports, classify it into one or more
test types: unit, integration, e2e, smoke, security.

Uses a multi-signal approach:
  1. Path fragments (tests/unit/, e2e/, etc.)
  2. Import analysis (imports playwright? → e2e. imports a real DB driver? → integration)
  3. Decorator/marker analysis (@pytest.mark.integration, #[ignore], etc.)
  4. Config overrides from .reassure.toml
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class TestType(StrEnum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    SMOKE = "smoke"
    SECURITY = "security"
    UNKNOWN = "unknown"


# Path fragment → test type
PATH_SIGNALS: dict[str, TestType] = {
    "unit": TestType.UNIT,
    "integration": TestType.INTEGRATION,
    "e2e": TestType.E2E,
    "end_to_end": TestType.E2E,
    "smoke": TestType.SMOKE,
    "security": TestType.SECURITY,
    "sec": TestType.SECURITY,
}

# Import → test type (presence of these imports strongly implies type)
IMPORT_SIGNALS: dict[str, TestType] = {
    # e2e
    "playwright": TestType.E2E,
    "selenium": TestType.E2E,
    "cypress": TestType.E2E,
    "puppeteer": TestType.E2E,
    # integration (real infrastructure)
    "psycopg2": TestType.INTEGRATION,
    "sqlalchemy": TestType.INTEGRATION,
    "pymongo": TestType.INTEGRATION,
    "redis": TestType.INTEGRATION,
    "boto3": TestType.INTEGRATION,
    "httpx": TestType.INTEGRATION,
    "requests": TestType.INTEGRATION,
    # security
    "bandit": TestType.SECURITY,
    "safety": TestType.SECURITY,
}

# Pytest markers that signal test type
MARKER_SIGNALS: dict[str, TestType] = {
    "pytest.mark.integration": TestType.INTEGRATION,
    "pytest.mark.e2e": TestType.E2E,
    "pytest.mark.smoke": TestType.SMOKE,
    "pytest.mark.security": TestType.SECURITY,
    "pytest.mark.slow": TestType.INTEGRATION,  # slow tests are usually integration
}


@dataclass
class TestClassification:
    primary: TestType
    signals: list[str]       # human-readable reasons for the classification


def classify_test_file(
    path: Path,
    imports: list[str],
    markers: list[str],
) -> TestClassification:
    """
    Classify a test file into a TestType using multi-signal heuristics.

    Priority: explicit marker > path fragment > import signal > UNKNOWN
    """
    # TODO: implement signal resolution with priority ordering
    # 1. Check markers (highest confidence)
    # 2. Check path fragments
    # 3. Check imports
    # 4. Fall back to UNIT if it's a test file with no other signals
    raise NotImplementedError


def classify_all(
    test_files: list[tuple[Path, list[str], list[str]]]
) -> dict[Path, TestClassification]:
    """Classify a batch of test files. Returns path → classification map."""
    return {
        path: classify_test_file(path, imports, markers)
        for path, imports, markers in test_files
    }
