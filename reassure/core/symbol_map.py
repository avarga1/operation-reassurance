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

from tree_sitter import Node, Tree


@dataclass
class Symbol:
    name: str
    kind: str  # "function" | "method" | "class" | "impl"
    file: Path
    line_start: int
    line_end: int
    lang: str
    decorators: list[str] = field(default_factory=list)
    parent_class: str | None = None
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
    symbols: list[Symbol] = []
    _walk_python(root, source, file, symbols, parent_class=None)
    return symbols


def _walk_python(
    node: Node,
    source: str,
    file: Path,
    symbols: list[Symbol],
    parent_class: str | None,
) -> None:
    """
    Recursively walk the Python CST, extracting symbols at each level.
    Tracks class context so methods know their parent.
    """
    for child in node.children:
        if child.type == "class_definition":
            name = _child_text(child, "identifier", source)
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        kind="class",
                        file=file,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        lang="python",
                        is_public=not name.startswith("_"),
                        parent_class=parent_class,
                    )
                )
                # Recurse into class body with this class as parent
                body = _first_child_of_type(child, "block")
                if body:
                    _walk_python(body, source, file, symbols, parent_class=name)

        elif child.type in ("function_definition", "async_function_definition"):
            _extract_python_function(child, source, file, symbols, parent_class, decorators=[])

        elif child.type == "decorated_definition":
            decorators = _extract_decorators(child, source)
            inner = (
                _first_child_of_type(child, "function_definition")
                or _first_child_of_type(child, "async_function_definition")
                or _first_child_of_type(child, "class_definition")
            )
            if inner and inner.type == "class_definition":
                name = _child_text(inner, "identifier", source)
                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            kind="class",
                            file=file,
                            line_start=child.start_point[0] + 1,
                            line_end=child.end_point[0] + 1,
                            lang="python",
                            decorators=decorators,
                            is_public=not name.startswith("_"),
                            parent_class=parent_class,
                        )
                    )
                    body = _first_child_of_type(inner, "block")
                    if body:
                        _walk_python(body, source, file, symbols, parent_class=name)
            elif inner:
                _extract_python_function(inner, source, file, symbols, parent_class, decorators)

        else:
            # Recurse into other block-level constructs (if/with/try at module level)
            _walk_python(child, source, file, symbols, parent_class)


def _extract_python_function(
    node: Node,
    source: str,
    file: Path,
    symbols: list[Symbol],
    parent_class: str | None,
    decorators: list[str],
) -> None:
    name = _child_text(node, "identifier", source)
    if not name:
        return

    is_async = node.type == "async_function_definition"
    kind = "method" if parent_class else "function"

    symbols.append(
        Symbol(
            name=name,
            kind=kind,
            file=file,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            lang="python",
            decorators=decorators,
            parent_class=parent_class,
            is_async=is_async,
            is_public=not name.startswith("_"),
        )
    )


def _extract_decorators(decorated_node: Node, source: str) -> list[str]:
    """Collect all decorator names from a decorated_definition node."""
    decorators = []
    for child in decorated_node.children:
        if child.type == "decorator":
            # decorator body is everything after the '@'
            text = _node_text(child, source).lstrip("@").strip().split("(")[0]
            decorators.append(text)
    return decorators


def _first_child_of_type(node: Node, type_name: str) -> Node | None:
    """Return the first direct child with the given node type."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _child_text(node: Node, child_type: str, source: str) -> str | None:
    """Return the text of the first direct child with the given type."""
    child = _first_child_of_type(node, child_type)
    return _node_text(child, source) if child else None


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
    return source[node.start_byte : node.end_byte]
