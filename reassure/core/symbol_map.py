"""
Symbol extraction from parsed CST trees.

Extracts all named symbols (functions, methods, classes) from a source file
along with their location and metadata. Language-specific extractors handle
the differing node types across grammars.

Output is a flat list of Symbol objects — the universal currency passed to
all downstream analyzers.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tree_sitter import Node, Tree


@dataclass
class Symbol:
    name: str
    kind: str                        # "function" | "method" | "class" | "impl"
    file: Path
    line_start: int
    line_end: int
    lang: str
    decorators: list[str] = field(default_factory=list)
    parent_class: Optional[str] = None
    is_async: bool = False
    is_public: bool = True


def extract_symbols(tree: Tree, source: str, file: Path, lang: str) -> list[Symbol]:
    """
    Walk the CST and extract all named symbols from a source file.
    Dispatches to the appropriate language extractor.
    """
    extractors = {
        "python": _extract_python,
        "rust": _extract_rust,
        "typescript": _extract_typescript,
        "javascript": _extract_javascript,
    }
    extractor = extractors.get(lang)
    if extractor is None:
        return []
    return extractor(tree.root_node, source, file)


def _extract_python(root: Node, source: str, file: Path) -> list[Symbol]:
    """
    Extract Python functions, async functions, and classes.
    Captures decorators and class membership.
    """
    # TODO: implement
    # Walk: function_definition, async_function_definition, class_definition
    # Capture decorator_list nodes above each function
    # Track class nesting for parent_class
    raise NotImplementedError


def _extract_rust(root: Node, source: str, file: Path) -> list[Symbol]:
    """
    Extract Rust functions, impl blocks, and struct definitions.
    Captures pub visibility and async markers.
    """
    # TODO: implement
    # Walk: function_item, impl_item, struct_item
    # Check visibility_modifier for pub
    # Track impl block for parent_class equivalent
    raise NotImplementedError


def _extract_typescript(root: Node, source: str, file: Path) -> list[Symbol]:
    """
    Extract TypeScript/TSX functions, classes, and methods.
    Handles arrow functions assigned to const declarations.
    """
    # TODO: implement
    # Walk: function_declaration, method_definition, class_declaration
    # Also: lexical_declaration -> arrow_function (const foo = () => ...)
    raise NotImplementedError


def _extract_javascript(root: Node, source: str, file: Path) -> list[Symbol]:
    """JavaScript extraction — delegates to TypeScript extractor (superset grammar)."""
    return _extract_typescript(root, source, file)


def _node_text(node: Node, source: str) -> str:
    """Extract the text content of a CST node from the source string."""
    return source[node.start_byte:node.end_byte]
