"""Tests for reassure.analyzers.async_linter."""

from pathlib import Path

from reassure.analyzers.async_linter import AsyncLinter, AsyncReport, _analyze_async
from reassure.core.repo_walker import FileRecord, RepoIndex
from reassure.core.symbol_map import Symbol

# ── helpers ───────────────────────────────────────────────────────────────────


def _sym(
    name: str,
    kind: str = "function",
    lang: str = "dart",
    line_start: int = 1,
    line_end: int = 10,
    is_async: bool = False,
    is_public: bool = True,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=Path(f"/repo/lib/{name}.dart"),
        line_start=line_start,
        line_end=line_end,
        lang=lang,
        is_public=is_public,
        is_async=is_async,
    )


def _record(path: str, symbols: list[Symbol], source: str, lang: str = "dart") -> FileRecord:
    return FileRecord(
        path=Path(path),
        lang=lang,
        symbols=symbols,
        loc=source.count("\n") + 1,
        is_test=False,
        source=source,
    )


def _index(*records: FileRecord) -> RepoIndex:
    return RepoIndex(root=Path("/repo"), files=list(records))


# ── async_never_awaits ────────────────────────────────────────────────────────


class TestAsyncNeverAwaits:
    def test_async_with_no_await_flagged(self):
        source = "Future<void> doThing() async {\n  print('hello');\n}\n"
        sym = _sym("doThing", is_async=True, line_end=3)
        rec = _record("/repo/lib/doThing.dart", [sym], source)
        report = _analyze_async(_index(rec))
        checks = [i.check for i in report.issues]
        assert "async_never_awaits" in checks

    def test_async_with_await_not_flagged(self):
        source = "Future<void> fetchData() async {\n  final x = await http.get(url);\n}\n"
        sym = _sym("fetchData", is_async=True, line_end=3)
        rec = _record("/repo/lib/fetchData.dart", [sym], source)
        report = _analyze_async(_index(rec))
        checks = [i.check for i in report.issues]
        assert "async_never_awaits" not in checks

    def test_sync_function_not_counted(self):
        source = "void doSync() {\n  x = 1;\n}\n"
        sym = _sym("doSync", is_async=False, line_end=3)
        rec = _record("/repo/lib/doSync.dart", [sym], source)
        report = _analyze_async(_index(rec))
        assert report.total_async_functions == 0
        assert report.issues == []

    def test_python_async_never_awaits(self):
        source = "async def handler():\n    return 42\n"
        sym = Symbol(
            name="handler",
            kind="function",
            file=Path("/repo/handler.py"),
            line_start=1,
            line_end=2,
            lang="python",
            is_async=True,
            is_public=True,
        )
        rec = FileRecord(
            path=Path("/repo/handler.py"),
            lang="python",
            symbols=[sym],
            loc=2,
            is_test=False,
            source=source,
        )
        report = _analyze_async(_index(rec))
        checks = [i.check for i in report.issues]
        assert "async_never_awaits" in checks


# ── missing_async ─────────────────────────────────────────────────────────────


class TestMissingAsync:
    def test_await_without_async_dart_flagged(self):
        source = "Future<void> broken() {\n  final x = await something();\n}\n"
        sym = _sym("broken", is_async=False, line_end=3)
        rec = _record("/repo/lib/broken.dart", [sym], source)
        report = _analyze_async(_index(rec))
        checks = [i.check for i in report.issues]
        assert "missing_async" in checks

    def test_no_await_sync_not_flagged(self):
        source = "void clean() {\n  x = 1;\n}\n"
        sym = _sym("clean", is_async=False, line_end=3)
        rec = _record("/repo/lib/clean.dart", [sym], source)
        report = _analyze_async(_index(rec))
        assert report.issues == []


# ── unawaited_future ──────────────────────────────────────────────────────────


class TestUnawaitedFuture:
    def test_bare_future_call_flagged(self):
        source = (
            "Future<void> save() async {\n"
            "  _data = value;\n"
            "  http.post(url, body: data);\n"  # bare future call
            "}\n"
        )
        sym = _sym("save", is_async=True, line_end=4)
        rec = _record("/repo/lib/save.dart", [sym], source)
        report = _analyze_async(_index(rec))
        checks = [i.check for i in report.issues]
        assert "unawaited_future" in checks

    def test_awaited_call_not_flagged(self):
        source = (
            "Future<void> save() async {\n"
            "  await http.post(url, body: data);\n"
            "}\n"
        )
        sym = _sym("save", is_async=True, line_end=3)
        rec = _record("/repo/lib/save.dart", [sym], source)
        report = _analyze_async(_index(rec))
        unawaited = [i for i in report.issues if i.check == "unawaited_future"]
        assert unawaited == []


# ── AsyncLinter plugin ────────────────────────────────────────────────────────


class TestAsyncLinter:
    def test_analyzer_name(self):
        assert AsyncLinter().name == "async"

    def test_clean_index_no_issues(self):
        source = "Future<void> good() async {\n  await Future.delayed(Duration.zero);\n}\n"
        sym = _sym("good", is_async=True, line_end=3)
        rec = _record("/repo/lib/good.dart", [sym], source)
        result = AsyncLinter().analyze(_index(rec))
        assert result.issues == []

    def test_issues_have_required_keys(self):
        source = "Future<void> bad() async {\n  doNothing();\n}\n"
        sym = _sym("bad", is_async=True, line_end=3)
        rec = _record("/repo/lib/bad.dart", [sym], source)
        result = AsyncLinter().analyze(_index(rec))
        assert len(result.issues) > 0
        issue = result.issues[0]
        assert "symbol" in issue
        assert "file" in issue
        assert "line" in issue
        assert "check" in issue
        assert "detail" in issue

    def test_summary_format(self):
        result = AsyncLinter().analyze(RepoIndex(root=Path("/repo"), files=[]))
        assert "async" in result.summary.lower() or "function" in result.summary.lower()

    def test_result_data_is_async_report(self):
        result = AsyncLinter().analyze(RepoIndex(root=Path("/repo"), files=[]))
        assert isinstance(result.data, AsyncReport)
