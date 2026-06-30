import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GameStatus(str, enum.Enum):
    active = "active"
    won = "won"
    lost = "lost"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[GameStatus] = mapped_column(
        SAEnum(GameStatus, name="game_status"), default=GameStatus.active, nullable=False
    )
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    enemy_hp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="games")  # noqa: F821
    inventory_items: Mapped[list["InventoryItem"]] = relationship(  # noqa: F821
        back_populates="game", cascade="all, delete-orphan"
    )
    turns: Mapped[list["Turn"]] = relationship(  # noqa: F821
        back_populates="game", cascade="all, delete-orphan", order_by="Turn.id"
    )
