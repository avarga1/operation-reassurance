"""
Language detection and tree-sitter parser initialization.

Responsible for:
- Detecting language from file extension
- Loading the appropriate tree-sitter grammar
- Returning parsed CST nodes for downstream analyzers
"""

from pathlib import Path

import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_rust
import tree_sitter_typescript
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

    # TODO: add dart, glsl when needed
    grammar_map = {
        "python": tree_sitter_python.language(),
        "rust": tree_sitter_rust.language(),
        "javascript": tree_sitter_javascript.language(),
        "typescript": tree_sitter_typescript.language_typescript(),
    }

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
