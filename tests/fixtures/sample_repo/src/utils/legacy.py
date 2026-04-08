"""
Legacy utils — fixture for dead code analyzer.

These functions are never imported or called anywhere.
Should be flagged as dead code.
"""


def parse_v1_format(data: str) -> dict:
    """Dead code — never called anywhere."""
    return {}


def convert_legacy_id(old_id: str) -> int:
    """Dead code — never called anywhere."""
    return int(old_id.replace("usr_", ""))


class LegacyClient:
    """Dead code — never instantiated anywhere."""

    def connect(self):
        pass

    def fetch(self, endpoint: str):
        pass
