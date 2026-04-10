"""Tests for reassure.hooks.pre_tool_use."""

import json
import subprocess
import sys
from pathlib import Path


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "reassure.hooks.pre_tool_use"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )


class TestPreToolUseHook:
    def test_non_write_tool_exits_0(self):
        result = _run_hook({"tool_name": "Read", "tool_input": {"file_path": "/repo/lib/a.dart"}})
        assert result.returncode == 0

    def test_clean_dart_file_exits_0(self):
        result = _run_hook({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/repo/lib/auth.dart",
                "content": "class AuthService {\n  void login() {}\n}\n",
            },
        })
        assert result.returncode == 0

    def test_print_in_lib_exits_2(self):
        result = _run_hook({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/repo/lib/auth.dart",
                "content": "void f() { print('debug'); }\n",
            },
        })
        assert result.returncode == 2
        assert "no-print-in-prod" in result.stdout
        assert "Blocked" in result.stdout

    def test_warning_only_exits_0(self):
        result = _run_hook({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/repo/lib/widgets/chip.dart",
                "content": "// TODO: clean this up\n",
            },
        })
        assert result.returncode == 0
        assert "warning" in result.stdout

    def test_edit_new_string_checked(self):
        result = _run_hook({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/repo/lib/services/api.dart",
                "old_string": "final url = '';",
                "new_string": "final url = 'https://api.example.com';",
            },
        })
        assert result.returncode == 2
        assert "no-hardcoded-urls" in result.stdout

    def test_malformed_json_exits_0(self):
        result = subprocess.run(
            [sys.executable, "-m", "reassure.hooks.pre_tool_use"],
            input="not json",
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0

    def test_empty_content_exits_0(self):
        result = _run_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": "/repo/lib/a.dart", "content": ""},
        })
        assert result.returncode == 0
