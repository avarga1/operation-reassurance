"""
Repository walker.

Walks the repo file tree, routes each file to the parser, and builds
the full symbol map and file index used by all analyzers.

Respects .reassure.toml ignore rules and .gitignore if present.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from reassure.core.parser import detect_language, parse_file
from reassure.core.symbol_map import Symbol, extract_symbols


@dataclass
class FileRecord:
    path: Path
    lang: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    loc: int = 0
    is_test: bool = False


@dataclass
class RepoIndex:
    root: Path
    files: list[FileRecord] = field(default_factory=list)

    @property
    def source_files(self) -> list[FileRecord]:
        return [f for f in self.files if not f.is_test]

    @property
    def test_files(self) -> list[FileRecord]:
        return [f for f in self.files if f.is_test]

    @property
    def all_symbols(self) -> list[Symbol]:
        return [s for f in self.source_files for s in f.symbols]


DEFAULT_IGNORE = {
    "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", "dist", "build", "target", ".git",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
}

TEST_PATH_HINTS = {"test", "tests", "spec", "specs", "__tests__"}


def is_test_file(path: Path) -> bool:
    """Heuristic: is this file a test file?"""
    parts = set(path.parts)
    if parts & TEST_PATH_HINTS:
        return True
    name = path.stem.lower()
    return name.startswith("test_") or name.endswith("_test") or name.endswith(".spec")


def walk_repo(
    root: Path,
    ignore: Optional[set[str]] = None,
) -> RepoIndex:
    """
    Walk a repository root and build a full RepoIndex.

    Parses every supported source file into CST, extracts symbols,
    and classifies files as source or test.
    """
    ignore = ignore or DEFAULT_IGNORE
    index = RepoIndex(root=root)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignore for part in path.parts):
            continue

        lang = detect_language(path)
        if lang is None:
            continue

        result = parse_file(path)
        if result is None:
            continue

        tree, source = result
        symbols = extract_symbols(tree, source, path, lang)
        loc = source.count("\n") + 1

        record = FileRecord(
            path=path,
            lang=lang,
            symbols=symbols,
            loc=loc,
            is_test=is_test_file(path),
        )
        index.files.append(record)

    return index
