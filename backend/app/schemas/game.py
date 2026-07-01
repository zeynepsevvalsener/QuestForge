from datetime import datetime

from pydantic import BaseModel

from app.models import GameStatus


class InventoryItemResponse(BaseModel):
    item: str
    quantity: int

    model_config = {"from_attributes": True}


class TurnResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_calls: list | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: str
    name: str
    description: str
    exits: dict[str, str]
    items: list[str]
    enemy: str | None = None


class QuestStep(BaseModel):
    label: str
    done: bool


class GameStateResponse(BaseModel):
    id: int
    status: GameStatus
    hp: int
    max_hp: int
    location: str
    objective: str
    progress: list[QuestStep]
    room: RoomResponse
    enemy_hp: int
    enemy_max_hp: int
    inventory: list[InventoryItemResponse]
    alive: bool
    turns: list[TurnResponse]

    model_config = {"from_attributes": True}


class ActionRequest(BaseModel):
    action: str
