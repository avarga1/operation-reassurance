"""Auth service — fixture for reassure integration tests."""

import logging

logger = logging.getLogger(__name__)


class AuthService:
    def login(self, username: str, password: str) -> bool:
        """Has unit + integration tests."""
        logger.info("login attempt for %s", username)
        return username == "admin" and password == "secret"

    def logout(self, user_id: int) -> None:
        """Has unit test only."""
        logger.info("logout for user %d", user_id)

    def reset_password(self, email: str) -> bool:
        """NO TESTS — should be flagged by coverage analyzer."""
        return True

    def _validate_token(self, token: str) -> bool:
        """Private — should be excluded from public coverage report."""
        return len(token) > 10


async def verify_session(session_id: str) -> bool:
    """Async standalone — has no tests, no observability."""
    return True
