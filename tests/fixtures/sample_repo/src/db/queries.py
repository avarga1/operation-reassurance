"""
DB queries — fixture for observability analyzer.

This entire module has ZERO logging, tracing, or metrics.
Should be flagged as a dark module.
"""


def get_user_by_id(user_id: int) -> dict | None:
    """No observability — should be flagged."""
    return None


def insert_user(username: str, email: str) -> int:
    """No observability — should be flagged."""
    return 1


def delete_user(user_id: int) -> bool:
    """No observability — should be flagged."""
    return True


def list_users(limit: int = 100) -> list:
    """No observability — should be flagged."""
    return []
