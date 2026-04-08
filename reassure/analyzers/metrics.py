"""
Structural metrics analyzer.

Computes repo-wide and per-file health metrics:
  - Lines of code (total, per file, per function)
  - Function/class counts
  - Test-to-source ratio
  - Churn vs complexity (danger zones — requires git history)
  - Language breakdown
  - Dependency depth (longest import chain)
"""

from dataclasses import dataclass, field
from pathlib import Path

from reassure.core.repo_walker import RepoIndex


@dataclass
class FileMetrics:
    path: Path
    lang: str
    loc: int
    function_count: int
    class_count: int
    avg_complexity: float
    import_count: int


@dataclass
class RepoMetrics:
    total_loc: int
    source_loc: int
    test_loc: int
    test_to_source_ratio: float
    language_breakdown: dict[str, int]  # lang → LOC
    file_metrics: list[FileMetrics] = field(default_factory=list)
    churn_hotspots: list[tuple[Path, int, float]] = field(default_factory=list)
    # churn_hotspots: (file, git_churn_count, avg_complexity) — danger zones


def compute_metrics(index: RepoIndex, repo_root: Path | None = None) -> RepoMetrics:
    """
    Compute structural metrics for the full repo index.

    If repo_root is provided and a git repo is detected, also computes
    churn data from git log to identify high-churn + high-complexity danger zones.
    """
    # TODO: implement
    # 1. Aggregate LOC from index.files
    # 2. Count functions/classes per file from symbols
    # 3. Compute language breakdown
    # 4. If git available: `git log --format="%H" -- <file>` for churn counts
    # 5. Cross-reference churn with complexity for hotspot detection
    raise NotImplementedError
