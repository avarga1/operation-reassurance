"""Tests for reassure.analyzers.observability — focusing on Dart false-positive fix."""

import tempfile
from pathlib import Path

import pytest

from reassure.analyzers.observability import (
    _DART_OBS,
    _has_obs_call_dart,
    analyze_observability,
)
from reassure.core.parser import parse_file
from reassure.core.repo_walker import walk_repo

# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_dart(source: str):
    """Write source to a temp .dart file and return (root_node, source)."""
    with tempfile.NamedTemporaryFile(suffix=".dart", mode="w", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    result = parse_file(path)
    path.unlink(missing_ok=True)
    return result  # (tree, source) or None


def _dart_body_node(source: str):
    """Return the function_body node for a single-method Dart class."""
    result = _parse_dart(source)
    if result is None:
        return None, None
    tree, src = result
    root = tree.root_node

    def _find(node):
        if node.type == "function_body":
            return node
        for child in node.children:
            found = _find(child)
            if found:
                return found
        return None

    return _find(root), src


# ── Dart OTel patterns present ────────────────────────────────────────────────


class TestDartObsPatterns:
    def test_otel_patterns_in_dart_obs(self):
        """Key OTel Dart SDK patterns must be in _DART_OBS."""
        required = {
            "tracer",
            "startSpan",
            "setAttribute",
            "globalTracerProvider",
            "getTracer",
            "_telemetry",
        }
        assert required <= _DART_OBS, f"Missing: {required - _DART_OBS}"

    def test_telemetry_record_method_in_dart_obs(self):
        assert "recordClientWrite" in _DART_OBS or "_telemetry" in _DART_OBS


# ── _has_obs_call_dart ────────────────────────────────────────────────────────


class TestHasObsCallDart:
    def test_telemetry_call_detected(self):
        source = (
            "class X {\n"
            "  void write(String key) {\n"
            "    _telemetry.recordClientWrite(key);\n"
            "  }\n"
            "}\n"
        )
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert _has_obs_call_dart(body, src, _DART_OBS)

    def test_otel_tracer_start_span_detected(self):
        source = (
            "class X {\n"
            "  void write(String key) {\n"
            "    final span = tracer.startSpan('write');\n"
            "  }\n"
            "}\n"
        )
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert _has_obs_call_dart(body, src, _DART_OBS)

    def test_global_tracer_provider_detected(self):
        source = (
            "class X {\n  void init() {\n    globalTracerProvider.getTracer('my-lib');\n  }\n}\n"
        )
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert _has_obs_call_dart(body, src, _DART_OBS)

    def test_dark_function_not_detected(self):
        source = "class X {\n  void compute(int x) {\n    return x * 2;\n  }\n}\n"
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert not _has_obs_call_dart(body, src, _DART_OBS)

    def test_debug_print_alone_not_obs(self):
        """debugPrint is excluded — it's stripped in release builds."""
        source = "class X {\n  void log(String msg) {\n    debugPrint(msg);\n  }\n}\n"
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert not _has_obs_call_dart(body, src, _DART_OBS)

    def test_sentry_capture_detected(self):
        source = "class X {\n  void onError(Object e) {\n    Sentry.captureException(e);\n  }\n}\n"
        body, src = _dart_body_node(source)
        if body is None:
            pytest.skip("Dart parse failed")
        assert _has_obs_call_dart(body, src, _DART_OBS)


# ── analyze_observability on Dart fixtures ────────────────────────────────────


class TestDartObservabilityAnalysis:
    def test_instrumented_dart_not_dark(self, tmp_path):
        dart_file = tmp_path / "lib" / "databus.dart"
        dart_file.parent.mkdir(parents=True)
        dart_file.write_text(
            "class DataBus {\n"
            "  void write(String key, dynamic value) {\n"
            "    _telemetry.recordClientWrite(key);\n"
            "    final span = tracer.startSpan('write');\n"
            "    span.setAttribute('key', key);\n"
            "    span.end();\n"
            "  }\n"
            "}\n"
        )
        index = walk_repo(tmp_path)
        report = analyze_observability(index)
        dark_names = {g.symbol.file.name for g in report.gaps}
        assert "databus.dart" not in dark_names, (
            "databus.dart has OTel instrumentation but was reported as dark — "
            "Dart call detection is broken"
        )

    def test_uninstrumented_dart_is_dark(self, tmp_path):
        dart_file = tmp_path / "lib" / "helper.dart"
        dart_file.parent.mkdir(parents=True)
        dart_file.write_text(
            "class Helper {\n  String format(String s) {\n    return s.toUpperCase();\n  }\n}\n"
        )
        index = walk_repo(tmp_path)
        report = analyze_observability(index)
        dark_names = {g.symbol.file.name for g in report.gaps}
        assert "helper.dart" in dark_names
