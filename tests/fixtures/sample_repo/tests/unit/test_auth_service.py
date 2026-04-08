"""Unit tests for AuthService — covers login and logout only."""

from src.auth.service import AuthService


class TestAuthService:
    def test_login_valid(self):
        svc = AuthService()
        assert svc.login("admin", "secret") is True

    def test_login_invalid(self):
        svc = AuthService()
        assert svc.login("admin", "wrong") is False

    def test_logout(self):
        svc = AuthService()
        svc.logout(1)  # should not raise
