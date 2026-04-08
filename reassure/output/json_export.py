"""
JSON export for CI integration.

Serializes all analyzer reports to a structured JSON format suitable
for CI artifact storage, dashboards, or downstream tooling.
"""

import json
from pathlib import Path
from typing import Any

from reassure.analyzers.test_coverage import CoverageReport
from reassure.analyzers.observability import ObservabilityReport
from reassure.analyzers.dead_code import DeadCodeReport
from reassure.analyzers.solid import SolidReport
from reassure.analyzers.metrics import RepoMetrics


def export_all(
    coverage: CoverageReport,
    observability: ObservabilityReport,
    dead_code: DeadCodeReport,
    solid: SolidReport,
    metrics: RepoMetrics,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    Serialize all reports to a single JSON structure.
    Writes to output_path if provided, always returns the dict.
    """
    # TODO: implement
    raise NotImplementedError
