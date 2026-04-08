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

import sys
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


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
    signals: list[str]  # human-readable reasons for the classification


def classify_test_file(
    path: Path,
    imports: list[str],
    markers: list[str],
) -> TestClassification:
    """
    Classify a test file into a TestType using multi-signal heuristics.

    Priority: explicit marker > path fragment > import signal > UNIT fallback
    Returns the highest-priority signal found, with all matching signals recorded.
    """
    signals: list[str] = []

    # 1. Markers — highest confidence, explicit developer intent
    for marker in markers:
        marker_clean = marker.strip()
        for pattern, test_type in MARKER_SIGNALS.items():
            if pattern in marker_clean:
                signals.append(f"marker:{marker_clean}")
                return TestClassification(primary=test_type, signals=signals)

    # 2. Path fragments — check every part of the path
    path_parts = [p.lower() for p in path.parts] + [path.stem.lower()]
    for part in path_parts:
        for fragment, test_type in PATH_SIGNALS.items():
            if fragment == part or fragment in part:
                signals.append(f"path:{part}")
                return TestClassification(primary=test_type, signals=signals)

    # 3. Import signals — infrastructure imports imply test type
    for imp in imports:
        imp_root = imp.split(".")[0].lower()
        if imp_root in IMPORT_SIGNALS:
            test_type = IMPORT_SIGNALS[imp_root]
            signals.append(f"import:{imp_root}")
            return TestClassification(primary=test_type, signals=signals)

    # 4. Fallback — it's a test file with no strong signals, assume unit
    signals.append("fallback:unit")
    return TestClassification(primary=TestType.UNIT, signals=signals)


def classify_all(
    test_files: list[tuple[Path, list[str], list[str]]],
) -> dict[Path, TestClassification]:
    """Classify a batch of test files. Returns path → classification map."""
    return {
        path: classify_test_file(path, imports, markers) for path, imports, markers in test_files
    }
