"""
Language detection and tree-sitter parser initialization.

Responsible for:
- Detecting language from file extension
- Loading the appropriate tree-sitter grammar
- Returning parsed CST nodes for downstream analyzers
"""

from pathlib import Path

# Try to import language grammars if they're installed. It's okay if some
# grammars are missing — we'll only enable languages we can actually parse.
try:
    import tree_sitter_dart as _tree_sitter_dart
except Exception:
    _tree_sitter_dart = None

try:
    import tree_sitter_javascript as _tree_sitter_javascript
except Exception:
    _tree_sitter_javascript = None

try:
    import tree_sitter_python as _tree_sitter_python
except Exception:
    _tree_sitter_python = None

try:
    import tree_sitter_rust as _tree_sitter_rust
except Exception:
    _tree_sitter_rust = None

try:
    import tree_sitter_typescript as _tree_sitter_typescript
except Exception:
    _tree_sitter_typescript = None

from tree_sitter import Language, Parser, Tree

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".dart": "dart",
}

_LANGUAGE_CACHE: dict[str, Language] = {}


def get_language(lang: str) -> Language | None:
    """
    Return a cached tree-sitter Language for the given language name.
    Returns None if the language grammar is not available.
    """
    if lang in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lang]

    # Only include grammars we were able to import. This builds a simple map
    # from language name to the language object that tree-sitter expects.
    grammar_map: dict[str, object] = {}
    if _tree_sitter_python is not None:
        grammar_map["python"] = _tree_sitter_python.language()
    if _tree_sitter_rust is not None:
        grammar_map["rust"] = _tree_sitter_rust.language()
    if _tree_sitter_javascript is not None:
        grammar_map["javascript"] = _tree_sitter_javascript.language()
    if _tree_sitter_typescript is not None:
        # some TypeScript bindings expose a helper; try the common names.
        try:
            grammar_map["typescript"] = _tree_sitter_typescript.language_typescript()
        except Exception:
            grammar_map["typescript"] = _tree_sitter_typescript.language()
    if _tree_sitter_dart is not None:
        grammar_map["dart"] = _tree_sitter_dart.language()

    # If the requested language isn't available, return None so callers can
    # continue gracefully.
    if lang not in grammar_map:
        return None

    language = Language(grammar_map[lang])
    _LANGUAGE_CACHE[lang] = language
    return language


def detect_language(path: Path) -> str | None:
    """Detect language from file extension. Returns None for unknown types."""
    return EXTENSION_MAP.get(path.suffix.lower())


def parse_file(path: Path) -> tuple[Tree, str] | None:
    """
    Parse a source file into a CST tree.

    Returns (tree, source_code) or None if language is unsupported.
    """
    lang_name = detect_language(path)
    if lang_name is None:
        return None

    language = get_language(lang_name)
    if language is None:
        return None

    parser = Parser(language)
    source = path.read_bytes()
    tree = parser.parse(source)
    return tree, source.decode("utf-8", errors="replace")


def parse_source(source: str, lang: str) -> Tree | None:
    """Parse a raw source string given an explicit language name."""
    language = get_language(lang)
    if language is None:
        return None
    parser = Parser(language)
    return parser.parse(source.encode())
