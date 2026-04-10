"""
Folder structure analyzer.

Enforces feature-first layout rules — the structural contracts that say:
  "lib/pages/ should not exist as a flat dump"
  "lib/features/*/ must contain data/, domain/, presentation/"
  "lib/features/*/presentation/ must stay under 12 files"

Rules are loaded from [[folder_rules]] in .reassure.toml.
If no config is found, built-in default rulesets are applied based on
detected stack (same detection logic as TaxonomyAnalyzer).

Three checks per rule:
  max_files = 0    → folder must not exist as a loose-file dump
  max_files = N    → folder must contain ≤ N direct source files
  required_children → folder must contain these named subdirectories
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from reassure.core.repo_walker import RepoIndex
from reassure.plugin import AnalyzerResult


@dataclass
class FolderRule:
    pattern: str  # glob matched against path relative to repo root
    max_files: int | None = None  # None = no limit; 0 = folder should not hold loose files
    required_children: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class FolderViolation:
    folder: Path  # absolute path of the offending folder
    rule: FolderRule
    reasons: list[str]  # ["22 files (max 0)", "missing: domain/"]


@dataclass
class FolderStructureReport:
    violations: list[FolderViolation] = field(default_factory=list)
    folders_checked: int = 0
    rules_applied: int = 0

    @property
    def has_issues(self) -> bool:
        return bool(self.violations)


# ── default rulesets ──────────────────────────────────────────────────────────

_FLUTTER_RIVERPOD_FOLDER_RULES: list[FolderRule] = [
    FolderRule(
        pattern="lib/pages",
        max_files=0,
        message=(
            "Flat lib/pages/ dump detected. Organize by feature: lib/features/<name>/presentation/."
        ),
    ),
    FolderRule(
        pattern="lib/screens",
        max_files=0,
        message=(
            "Flat lib/screens/ dump detected. "
            "Organize by feature: lib/features/<name>/presentation/."
        ),
    ),
    FolderRule(
        pattern="lib/features/*",
        max_files=0,
        required_children=["data", "domain", "presentation"],
        message=(
            "Feature folders must contain data/, domain/, and presentation/ — not loose files."
        ),
    ),
    FolderRule(
        pattern="lib/features/*/presentation",
        max_files=12,
        message="presentation/ is getting crowded. Consider splitting into sub-features.",
    ),
    FolderRule(
        pattern="lib/features/*/data",
        max_files=8,
        message="data/ is getting crowded. Consider splitting repositories by domain.",
    ),
    FolderRule(
        pattern="lib/features/*/domain",
        max_files=8,
        message="domain/ is getting crowded. Consider grouping models into sub-packages.",
    ),
    FolderRule(
        pattern="lib/core",
        max_files=15,
        message=(
            "lib/core/ is growing large. "
            "If it exceeds 15 files, logic is probably leaking into utilities."
        ),
    ),
]

_FLUTTER_BLOC_FOLDER_RULES: list[FolderRule] = [
    FolderRule(
        pattern="lib/pages",
        max_files=0,
        message="Flat lib/pages/ dump. Organize by feature: lib/features/<name>/.",
    ),
    FolderRule(
        pattern="lib/features/*",
        max_files=0,
        required_children=["bloc", "data", "view"],
        message="Feature folders must contain bloc/, data/, and view/ — not loose files.",
    ),
    FolderRule(
        pattern="lib/features/*/view",
        max_files=10,
        message="view/ is getting crowded. Consider splitting into sub-features.",
    ),
    FolderRule(
        pattern="lib/core",
        max_files=15,
        message="lib/core/ is growing large.",
    ),
]

_FASTAPI_FOLDER_RULES: list[FolderRule] = [
    FolderRule(
        pattern="src/routers",
        max_files=15,
        message="routers/ is growing. Consider grouping by domain into sub-packages.",
    ),
    FolderRule(
        pattern="src/services",
        max_files=15,
        message="services/ is growing. Consider grouping by domain.",
    ),
    FolderRule(
        pattern="src/repositories",
        max_files=15,
        message="repositories/ is growing. Consider grouping by domain.",
    ),
]

_AXUM_FOLDER_RULES: list[FolderRule] = [
    FolderRule(
        pattern="src/handlers",
        max_files=15,
        message="handlers/ is growing. Consider grouping by domain module.",
    ),
    FolderRule(
        pattern="src/services",
        max_files=15,
        message="services/ is growing. Consider splitting into domain modules.",
    ),
]

_DEFAULT_RULESETS: dict[str, list[FolderRule]] = {
    "flutter-riverpod": _FLUTTER_RIVERPOD_FOLDER_RULES,
    "flutter-bloc": _FLUTTER_BLOC_FOLDER_RULES,
    "fastapi": _FASTAPI_FOLDER_RULES,
    "axum": _AXUM_FOLDER_RULES,
}


# ── analyzer ──────────────────────────────────────────────────────────────────


class FolderStructureAnalyzer:
    name = "folder_structure"
    description = (
        "Enforces feature-first folder layout — checks that flat page dumps don't exist, "
        "that feature folders contain the required layers (data/domain/presentation), "
        "and that no layer holds more files than its max. Rules loaded from "
        "[[folder_rules]] in .reassure.toml with built-in defaults for Flutter, FastAPI, Axum."
    )

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        rules = self._load_rules(index.root)
        report = analyze_folder_structure(index.root, rules)

        issues = [
            {
                "folder": str(v.folder),
                "rule_pattern": v.rule.pattern,
                "reasons": v.reasons,
                "message": v.rule.message,
            }
            for v in report.violations
        ]

        return AnalyzerResult(
            name=self.name,
            summary=(
                f"{len(report.violations)} folder structure violations "
                f"({report.folders_checked} folders checked, {report.rules_applied} rules)"
            ),
            data=report,
            issues=issues,
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from reassure.output.terminal import render_folder_structure

        render_folder_structure(result.data, root=root)

    def _load_rules(self, root: Path) -> list[FolderRule]:
        config_path = self._config_path or root / ".reassure.toml"
        if config_path.exists():
            return _rules_from_toml(config_path)
        return _detect_default_rules(root)


# ── core logic ────────────────────────────────────────────────────────────────


def analyze_folder_structure(root: Path, rules: list[FolderRule]) -> FolderStructureReport:
    """
    Walk the repo tree and check each directory against the folder rules.
    """
    report = FolderStructureReport(rules_applied=len(rules))
    checked: set[Path] = set()

    for folder in _walk_dirs(root):
        rel = _rel(folder, root)
        matching = [r for r in rules if _matches_folder_pattern(rel, r.pattern)]
        if not matching:
            continue

        checked.add(folder)
        source_files = _direct_source_files(folder)
        children = _direct_subdirs(folder)

        for rule in matching:
            reasons = _check_folder_rule(folder, rule, source_files, children)
            if reasons:
                report.violations.append(
                    FolderViolation(
                        folder=folder,
                        rule=rule,
                        reasons=reasons,
                    )
                )

    report.folders_checked = len(checked)
    return report


def check_new_file(
    proposed_path: Path,
    root: Path,
    rules: list[FolderRule],
) -> list[FolderViolation]:
    """
    Given a path about to be written, check if it would violate a folder rule.
    Used by the PreToolUse hook — no full walk needed.
    """
    folder = proposed_path.parent
    rel = _rel(folder, root)
    matching = [r for r in rules if _matches_folder_pattern(rel, r.pattern)]
    if not matching:
        return []

    # Count what's already there + the proposed file
    source_files = _direct_source_files(folder)
    source_files_after = source_files + 1  # the proposed addition

    _direct_subdirs(folder)  # reserved for required_children check
    violations = []

    for rule in matching:
        reasons: list[str] = []

        if rule.max_files is not None:
            if rule.max_files == 0 and source_files_after > 0:
                reasons.append(
                    f"writing here creates a flat file dump (rule: max_files=0, "
                    f"would have {source_files_after} files)"
                )
            elif rule.max_files > 0 and source_files_after > rule.max_files:
                reasons.append(
                    f"would exceed {rule.max_files} file limit "
                    f"({source_files_after} files after write)"
                )

        if reasons:
            violations.append(FolderViolation(folder=folder, rule=rule, reasons=reasons))

    return violations


# ── helpers ───────────────────────────────────────────────────────────────────

_SOURCE_EXTENSIONS = {".dart", ".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}
_IGNORE_DIRS = {"__pycache__", ".dart_tool", "build", "dist", "node_modules", ".git", "target"}


def _walk_dirs(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        yield path


def _direct_source_files(folder: Path) -> int:
    """Count direct (non-recursive) source files in a folder."""
    try:
        return sum(1 for f in folder.iterdir() if f.is_file() and f.suffix in _SOURCE_EXTENSIONS)
    except PermissionError:
        return 0


def _direct_subdirs(folder: Path) -> set[str]:
    """Return names of direct subdirectories."""
    try:
        return {f.name for f in folder.iterdir() if f.is_dir() and f.name not in _IGNORE_DIRS}
    except PermissionError:
        return set()


def _check_folder_rule(
    folder: Path,
    rule: FolderRule,
    source_file_count: int,
    children: set[str],
) -> list[str]:
    reasons: list[str] = []

    if rule.max_files is not None:
        if rule.max_files == 0 and source_file_count > 0:
            reasons.append(
                f"flat file dump — {source_file_count} loose source files "
                f"(should be organized into subdirectories)"
            )
        elif rule.max_files > 0 and source_file_count > rule.max_files:
            reasons.append(f"{source_file_count} files exceeds limit of {rule.max_files}")

    for required in rule.required_children:
        if required not in children:
            reasons.append(f"missing required subdirectory: {required}/")

    return reasons


def _matches_folder_pattern(rel: str, pattern: str) -> bool:
    """
    Match a relative folder path against a rule pattern.

    Patterns use fnmatch-style globs where * matches within a single path segment.
    Examples:
      "lib/pages"           matches "lib/pages"
      "lib/features/*"      matches "lib/features/auth", "lib/features/dashboard"
      "lib/features/*/data" matches "lib/features/auth/data"
    """
    # Normalise separators
    rel = rel.replace("\\", "/").rstrip("/")
    pattern = pattern.replace("\\", "/").rstrip("/")

    # Split into segments and match each
    rel_parts = rel.split("/")
    pat_parts = pattern.split("/")

    if len(rel_parts) != len(pat_parts):
        return False

    return all(fnmatch.fnmatch(r, p) for r, p in zip(rel_parts, pat_parts, strict=False))


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ── config loading ────────────────────────────────────────────────────────────


def _rules_from_toml(path: Path) -> list[FolderRule]:
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        return []

    raw = cfg.get("folder_rules", [])
    result: list[FolderRule] = []

    for r in raw:
        if "pattern" not in r:
            continue
        result.append(
            FolderRule(
                pattern=r["pattern"],
                max_files=r.get("max_files"),
                required_children=r.get("required_children", []),
                message=r.get("message", ""),
            )
        )

    if not result:
        # Fall back to defaults based on declared stack
        stack = cfg.get("taxonomy", {}).get("stack", "")
        result.extend(_stack_to_default_rules(stack))

    return result


def _detect_default_rules(root: Path) -> list[FolderRule]:
    """Walk up from root to find stack config files and return matching default rules."""
    from reassure.analyzers.taxonomy import _find_upward

    pubspec = _find_upward(root, "pubspec.yaml")
    if not pubspec:
        candidates = list(root.glob("*/pubspec.yaml"))
        pubspec = candidates[0] if candidates else None

    if pubspec and pubspec.exists():
        text = pubspec.read_text()
        if "flutter_riverpod" in text or "riverpod" in text:
            return _FLUTTER_RIVERPOD_FOLDER_RULES
        if "flutter_bloc" in text:
            return _FLUTTER_BLOC_FOLDER_RULES
        # Unknown Flutter state management — still apply layout rules
        return _FLUTTER_RIVERPOD_FOLDER_RULES

    pyproject = _find_upward(root, "pyproject.toml")
    if pyproject and pyproject.exists():
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = set(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
            if "fastapi" in {d.lower() for d in deps}:
                return _FASTAPI_FOLDER_RULES
        except Exception:
            pass

    cargo = _find_upward(root, "Cargo.toml")
    if cargo and cargo.exists():
        try:
            with open(cargo, "rb") as f:
                data = tomllib.load(f)
            if "axum" in data.get("dependencies", {}):
                return _AXUM_FOLDER_RULES
        except Exception:
            pass

    return []


def _stack_to_default_rules(stack: str) -> list[FolderRule]:
    for key, rules in _DEFAULT_RULESETS.items():
        if key in stack:
            return rules
    return []
