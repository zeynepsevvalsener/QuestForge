"""Read helpers and serialization for authoritative game state."""

from sqlalchemy.orm import Session

from app.game import world
from app.models import Game, GameStatus, InventoryItem


def inventory_map(game: Game) -> dict[str, int]:
    return {i.item: i.quantity for i in game.inventory_items}


def has_item(game: Game, item: str, quantity: int = 1) -> bool:
    return inventory_map(game).get(item, 0) >= quantity


def add_inventory(db: Session, game: Game, item: str, quantity: int = 1) -> None:
    existing = next((i for i in game.inventory_items if i.item == item), None)
    if existing is not None:
        existing.quantity += quantity
    else:
        db.add(InventoryItem(game_id=game.id, item=item, quantity=quantity))


def remove_inventory(db: Session, game: Game, item: str, quantity: int = 1) -> bool:
    existing = next((i for i in game.inventory_items if i.item == item), None)
    if existing is None or existing.quantity < quantity:
        return False
    existing.quantity -= quantity
    if existing.quantity <= 0:
        db.delete(existing)
    return True


def enemy_alive(game: Game) -> bool:
    return game.enemy_hp > 0


def current_room(game: Game) -> world.Room:
    return world.WORLD[game.location]


def state_summary(game: Game) -> dict:
    """Compact, authoritative snapshot handed to the AI each round.

    The AI must narrate only from this; it never sets these values itself.
    """
    room = current_room(game)
    enemy_present = room.enemy is not None and enemy_alive(game)
    available_exits = dict(room.exits)
    if room.locked_exits and not enemy_alive(game):
        available_exits.update(room.locked_exits)

    notes: list[str] = []
    if room.locked_exits:
        for direction, dest in room.locked_exits.items():
            if enemy_alive(game):
                notes.append(
                    f"The {direction} exit is currently sealed/blocked and cannot be used "
                    "until the goblin is defeated."
                )
            else:
                notes.append(
                    f"The previously sealed {direction} door is now OPEN; moving {direction} "
                    f"leads to {dest}. If the player goes {direction}, call move_player('{direction}')."
                )

    return {
        "status": game.status.value,
        "hp": game.hp,
        "max_hp": world.MAX_HP,
        "alive": game.hp > 0,
        "location": game.location,
        "room_name": room.name,
        "room_description": room.description,
        "available_exits": available_exits,
        "locked_exits": list(room.locked_exits) if (room.locked_exits and enemy_alive(game)) else [],
        "items_here": [
            item for item in room.items if f"{room.id}:{item}" not in (game.collected_items or [])
        ],
        "inventory": inventory_map(game),
        "enemy_here": room.enemy if enemy_present else None,
        "enemy_hp": game.enemy_hp if enemy_present else None,
        "notes": notes,
    }


def serialize_game(game: Game) -> dict:
    room = current_room(game)
    available_exits = dict(room.exits)
    if room.locked_exits and not enemy_alive(game):
        available_exits.update(room.locked_exits)
    return {
        "id": game.id,
        "status": game.status,
        "hp": game.hp,
        "max_hp": world.MAX_HP,
        "location": game.location,
        "room": {
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "exits": available_exits,
            "items": [
                item
                for item in room.items
                if f"{room.id}:{item}" not in (game.collected_items or [])
            ],
            "enemy": room.enemy if (room.enemy and enemy_alive(game)) else None,
        },
        "enemy_hp": game.enemy_hp,
        "inventory": [{"item": i.item, "quantity": i.quantity} for i in game.inventory_items],
        "alive": game.hp > 0,
        "turns": [
            {
                "id": t.id,
                "role": t.role.value,
                "content": t.content,
                "tool_calls": t.tool_calls,
                "created_at": t.created_at,
            }
            for t in game.turns
        ],
    }


def create_new_game(db: Session, user_id: int) -> Game:
    game = Game(
        user_id=user_id,
        status=GameStatus.active,
        hp=world.STARTING_HP,
        location=world.STARTING_ROOM,
        enemy_hp=world.ENEMY_MAX_HP,
        collected_items=[],
    )
    db.add(game)
    db.flush()
    return game
