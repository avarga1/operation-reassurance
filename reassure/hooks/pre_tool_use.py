"""
Claude Code PreToolUse hook for operation-reassurance.

Intercepts Write and Edit tool calls before they land and blocks any that
violate repo rules. Errors block the write; warnings are printed but allow it.

Wire up in your project's .claude/settings.json:

    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Write|Edit",
            "hooks": [
              {
                "type": "command",
                "command": "python3 -m reassure.hooks.pre_tool_use"
              }
            ]
          }
        ]
      }
    }

Or globally in ~/.claude/settings.json to apply to every repo.

Claude Code passes the tool call as JSON on stdin:

  Write:  { "tool_name": "Write", "tool_input": { "file_path": "...", "content": "..." } }
  Edit:   { "tool_name": "Edit",  "tool_input": { "file_path": "...", "new_string": "..." } }

Exit 0  → allow the write
Exit 2  → block the write, show output to the agent as feedback
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        # Can't parse — don't block, let the tool proceed
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = Path(tool_input.get("file_path", "")).expanduser().resolve()

    # Write supplies full content; Edit supplies only the new_string being inserted
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        sys.exit(0)

    # Resolve rules for this file
    from reassure.analyzers.repo_rules import (
        PRESETS,
        _detect_default_rules,
        _rules_from_toml,
        check_content,
    )
    from reassure.mcp.server import _find_repo_root

    root = _find_repo_root(file_path)
    toml_path = root / ".reassure.toml" if root else None

    if toml_path and toml_path.exists():
        rules = _rules_from_toml(toml_path)
    elif root:
        rules = _detect_default_rules(root)
    else:
        # No repo root found — fall back to extension-based preset
        _EXT_PRESET = {".dart": "flutter", ".py": "python", ".rs": "rust"}
        preset = _EXT_PRESET.get(file_path.suffix, "general")
        rules = PRESETS[preset]

    # If root still unknown, infer a synthetic one from the path so that
    # patterns like lib/**/*.dart match /anything/lib/auth.dart correctly
    if root is None:
        root = _infer_root(file_path)

    matches = check_content(file_path, content, rules, root)
    if not matches:
        sys.exit(0)

    errors = [m for m in matches if m.rule.severity == "error"]
    warnings = [m for m in matches if m.rule.severity == "warning"]

    # Print structured feedback the agent can read
    lines: list[str] = []
    lines.append(f"reassure: {len(errors)} error(s), {len(warnings)} warning(s) in {file_path.name}")
    lines.append("")

    for m in matches:
        icon = "✗" if m.rule.severity == "error" else "⚠"
        lines.append(f"  {icon} [{m.rule.severity}] {m.rule.name}  line {m.line}")
        lines.append(f"      {m.matched_content.strip()}")
        if m.rule.message:
            lines.append(f"      → {m.rule.message}")
        lines.append("")

    if errors:
        lines.append(f"Blocked: {len(errors)} rule violation(s) must be fixed before writing.")
    else:
        lines.append(f"Allowed with {len(warnings)} warning(s). Fix before merging.")

    print("\n".join(lines))
    # Exit 2 blocks the tool call and surfaces output to the agent
    sys.exit(2 if errors else 0)


def _infer_root(file_path: Path) -> Path | None:
    """Infer a synthetic repo root by finding the parent of a known source dir."""
    _SRC_DIRS = {"lib", "src", "test", "tests", "app"}
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part in _SRC_DIRS and i > 0:
            return Path(*parts[:i])
    return None


if __name__ == "__main__":
    main()
