"""
Repo rules analyzer.

Enforces repo-wide content rules that apply regardless of file type or location.
Unlike taxonomy rules (file-pattern contracts) or folder rules (layout contracts),
repo rules express universal invariants:

  "No mock data inlined in production code"
  "No hardcoded URLs"
  "No print() in lib/"
  "No TODO/FIXME in prod"

Rules are loaded from [[repo_rules]] in .reassure.toml.
If no config is found, built-in presets are applied based on detected stack.

Each rule has:
  name              — identifier shown in output and MCP responses
  pattern           — glob for which files to check (e.g. "lib/**/*.dart")
  forbidden_content — list of strings/patterns that must not appear
  severity          — "error" (blocks) or "warning" (flags but doesn't block)
  message           — shown to the LLM when the rule is violated
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from reassure.core.repo_walker import RepoIndex
from reassure.plugin import AnalyzerResult


@dataclass
class RepoRule:
    name: str
    pattern: str  # glob against repo-relative path, e.g. "lib/**/*.dart"
    forbidden_content: list[str] = field(default_factory=list)
    severity: str = "error"  # "error" | "warning"
    message: str = ""
    is_regex: bool = False  # treat forbidden_content as regex patterns


@dataclass
class RepoRuleMatch:
    file: Path
    rule: RepoRule
    line: int
    matched_content: str  # the actual line that triggered the violation


@dataclass
class RepoRulesReport:
    matches: list[RepoRuleMatch] = field(default_factory=list)
    files_checked: int = 0
    rules_applied: int = 0

    @property
    def errors(self) -> list[RepoRuleMatch]:
        return [m for m in self.matches if m.rule.severity == "error"]

    @property
    def warnings(self) -> list[RepoRuleMatch]:
        return [m for m in self.matches if m.rule.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_issues(self) -> bool:
        return bool(self.matches)


# ── built-in presets ──────────────────────────────────────────────────────────

PRESETS: dict[str, list[RepoRule]] = {
    "flutter": [
        RepoRule(
            name="no-print-in-prod",
            pattern="lib/**/*.dart",
            forbidden_content=["print("],
            severity="error",
            message="Use a logger (package:logging or similar). print() is not stripped in release builds.",
        ),
        RepoRule(
            name="no-inline-mock-data",
            pattern="lib/**/*.dart",
            forbidden_content=[
                "MockData(",
                "FakeData(",
                "DummyData(",
                "fakeUser",
                "dummyUser",
                "testUser",
                "mockUser",
                "hardcodedToken",
                "fake_token",
                "test_token",
            ],
            severity="error",
            message="Mock data belongs in test fixtures, not production code.",
        ),
        RepoRule(
            name="no-hardcoded-urls",
            pattern="lib/**/*.dart",
            forbidden_content=["'http://", '"http://', "'https://", '"https://'],
            severity="error",
            message="URLs belong in a config file or environment constants, not inlined.",
        ),
        RepoRule(
            name="no-localhost",
            pattern="lib/**/*.dart",
            forbidden_content=["localhost:", "127.0.0.1", "0.0.0.0"],
            severity="error",
            message="Localhost references must not ship in production code.",
        ),
        RepoRule(
            name="no-todo-in-prod",
            pattern="lib/**/*.dart",
            forbidden_content=["// TODO", "// FIXME", "// HACK", "// XXX"],
            severity="warning",
            message="Resolve before shipping.",
        ),
        RepoRule(
            name="no-debug-flags",
            pattern="lib/**/*.dart",
            forbidden_content=["kDebugMode && print", "debugPrint(", "assert(false"],
            severity="warning",
            message="Remove debug-only code paths before release.",
        ),
        RepoRule(
            name="no-inline-box-decoration",
            pattern="lib/**/*.dart",
            forbidden_content=["BoxDecoration("],
            severity="warning",
            message="Extract BoxDecoration to a theme extension or a named const style variable.",
        ),
        RepoRule(
            name="no-inline-opacity",
            pattern="lib/**/*.dart",
            forbidden_content=[".withValues(alpha:", ".withOpacity("],
            severity="warning",
            message="Use a named color token from your theme instead of inline alpha/opacity.",
        ),
        RepoRule(
            name="no-raw-border-radius",
            pattern="lib/**/*.dart",
            forbidden_content=["BorderRadius.circular(", "BorderRadius.only(", "BorderRadius.all("],
            severity="warning",
            message="Use theme radius tokens (e.g. theme.radii.*) instead of hardcoded BorderRadius.",
        ),
        RepoRule(
            name="no-raw-edge-insets",
            pattern="lib/**/*.dart",
            forbidden_content=["EdgeInsets.symmetric(", "EdgeInsets.all(", "EdgeInsets.only(", "EdgeInsets.fromLTRB("],
            severity="warning",
            message="Use theme spacing tokens instead of hardcoded EdgeInsets.",
        ),
        RepoRule(
            name="no-hardcoded-colors",
            pattern="lib/**/*.dart",
            forbidden_content=["Colors.red", "Colors.blue", "Colors.green", "Colors.black", "Colors.white", "Colors.grey", "Color(0x", "Color.fromARGB(", "Color.fromRGBO("],
            severity="warning",
            message="Use theme.colorScheme.* instead of hardcoded colors.",
        ),
        RepoRule(
            name="no-inline-text-style",
            pattern="lib/**/*.dart",
            forbidden_content=["TextStyle(fontSize:", "TextStyle(fontWeight:", "TextStyle(color:", "TextStyle(fontFamily:"],
            severity="warning",
            message="Use theme.textTheme.* instead of inline TextStyle.",
        ),
        RepoRule(
            name="no-imperative-navigation",
            pattern="lib/**/*.dart",
            forbidden_content=["Navigator.of(context).push", "Navigator.push(", "Navigator.pushNamed(", "Navigator.pop("],
            severity="warning",
            message="Use a declarative router (go_router / auto_route) instead of Navigator directly.",
        ),
        RepoRule(
            name="no-media-query-size",
            pattern="lib/**/*.dart",
            forbidden_content=["MediaQuery.of(context).size", "MediaQuery.of(context).width", "MediaQuery.of(context).height"],
            severity="warning",
            message="Use MediaQuery.sizeOf(context) — the .of() accessor rebuilds on any MediaQuery change.",
        ),
        RepoRule(
            name="no-null-bang",
            pattern="lib/**/*.dart",
            forbidden_content=["!;", "! ,", "! )", "!,\n", "!)"],
            severity="warning",
            message="Avoid the null-bang operator (!). Use null-safe patterns, early returns, or provide a fallback.",
        ),
        RepoRule(
            name="no-future-delayed-zero",
            pattern="lib/**/*.dart",
            forbidden_content=["Future.delayed(Duration.zero", "Future.delayed(const Duration()"],
            severity="warning",
            message="Future.delayed(Duration.zero) is a frame-defer hack. Fix the lifecycle issue instead (use addPostFrameCallback).",
        ),
        RepoRule(
            name="no-raw-sized-box-spacing",
            pattern="lib/**/*.dart",
            forbidden_content=["SizedBox(height:", "SizedBox(width:"],
            severity="warning",
            message="Use theme spacing tokens instead of hardcoded SizedBox dimensions.",
        ),
    ],
    "python": [
        RepoRule(
            name="no-print-debug",
            pattern="src/**/*.py",
            forbidden_content=["print("],
            severity="warning",
            message="Use logging instead of print() in production code.",
        ),
        RepoRule(
            name="no-hardcoded-secrets",
            pattern="**/*.py",
            forbidden_content=[
                "password =",
                "secret =",
                "api_key =",
                "API_KEY =",
                "SECRET_KEY =",
                "token =",
            ],
            severity="error",
            message="Secrets must not be hardcoded. Use environment variables or a secrets manager.",
        ),
        RepoRule(
            name="no-bare-except",
            pattern="**/*.py",
            forbidden_content=["except:"],
            severity="error",
            message="Bare except catches everything including KeyboardInterrupt. Catch specific exceptions.",
        ),
        RepoRule(
            name="no-inline-mock-data",
            pattern="src/**/*.py",
            forbidden_content=["mock_data", "fake_data", "dummy_data", "test_token", "fake_token"],
            severity="error",
            message="Mock data belongs in test fixtures, not production code.",
        ),
        RepoRule(
            name="no-todo-in-prod",
            pattern="src/**/*.py",
            forbidden_content=["# TODO", "# FIXME", "# HACK"],
            severity="warning",
            message="Resolve before shipping.",
        ),
    ],
    "rust": [
        RepoRule(
            name="no-unwrap-in-prod",
            pattern="src/**/*.rs",
            forbidden_content=[".unwrap()", ".expect("],
            severity="warning",
            message="Prefer proper error handling over unwrap/expect in production paths.",
        ),
        RepoRule(
            name="no-todo-macro",
            pattern="src/**/*.rs",
            forbidden_content=["todo!(", "unimplemented!(", "panic!("],
            severity="error",
            message="todo!/unimplemented!/panic! must not ship in production.",
        ),
        RepoRule(
            name="no-println-in-prod",
            pattern="src/**/*.rs",
            forbidden_content=["println!(", "dbg!(", "eprintln!("],
            severity="warning",
            message="Use the tracing or log crate instead of println!/dbg!.",
        ),
        RepoRule(
            name="no-hardcoded-secrets",
            pattern="src/**/*.rs",
            forbidden_content=[
                'password = "',
                'secret = "',
                'api_key = "',
                'token = "',
            ],
            severity="error",
            message="Secrets must not be hardcoded.",
        ),
    ],
    "general": [
        RepoRule(
            name="no-todo-in-prod",
            pattern="**/*",
            forbidden_content=["TODO", "FIXME", "HACK"],
            severity="warning",
            message="Resolve before shipping.",
        ),
        RepoRule(
            name="no-hardcoded-secrets",
            pattern="**/*",
            forbidden_content=[
                "password=",
                "secret=",
                "api_key=",
                "apikey=",
                "access_token=",
            ],
            severity="error",
            message="Secrets must not be hardcoded.",
        ),
    ],
}

# Stack → preset keys to apply
_STACK_PRESETS: dict[str, list[str]] = {
    "flutter": ["flutter"],
    "fastapi": ["python"],
    "axum": ["rust"],
}


# ── analyzer ──────────────────────────────────────────────────────────────────


class RepoRulesAnalyzer:
    name = "repo_rules"
    description = (
        "Enforces repo-wide content rules — no mock data inlined, no hardcoded URLs, "
        "no print() in prod, no TODO/FIXME, no bare except. Rules loaded from "
        "[[repo_rules]] in .reassure.toml with built-in presets for Flutter, Python, Rust."
    )

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path

    def analyze(self, index: RepoIndex) -> AnalyzerResult:
        rules = self._load_rules(index.root)
        report = analyze_repo_rules(index, rules)

        issues = [
            {
                "file": str(m.file),
                "line": m.line,
                "rule": m.rule.name,
                "severity": m.rule.severity,
                "matched": m.matched_content.strip(),
                "message": m.rule.message,
            }
            for m in report.matches
        ]

        error_count = len(report.errors)
        warn_count = len(report.warnings)
        parts = []
        if error_count:
            parts.append(f"{error_count} errors")
        if warn_count:
            parts.append(f"{warn_count} warnings")

        return AnalyzerResult(
            name=self.name,
            summary=(
                f"{', '.join(parts) if parts else 'clean'} "
                f"({report.files_checked} files, {report.rules_applied} rules)"
            ),
            data=report,
            issues=issues,
        )

    def render_terminal(self, result: AnalyzerResult, root: Path) -> None:
        from reassure.output.terminal import render_repo_rules

        render_repo_rules(result.data, root=root)

    def _load_rules(self, root: Path) -> list[RepoRule]:
        config_path = self._config_path or root / ".reassure.toml"
        if config_path.exists():
            rules = _rules_from_toml(config_path)
            if rules:
                return rules
        return _detect_default_rules(root)


# ── core logic ────────────────────────────────────────────────────────────────


def analyze_repo_rules(index: RepoIndex, rules: list[RepoRule]) -> RepoRulesReport:
    report = RepoRulesReport(rules_applied=len(rules))
    checked: set[Path] = set()

    for file in index.source_files:
        if file.source is None:
            continue

        rel = _rel(file.path, index.root)
        matching = [r for r in rules if _matches_glob(rel, r.pattern)]
        if not matching:
            continue

        checked.add(file.path)
        lines = file.source.splitlines()

        for rule in matching:
            for lineno, line in enumerate(lines, 1):
                for forbidden in rule.forbidden_content:
                    if rule.is_regex:
                        if re.search(forbidden, line):
                            report.matches.append(
                                RepoRuleMatch(
                                    file=file.path,
                                    rule=rule,
                                    line=lineno,
                                    matched_content=line,
                                )
                            )
                            break
                    else:
                        if forbidden in line:
                            report.matches.append(
                                RepoRuleMatch(
                                    file=file.path,
                                    rule=rule,
                                    line=lineno,
                                    matched_content=line,
                                )
                            )
                            break

    report.files_checked = len(checked)
    return report


def check_content(
    path: Path,
    content: str,
    rules: list[RepoRule],
    root: Path | None = None,
) -> list[RepoRuleMatch]:
    """
    Check proposed file content against repo rules.
    Used by the PreToolUse hook and check_repo_rules MCP tool.
    """
    rel = _rel(path, root) if root else path.name
    matching = [r for r in rules if _matches_glob(rel, r.pattern)]
    if not matching:
        return []

    matches: list[RepoRuleMatch] = []
    lines = content.splitlines()

    for rule in matching:
        for lineno, line in enumerate(lines, 1):
            for forbidden in rule.forbidden_content:
                hit = re.search(forbidden, line) if rule.is_regex else forbidden in line
                if hit:
                    matches.append(
                        RepoRuleMatch(file=path, rule=rule, line=lineno, matched_content=line)
                    )
                    break

    return matches


def list_presets() -> dict[str, list[str]]:
    """Return available preset names and their rule names."""
    return {name: [r.name for r in rules] for name, rules in PRESETS.items()}


# ── helpers ───────────────────────────────────────────────────────────────────


def _matches_glob(rel: str, pattern: str) -> bool:
    """Match a repo-relative file path against a glob pattern.

    Supports ** to match zero or more path segments, e.g. lib/**/*.dart
    matches both lib/a.dart and lib/src/auth/a.dart.
    """
    import fnmatch

    rel_parts = rel.replace("\\", "/").split("/")
    pat_parts = pattern.replace("\\", "/").split("/")

    def _match(rp: list[str], pp: list[str]) -> bool:
        if not pp:
            return not rp
        if pp[0] == "**":
            # ** matches zero or more segments
            rest_pp = pp[1:]
            return any(_match(rp[i:], rest_pp) for i in range(len(rp) + 1))
        if not rp:
            return False
        return fnmatch.fnmatch(rp[0], pp[0]) and _match(rp[1:], pp[1:])

    return _match(rel_parts, pat_parts)


def _rel(path: Path, root: Path | None) -> str:
    if not path.is_absolute():
        # Already a relative path — use as-is so patterns like lib/**/*.dart work
        return str(path).replace("\\", "/")
    if root is None:
        return path.name
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


# ── config ────────────────────────────────────────────────────────────────────


def _rules_from_toml(path: Path) -> list[RepoRule]:
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        return []

    raw = cfg.get("repo_rules", [])
    result: list[RepoRule] = []

    for r in raw:
        if "name" not in r or "pattern" not in r:
            continue
        result.append(
            RepoRule(
                name=r["name"],
                pattern=r["pattern"],
                forbidden_content=r.get("forbidden_content", []),
                severity=r.get("severity", "error"),
                message=r.get("message", ""),
                is_regex=r.get("is_regex", False),
            )
        )

    # Allow opting into presets from config
    for preset_name in cfg.get("repo_rules_presets", []):
        result.extend(PRESETS.get(preset_name, []))

    return result


def _find_upward(start: Path, filename: str) -> Path | None:
    """Walk up directory tree looking for a file by name."""
    current = start if start.is_dir() else start.parent
    for _ in range(10):
        candidate = current / filename
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _detect_default_rules(root: Path) -> list[RepoRule]:
    """Walk up from root to detect stack and return matching preset."""
    pubspec = _find_upward(root, "pubspec.yaml")
    if not pubspec:
        candidates = list(root.glob("*/pubspec.yaml"))
        pubspec = candidates[0] if candidates else None

    if pubspec and pubspec.exists():
        return PRESETS["flutter"]

    pyproject = _find_upward(root, "pyproject.toml")
    if not pyproject:
        candidates = list(root.glob("*/pyproject.toml"))
        pyproject = candidates[0] if candidates else None

    if pyproject and pyproject.exists():
        return PRESETS["python"]

    cargo = _find_upward(root, "Cargo.toml")
    if not cargo:
        candidates = list(root.glob("*/Cargo.toml"))
        cargo = candidates[0] if candidates else None

    if cargo and cargo.exists():
        return PRESETS["rust"]

    return PRESETS["general"]
