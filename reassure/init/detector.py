"""
Stack detector.

Sniffs a repository root for known config files and returns a StackProfile
describing the detected framework, state management, backend, and database.
Used by `reassure init` both for new project setup and for applying the right
default taxonomy ruleset to an existing repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import toml


@dataclass
class StackProfile:
    """Detected technology stack for a repository."""

    # Frontend
    frontend: str | None = None          # "flutter", "nextjs", "react"
    state_management: str | None = None  # "riverpod", "bloc", "zustand", "jotai"

    # Backend
    backend: str | None = None           # "fastapi", "axum", "trpc", "none"

    # Database
    database: str | None = None          # "postgres", "sqlite", "supabase", "none"

    # Template key — set if a known template matches exactly
    template_key: str | None = None

    # Human-readable description
    description: str = ""

    # Warnings for ambiguous or partial detection
    warnings: list[str] = field(default_factory=list)

    @property
    def is_known(self) -> bool:
        return self.template_key is not None


# Map from template_key → human label
KNOWN_TEMPLATES: dict[str, str] = {
    "flutter-riverpod-pg": "Flutter (Riverpod) + Postgres",
    "flutter-bloc-pg":     "Flutter (BLoC) + Postgres",
    "next-trpc-pg":        "Next.js + tRPC + Postgres",
    "next-fastapi-pg":     "Next.js + FastAPI + Postgres",
    "next-axum-pg":        "Next.js + Axum + Postgres",
    "spa-fastapi-pg":      "Vite/React + FastAPI + Postgres",
}


def detect(root: Path) -> StackProfile:
    """
    Detect the stack at *root* by inspecting config files.

    Detection is non-destructive and read-only. Unknown stacks still return
    a partial StackProfile — callers should check `profile.is_known` before
    attempting template scaffolding.
    """
    profile = StackProfile()

    _detect_flutter(root, profile)
    _detect_python_backend(root, profile)
    _detect_rust_backend(root, profile)
    _detect_node(root, profile)
    _detect_database(root, profile)
    _resolve_template_key(profile)
    _build_description(profile)

    return profile


# ── per-ecosystem sniffers ────────────────────────────────────────────────────

def _detect_flutter(root: Path, profile: StackProfile) -> None:
    pubspec = root / "pubspec.yaml"
    if not pubspec.exists():
        # Also check one level deep (monorepo: frontend/pubspec.yaml)
        candidates = list(root.glob("*/pubspec.yaml"))
        if not candidates:
            return
        pubspec = candidates[0]

    try:
        import yaml  # type: ignore[import]
        yaml.safe_load(pubspec.read_text())
    except Exception:
        # Fall back to raw text scan if pyyaml not installed
        text = pubspec.read_text()
    else:
        text = pubspec.read_text()

    profile.frontend = "flutter"

    deps_text = text  # always scan raw text — yaml parsing is best-effort
    if "flutter_riverpod" in deps_text or "riverpod" in deps_text:
        profile.state_management = "riverpod"
    elif "flutter_bloc" in deps_text:
        profile.state_management = "bloc"
    elif "get:" in deps_text or "getx" in deps_text.lower():
        profile.state_management = "getx"
        profile.warnings.append("GetX detected — no built-in taxonomy ruleset yet")
    elif "provider:" in deps_text:
        profile.state_management = "provider"
        profile.warnings.append("Provider detected — consider migrating to Riverpod")


def _detect_python_backend(root: Path, profile: StackProfile) -> None:
    for candidate in [root / "pyproject.toml", *root.glob("*/pyproject.toml")]:
        if not candidate.exists():
            continue
        try:
            data = toml.load(candidate)
        except Exception:
            continue
        deps = _flatten_deps(data)
        if "fastapi" in deps:
            profile.backend = "fastapi"
            return


def _detect_rust_backend(root: Path, profile: StackProfile) -> None:
    for candidate in [root / "Cargo.toml", *root.glob("*/Cargo.toml")]:
        if not candidate.exists():
            continue
        try:
            data = toml.load(candidate)
        except Exception:
            continue
        deps = _flatten_deps(data)
        if "axum" in deps:
            profile.backend = "axum"
            return
        if "actix-web" in deps:
            profile.backend = "actix"
            profile.warnings.append("Actix-web detected — no built-in taxonomy ruleset yet")
            return


def _detect_node(root: Path, profile: StackProfile) -> None:
    for candidate in [root / "package.json", *root.glob("*/package.json")]:
        if not candidate.exists():
            continue
        # Skip node_modules
        if "node_modules" in candidate.parts:
            continue
        try:
            import json
            data = json.loads(candidate.read_text())
        except Exception:
            continue

        all_deps: dict = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))

        if "next" in all_deps:
            profile.frontend = profile.frontend or "nextjs"
            if "@trpc/server" in all_deps or "@trpc/client" in all_deps:
                profile.backend = "trpc"
        elif "vite" in all_deps and ("react" in all_deps or "react-dom" in all_deps):
            profile.frontend = profile.frontend or "react"
        return


def _detect_database(root: Path, profile: StackProfile) -> None:
    # Check for Postgres indicators
    indicators = [
        root / "docker-compose.yml",
        root / "docker-compose.yaml",
        *root.glob("**/migrations/*.sql"),
        *root.glob("db/migrations"),
    ]
    for path in indicators:
        if not path.exists():
            continue
        try:
            text = path.read_text().lower()
        except Exception:
            continue
        if "postgres" in text or "postgresql" in text:
            profile.database = "postgres"
            return
        if "supabase" in text:
            profile.database = "supabase"
            return

    # Check pyproject / Cargo for db drivers
    for candidate in [*root.glob("**/pyproject.toml"), *root.glob("**/Cargo.toml")]:
        if "node_modules" in candidate.parts:
            continue
        try:
            data = toml.load(candidate)
        except Exception:
            continue
        deps = _flatten_deps(data)
        if any(d in deps for d in ("asyncpg", "psycopg2", "psycopg", "sqlx")):
            profile.database = "postgres"
            return
        if "sqlite" in deps or "rusqlite" in deps:
            profile.database = "sqlite"
            return


# ── resolution ────────────────────────────────────────────────────────────────

def _resolve_template_key(profile: StackProfile) -> None:
    mapping: list[tuple[dict, str]] = [
        ({"frontend": "flutter", "state_management": "riverpod", "database": "postgres"}, "flutter-riverpod-pg"),
        ({"frontend": "flutter", "state_management": "bloc",     "database": "postgres"}, "flutter-bloc-pg"),
        ({"frontend": "nextjs",  "backend": "trpc",              "database": "postgres"}, "next-trpc-pg"),
        ({"frontend": "nextjs",  "backend": "fastapi",           "database": "postgres"}, "next-fastapi-pg"),
        ({"frontend": "nextjs",  "backend": "axum",              "database": "postgres"}, "next-axum-pg"),
        ({"frontend": "react",   "backend": "fastapi",           "database": "postgres"}, "spa-fastapi-pg"),
    ]
    for criteria, key in mapping:
        if all(getattr(profile, k) == v for k, v in criteria.items()):
            profile.template_key = key
            return


def _build_description(profile: StackProfile) -> None:
    if profile.template_key:
        profile.description = KNOWN_TEMPLATES[profile.template_key]
        return
    parts = []
    if profile.frontend:
        sm = f" ({profile.state_management})" if profile.state_management else ""
        parts.append(f"{profile.frontend}{sm}")
    if profile.backend:
        parts.append(profile.backend)
    if profile.database:
        parts.append(profile.database)
    profile.description = " + ".join(parts) if parts else "unknown stack"


# ── helpers ───────────────────────────────────────────────────────────────────

def _flatten_deps(toml_data: dict) -> set[str]:
    """Extract all dependency names from a pyproject.toml or Cargo.toml."""
    deps: set[str] = set()

    # pyproject.toml: [tool.poetry.dependencies] or [project.dependencies]
    poetry_deps = toml_data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    deps.update(k.lower() for k in poetry_deps)

    project_deps = toml_data.get("project", {}).get("dependencies", [])
    for d in project_deps:
        deps.add(d.split("[")[0].split(">=")[0].split("==")[0].strip().lower())

    # Cargo.toml: [dependencies]
    cargo_deps = toml_data.get("dependencies", {})
    deps.update(k.lower() for k in cargo_deps)

    return deps
