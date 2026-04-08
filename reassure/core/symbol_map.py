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
        "dart": _extract_dart,
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
                # Now walk the class body so methods get the class name as
                # their `parent_class`.
                body = _first_child_of_type(child, "block")
                if body:
                    _walk_python(body, source, file, symbols, parent_class=name)

        elif child.type in ("function_definition", "async_function_definition"):
            # Found a top-level function (or async function). Extract it and
            # record whether it's a method or a free function based on the
            # `parent_class` context.
            _extract_python_function(child, source, file, symbols, parent_class, decorators=[])

        elif child.type == "decorated_definition":
            # Collect decorator names, then inspect the inner node which may
            # be a class or a function. Decorators should be attached to the
            # resulting Symbol so downstream code knows about them.
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
            # For any other node types, keep walking to find nested
            # definitions (for example functions inside if/with/try blocks).
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

    # tree-sitter python may represent async functions as a `function_definition`
    # node with an `async` child token, so detect either form.
    # Some Python async definitions appear as a function node with an
    # `async` child token. Check both the node type and the presence of the
    # `async` token so we correctly mark async functions.
    is_async = node.type == "async_function_definition" or any(
        c.type == "async" for c in node.children
    )
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
                    # The decorator node includes the '@' symbol. Strip it and any
                    # arguments so we end up with the decorator's name.
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

    Not implemented yet — placeholder so Python code can import this module.
    """
    raise NotImplementedError


def _extract_typescript(root: Node, source: str, file: Path) -> list[Symbol]:
    """
    Extract TypeScript/TSX functions, classes, and methods.

    Not implemented yet — reserved for future TypeScript support.
    """
    raise NotImplementedError


def _extract_javascript(root: Node, source: str, file: Path) -> list[Symbol]:
    """JavaScript extraction — reuses the TypeScript extractor."""
    return _extract_typescript(root, source, file)


def _extract_dart(root: Node, source: str, file: Path) -> list[Symbol]:
    """
    Extract Dart classes, top-level functions, and methods.

    CST layout:
    - class_definition: identifier + class_body
    - class_body children: method_signature (+ function_body sibling)
    - method_signature children: function_signature with identifier
    - top-level function_signature: direct child of program node
    """
    symbols: list[Symbol] = []
    _walk_dart(root, source, file, symbols, parent_class=None)
    return symbols


def _walk_dart(
    node: Node,
    source: str,
    file: Path,
    symbols: list[Symbol],
    parent_class: str | None,
) -> None:
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
                        lang="dart",
                        is_public=not name.startswith("_"),
                        parent_class=parent_class,
                    )
                )
                body = _first_child_of_type(child, "class_body")
                if body:
                    _walk_dart(body, source, file, symbols, parent_class=name)

        elif child.type == "method_signature":
            # method_signature > function_signature > identifier
            func_sig = _first_child_of_type(child, "function_signature")
            if func_sig:
                _extract_dart_function(child, func_sig, source, file, symbols, parent_class)

        elif child.type == "function_signature" and parent_class is None:
            # Top-level function: function_signature at program level
            # Find the matching function_body (next sibling handled by parent walker)
            # The function_signature IS the declaration node for line range
            _extract_dart_function(child, child, source, file, symbols, parent_class=None)

        else:
            _walk_dart(child, source, file, symbols, parent_class)


def _extract_dart_function(
    outer: Node,
    func_sig: Node,
    source: str,
    file: Path,
    symbols: list[Symbol],
    parent_class: str | None,
) -> None:
    """Extract a single Dart function or method from a function_signature node."""
    name = _child_text(func_sig, "identifier", source)
    if not name:
        return

    # async marker lives in function_body sibling — check parent's children
    is_async = any(
        sib.type == "function_body" and any(c.type == "async" for c in sib.children)
        for sib in (outer.parent.children if outer.parent else [])
    )

    kind = "method" if parent_class else "function"
    symbols.append(
        Symbol(
            name=name,
            kind=kind,
            file=file,
            line_start=outer.start_point[0] + 1,
            line_end=outer.end_point[0] + 1,
            lang="dart",
            parent_class=parent_class,
            is_async=is_async,
            is_public=not name.startswith("_"),
        )
    )


def _node_text(node: Node, source: str) -> str:
    """Extract the text content of a CST node from the source string."""
    return source.encode()[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
