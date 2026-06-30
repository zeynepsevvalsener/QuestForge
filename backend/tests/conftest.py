import uuid

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.game import state
from app.models import Game, User


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def user(db: Session) -> User:
    u = User(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def game(db: Session, user: User) -> Game:
    g = state.create_new_game(db, user.id)
    db.commit()
    db.refresh(g)
    return g
