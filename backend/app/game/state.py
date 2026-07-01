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
        game.inventory_items.append(InventoryItem(item=item, quantity=quantity))


def remove_inventory(db: Session, game: Game, item: str, quantity: int = 1) -> bool:
    existing = next((i for i in game.inventory_items if i.item == item), None)
    if existing is None or existing.quantity < quantity:
        return False
    existing.quantity -= quantity
    if existing.quantity <= 0:
        game.inventory_items.remove(existing)
    return True


def enemy_alive(game: Game) -> bool:
    return game.enemy_hp > 0


def current_room(game: Game) -> world.Room:
    """Resolve the player's room, lazily migrating any legacy location id."""
    normalized = world.normalize_location(game.location)
    if normalized != game.location:
        game.location = normalized
    return world.WORLD[normalized]


def items_on_ground(game: Game, room: world.Room) -> list[str]:
    return [
        item for item in room.items if f"{room.id}:{item}" not in (game.collected_items or [])
    ]


def available_exits(game: Game, room: world.Room) -> dict[str, str]:
    exits = dict(room.exits)
    if room.locked_exits and not enemy_alive(game):
        exits.update(room.locked_exits)
    return exits


def quest_progress(game: Game) -> list[dict]:
    """Authoritative quest checklist, derived purely from persisted state."""
    collected = game.collected_items or []
    goblin_defeated = not enemy_alive(game)
    won = game.status == GameStatus.won
    entered_hall = (
        game.location != world.STARTING_ROOM
        or bool(collected)
        or goblin_defeated
        or won
    )
    return [
        {"label": "Enter the Great Hall", "done": entered_hall},
        {"label": "Collect the Health Potion", "done": "hall:health_potion" in collected},
        {"label": "Find the Iron Sword", "done": "armory:iron_sword" in collected},
        {"label": "Defeat the Goblin", "done": goblin_defeated},
        {"label": "Reach the Treasure Vault", "done": game.location == "treasure_vault" or won},
        {"label": "Claim the Ancient Relic", "done": "treasure_vault:ancient_relic" in collected},
    ]


def objective_for(game: Game) -> str:
    """A short, always-accurate goal string derived from authoritative state."""
    if game.status == GameStatus.won:
        return "Quest complete. You have cleared the dungeon."
    if game.status == GameStatus.lost:
        return "You have fallen. Start a new game to try again."

    room = current_room(game)
    has_relic = "treasure_vault:ancient_relic" in (game.collected_items or [])
    if room.id == "treasure_vault":
        if has_relic:
            return "Quest complete. You have claimed the relic and cleared the dungeon."
        return "Claim the Ancient Relic to complete your quest."
    if room.id == "goblin_lair" and enemy_alive(game):
        return "Defeat the goblin."
    if room.id == "armory" and world.ITEM_IRON_SWORD in items_on_ground(game, room):
        return "Pick up the iron sword."
    if not enemy_alive(game):
        return "Return to the Great Hall and go north to reach the Treasure Vault."
    return "Find a weapon, defeat the goblin, and reach the Treasure Vault."


def state_summary(game: Game) -> dict:
    """Compact, authoritative snapshot handed to the AI each round.

    The AI must narrate only from this; it never sets these values itself.
    """
    room = current_room(game)
    enemy_present = room.enemy is not None and enemy_alive(game)
    exits = available_exits(game, room)

    notes: list[str] = []
    if room.locked_exits:
        for direction, dest in room.locked_exits.items():
            if enemy_alive(game):
                notes.append(
                    f"The {direction} exit is currently sealed/blocked and cannot be used "
                    "until the goblin is defeated."
                )
            else:
                dest_name = world.WORLD[dest].name
                notes.append(
                    f"The previously sealed {direction} door is now OPEN; moving {direction} "
                    f"leads to {dest_name}. If the player goes {direction}, call move_player('{direction}')."
                )

    return {
        "status": game.status.value,
        "hp": game.hp,
        "max_hp": world.MAX_HP,
        "alive": game.hp > 0,
        "location": game.location,
        "room_name": room.name,
        "room_description": room.description,
        "objective": objective_for(game),
        "exits": exits,
        "locked_exits": list(room.locked_exits) if (room.locked_exits and enemy_alive(game)) else [],
        "items_here": items_on_ground(game, room),
        "inventory": inventory_map(game),
        "enemy_here": room.enemy if enemy_present else None,
        "enemies_here": [room.enemy] if enemy_present else [],
        "enemy_hp": game.enemy_hp if enemy_present else None,
        "enemy": {"name": room.enemy, "hp": game.enemy_hp} if enemy_present else None,
        "notes": notes,
    }


def serialize_game(game: Game) -> dict:
    room = current_room(game)
    exits = available_exits(game, room)
    return {
        "id": game.id,
        "status": game.status,
        "hp": game.hp,
        "max_hp": world.MAX_HP,
        "location": game.location,
        "objective": objective_for(game),
        "progress": quest_progress(game),
        "room": {
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "exits": exits,
            "items": items_on_ground(game, room),
            "enemy": room.enemy if (room.enemy and enemy_alive(game)) else None,
        },
        "enemy_hp": game.enemy_hp,
        "enemy_max_hp": world.ENEMY_MAX_HP,
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
