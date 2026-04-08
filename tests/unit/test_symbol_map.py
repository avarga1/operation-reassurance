from pathlib import Path

from reassure.core.parser import parse_source
from reassure.core.symbol_map import extract_symbols


def _symbols_from_source(src: str):
    tree = parse_source(src, "python")
    assert tree is not None, "Parser failed to produce a tree"
    return extract_symbols(tree, src, Path("/tmp/test.py"), "python")


def test_plain_function():
    src = """
def foo():
    return 1
"""
    syms = _symbols_from_source(src)
    assert any(s.name == "foo" and s.kind == "function" for s in syms)


def test_async_function():
    src = """
async def bar():
    pass
"""
    syms = _symbols_from_source(src)
    f = next(s for s in syms if s.name == "bar")
    assert f.is_async


def test_class_and_method():
    src = """
class A:
    def m(self):
        return 2
"""
    syms = _symbols_from_source(src)
    assert any(s.name == "A" and s.kind == "class" for s in syms)
    m = next(s for s in syms if s.name == "m")
    assert m.kind == "method"
    assert m.parent_class == "A"


def test_decorated_function_and_private():
    src = """
@decorator
def public_fn():
    pass

def _private():
    pass
"""
    syms = _symbols_from_source(src)
    pub = next(s for s in syms if s.name == "public_fn")
    assert "decorator" in pub.decorators
    priv = next(s for s in syms if s.name == "_private")
    assert not priv.is_public
