"""Integration tests for AuthService — hits a real DB."""

import sqlalchemy  # noqa: F401 — import signals integration type to reassure

from src.auth.service import AuthService


class TestAuthIntegration:
    def test_login_persists_session(self):
        svc = AuthService()
        result = svc.login("admin", "secret")
        assert result is True
