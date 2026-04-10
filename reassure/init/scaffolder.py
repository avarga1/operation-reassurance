"""
Project scaffolder.

Copies a template directory to a target path, rendering {{placeholders}}
in both file contents and file/directory names.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from reassure.init.detector import StackProfile

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
PARTIALS_DIR = TEMPLATES_DIR / "_partials"


def scaffold(
    template_key: str,
    target: Path,
    project_name: str,
    overwrite: bool = False,
) -> list[Path]:
    """
    Render a template into *target*.

    Returns a list of created file paths.
    Raises FileExistsError if *target* exists and *overwrite* is False.
    """
    template_dir = TEMPLATES_DIR / template_key
    if not template_dir.exists():
        raise ValueError(f"No template found for '{template_key}'. "
                         f"Available: {list_templates()}")

    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists. Pass overwrite=True to replace.")

    target.mkdir(parents=True, exist_ok=True)

    ctx = _build_context(project_name, template_key)
    created: list[Path] = []

    # Copy partials first (base .reassure.toml, .mcp.json, CLAUDE.md)
    if PARTIALS_DIR.exists():
        _copy_tree(PARTIALS_DIR, target, ctx, created)

    # Copy template (overrides any conflicting partials)
    _copy_tree(template_dir, target, ctx, created)

    return created


def install_rules(profile: StackProfile, target: Path) -> Path:
    """
    Write only the .reassure.toml rules into an existing project at *target*.
    Does not scaffold any source files.

    Returns the path to the written config.
    """
    if not profile.template_key:
        raise ValueError(
            f"Cannot install rules for unknown stack: {profile.description}. "
            "Run 'reassure init' interactively to pick a template."
        )

    partials_toml = PARTIALS_DIR / ".reassure.toml.tmpl"
    template_toml = TEMPLATES_DIR / profile.template_key / ".reassure.toml.tmpl"

    # Template-specific config takes priority over partial
    source = template_toml if template_toml.exists() else partials_toml
    if not source.exists():
        raise FileNotFoundError(f"No .reassure.toml template found at {source}")

    ctx = _build_context(target.name, profile.template_key)
    dest = target / ".reassure.toml"
    dest.write_text(_render(source.read_text(), ctx))
    return dest


def list_templates() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return [
        d.name for d in sorted(TEMPLATES_DIR.iterdir())
        if d.is_dir() and not d.name.startswith("_")
    ]


# ── internals ────────────────────────────────────────────────────────────────

def _build_context(project_name: str, template_key: str) -> dict[str, str]:
    return {
        "project_name": project_name,
        "project_name_snake": re.sub(r"[^a-z0-9]+", "_", project_name.lower()),
        "project_name_pascal": _to_pascal(project_name),
        "template_key": template_key,
    }


def _copy_tree(src: Path, dst: Path, ctx: dict[str, str], created: list[Path]) -> None:
    for src_path in sorted(src.rglob("*")):
        if not src_path.is_file():
            continue

        rel = src_path.relative_to(src)
        # Render placeholders in path segments
        rendered_parts = [_render(part, ctx) for part in rel.parts]
        # Strip .tmpl extension from destination
        dest_name = rendered_parts[-1]
        if dest_name.endswith(".tmpl"):
            dest_name = dest_name[:-5]
        rendered_parts[-1] = dest_name

        dst_path = dst.joinpath(*rendered_parts)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_text(_render(src_path.read_text(), ctx))
        created.append(dst_path)


def _render(text: str, ctx: dict[str, str]) -> str:
    for key, value in ctx.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _to_pascal(name: str) -> str:
    return "".join(word.capitalize() for word in re.split(r"[^a-zA-Z0-9]+", name) if word)
