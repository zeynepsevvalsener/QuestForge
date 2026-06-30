"""Create a known test account so reviewers can log in immediately.

Usage (inside the backend container or a configured local env):
    python -m scripts.seed_test_user

Idempotent: does nothing if the account already exists.
"""

import sys

from app.auth.security import hash_password
from app.database import SessionLocal
from app.models import User

TEST_EMAIL = "test@questforge.dev"
TEST_PASSWORD = "Test1234!"


def main() -> int:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == TEST_EMAIL).first()
        if existing is not None:
            print(f"Test user already exists: {TEST_EMAIL}")
            return 0
        db.add(User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD)))
        db.commit()
        print(f"Created test user: {TEST_EMAIL} / {TEST_PASSWORD}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
