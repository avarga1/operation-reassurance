"""
Observability coverage analyzer.

Detects functions and modules with no logging, tracing, or metrics
instrumentation — purely via static CST analysis.

A function is considered "dark" (unobservable) if its body contains no
calls matching configured observability patterns. debugPrint / print are
explicitly excluded — they are dev-only and stripped from release builds.

Default patterns cover the most common stacks per language:
  Python  : logging.*, logger.*, structlog.*, tracer.*, span.*
  Dart    : Logger.*, log.*, Sentry.*, tracer.*, FirebaseCrashlytics.*
  Rust    : tracing::*, log::*, info!, warn!, error!, debug!
  TS/JS   : logger.*, console.error (not console.log), Sentry.*, tracer.*

Configurable via .reassure.toml [observability] section.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from reassure.core.parser import parse_file
from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol

# --------------------------------------------------------------------------- #
# Default patterns — identifier prefixes that count as real observability
# --------------------------------------------------------------------------- #

_PYTHON_OBS = {
    "logging",
    "logger",
    "log",
    "structlog",
    "tracer",
    "span",
    "meter",
    "counter",
    "histogram",
    "sentry_sdk",
    "capture_exception",
    "capture_message",
}

_DART_OBS = {
    "Logger",
    "_log",
    "log",
    "Sentry",
    "captureException",
    "captureMessage",
    "tracer",
    "span",
    "FirebaseCrashlytics",
    "FirebasePerformance",
    "recordError",
    "recordFlutterFatalError",
}

_RUST_OBS = {
    "tracing",
    "log",
    "info",
    "warn",
    "error",
    "debug",
    "trace",
    "span",
    "instrument",
}

_TS_OBS = {
    "logger",
    "log",
    "Sentry",
    "captureException",
    "captureMessage",
    "tracer",
    "span",
    "meter",
    "console",  # console.error / console.warn count — NOT console.log
}

# Calls that look like observability but aren't production-safe
_EXCLUDED = {"print", "debugPrint", "println", "console.log", "fmt.Print", "fmt.Println"}

DEFAULT_PATTERNS: dict[str, set[str]] = {
    "python": _PYTHON_OBS,
    "dart": _DART_OBS,
    "rust": _RUST_OBS,
    "typescript": _TS_OBS,
    "javascript": _TS_OBS,
}


# --------------------------------------------------------------------------- #
# Report types
# --------------------------------------------------------------------------- #


@dataclass
class ObservabilityGap:
    symbol: Symbol
    reason: str  # "no logging", "no tracing", "completely dark"


@dataclass
class ObservabilityReport:
    gaps: list[ObservabilityGap]
    total_functions: int
    dark_functions: int
    dark_module_paths: list[Path] = field(default_factory=list)

    @property
    def dark_pct(self) -> float:
        if self.total_functions == 0:
            return 0.0
        return round(self.dark_functions / self.total_functions * 100, 1)


# --------------------------------------------------------------------------- #
# Analyzer entry point
# --------------------------------------------------------------------------- #


def analyze_observability(
    index: RepoIndex,
    extra_patterns: dict[str, set[str]] | None = None,
) -> ObservabilityReport:
    """
    Scan all public source functions for observability instrumentation.

    Skips private symbols (name starts with _) — they're implementation
    details that don't need direct instrumentation.
    """
    patterns = {lang: set(p) for lang, p in DEFAULT_PATTERNS.items()}
    if extra_patterns:
        for lang, p in extra_patterns.items():
            patterns.setdefault(lang, set()).update(p)

    # Parse every source file once and cache the (node, source) tuple
    file_cache: dict[Path, tuple[Node, str] | None] = {}
    for record in index.source_files:
        parsed = parse_file(record.path)
        file_cache[record.path] = (parsed[0].root_node, parsed[1]) if parsed else None

    gaps: list[ObservabilityGap] = []
    total = 0
    dark = 0

    # Track which files have at least one instrumented function
    file_has_obs: dict[Path, bool] = defaultdict(bool)

    for symbol in index.all_symbols:
        # Only check public functions and methods — not classes, not privates
        if symbol.kind not in ("function", "method"):
            continue
        if not symbol.is_public:
            continue

        total += 1
        cached = file_cache.get(symbol.file)
        if cached is None:
            gaps.append(ObservabilityGap(symbol=symbol, reason="completely dark"))
            dark += 1
            continue

        root, source = cached
        lang_patterns = patterns.get(symbol.lang, set())
        body_node = _find_function_body(root, symbol)

        if body_node is None or not _has_obs_call(body_node, source, lang_patterns):
            gaps.append(ObservabilityGap(symbol=symbol, reason="completely dark"))
            dark += 1
        else:
            file_has_obs[symbol.file] = True

    # Dark modules = files where every public function is dark
    all_public_files = {
        s.file for s in index.all_symbols if s.kind in ("function", "method") and s.is_public
    }
    dark_module_paths = sorted(f for f in all_public_files if not file_has_obs[f])

    return ObservabilityReport(
        gaps=gaps,
        total_functions=total,
        dark_functions=dark,
        dark_module_paths=dark_module_paths,
    )


# --------------------------------------------------------------------------- #
# CST helpers
# --------------------------------------------------------------------------- #


def _find_function_body(root: Node, symbol: Symbol) -> Node | None:
    """
    Find the body node for a symbol by scanning the CST for a matching
    function/method definition at the expected line.
    """
    target_line = symbol.line_start - 1  # tree-sitter is 0-indexed

    def walk(node: Node) -> Node | None:
        if node.start_point[0] == target_line:
            body = _body_of(node, symbol.lang)
            if body:
                return body
        for child in node.children:
            result = walk(child)
            if result:
                return result
        return None

    return walk(root)


def _body_of(node: Node, lang: str) -> Node | None:
    """Extract the body/block node from a function definition node."""
    if lang == "python":
        if node.type in ("function_definition", "async_function_definition"):
            return _first_child_of_type(node, "block")
    elif lang == "dart":
        # method_signature is paired with a function_body sibling
        if node.type in ("method_signature", "function_signature"):
            parent = node.parent
            if parent:
                for sib in parent.children:
                    if sib.type == "function_body":
                        return sib
        if node.type == "function_body":
            return node
    elif lang == "rust" and node.type == "function_item":
        return _first_child_of_type(node, "block")
    elif lang in ("typescript", "javascript") and node.type in (
        "function_declaration",
        "method_definition",
        "arrow_function",
    ):
        return _first_child_of_type(node, "statement_block")
    return None


def _has_obs_call(body: Node, source: str, patterns: set[str]) -> bool:
    """
    Return True if any call in the body matches an observability pattern.
    Excludes known dev-only calls (print, debugPrint, etc.).
    """
    for node in _iter_calls(body):
        name = _call_name(node, source)
        if name and name not in _EXCLUDED:
            # Match if the call name starts with any pattern prefix
            for pattern in patterns:
                if (
                    name == pattern
                    or name.startswith(pattern + ".")
                    or name.startswith(pattern + "_")
                ):
                    return True
    return False


def _iter_calls(node: Node):
    """Yield all call nodes in a subtree."""
    if node.type == "call":
        yield node
    for child in node.children:
        yield from _iter_calls(child)


def _call_name(node: Node, source: str) -> str | None:
    """Extract the callable name from a call node (handles obj.method)."""
    func = node.child_by_field_name("function")
    if func is None:
        return None
    if func.type == "identifier":
        return _node_text(func, source)
    if func.type == "attribute":
        obj = func.child_by_field_name("object")
        attr = func.child_by_field_name("attribute")
        if obj and attr:
            return f"{_node_text(obj, source)}.{_node_text(attr, source)}"
    return None


def _first_child_of_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _node_text(node: Node, source: str) -> str:
    return source.encode()[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
