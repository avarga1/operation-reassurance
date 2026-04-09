# REASSURE: expect clean (no god class, no god file, no soc violation)
#
# One class. One responsibility. Correct.
# This file must NOT trigger any SOLID flags.
# If it does, the analyzer has a false positive.

import hashlib


class PasswordHasher:
    """Hashes and verifies passwords. That's it. That's the whole class."""

    algorithm = "sha256"

    def hash(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def verify(self, password: str, hashed: str) -> bool:
        return self.hash(password) == hashed
