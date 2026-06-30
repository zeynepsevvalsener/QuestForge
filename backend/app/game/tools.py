"""AI-facing tools and their authoritative handlers.

Every state change in QuestForge flows through one of these handlers. The
handler validates the request against the database state and the static world;
illegal requests are rejected and nothing is mutated. The AI never mutates
state directly -- it only proposes tool calls, and narrates whatever result
the handler returns.
"""

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.game import state, world
from app.models import Game, GameStatus

MAX_ENV_DAMAGE = 40

# OpenAI function-calling tool definitions.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "move_player",
            "description": "Move the player one step in a compass direction (north/south/east/west).",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["north", "south", "east", "west"],
                        "description": "Direction to move.",
                    }
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attack",
            "description": (
                "Attack the enemy in the player's current room. The server computes "
                "damage from the player's equipped weapon and applies the enemy's "
                "counterattack."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Name of the enemy to attack."}
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pick_up_item",
            "description": "Pick up an item lying in the player's current room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "Item id to pick up."}
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drop_item",
            "description": "Drop / remove an item the player is currently carrying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "Item id to drop."}
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "heal_player",
            "description": (
                "Consume one health potion from the inventory to restore HP. The server "
                "decides the heal amount; the player cannot choose it."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_damage",
            "description": (
                "Apply environmental damage to the player (e.g. a trap or fall the GM "
                "narrates). Only the player can be targeted this way."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Must be 'player'."},
                    "amount": {
                        "type": "integer",
                        "description": f"Damage amount, 1 to {MAX_ENV_DAMAGE}.",
                    },
                },
                "required": ["target", "amount"],
            },
        },
    },
]


def _rejected(reason: str) -> dict:
    return {"accepted": False, "reason": reason}


def _accepted(message: str, **extra) -> dict:
    return {"accepted": True, "result": message, **extra}


def _check_active(game: Game) -> dict | None:
    if game.status != GameStatus.active:
        return _rejected(f"The game is over (status: {game.status.value}). No further actions allowed.")
    return None


def _check_win_lose(game: Game) -> None:
    if game.hp <= 0:
        game.hp = 0
        game.status = GameStatus.lost
    elif world.WORLD[game.location].is_win:
        game.status = GameStatus.won


def handle_move_player(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    direction = str(args.get("direction", "")).lower().strip()
    room = world.WORLD[game.location]

    available = dict(room.exits)
    if room.locked_exits and not state.enemy_alive(game):
        available.update(room.locked_exits)

    if direction not in available:
        if direction in room.locked_exits:
            return _rejected(
                f"The path {direction} is blocked while the {room.enemy or 'guardian'} "
                "still lives. Defeat it first."
            )
        return _rejected(
            f"There is no exit to the {direction or '(none given)'} from {room.name}. "
            f"Valid exits: {', '.join(available) or 'none'}."
        )

    game.location = available[direction]
    new_room = world.WORLD[game.location]
    _check_win_lose(game)
    return _accepted(
        f"Moved {direction} into {new_room.name}.",
        location=game.location,
        won=game.status == GameStatus.won,
    )


def handle_attack(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    room = world.WORLD[game.location]
    if room.enemy is None:
        return _rejected("There is no enemy here to attack.")
    if not state.enemy_alive(game):
        return _rejected(f"The {room.enemy} is already dead.")

    target = str(args.get("target", "")).lower().strip()
    if target and room.enemy not in target and target not in room.enemy:
        return _rejected(f"There is no '{target}' here. The enemy here is the {room.enemy}.")

    has_sword = state.has_item(game, world.ITEM_IRON_SWORD)
    damage = world.SWORD_DAMAGE if has_sword else world.FISTS_DAMAGE
    game.enemy_hp = max(0, game.enemy_hp - damage)
    weapon = "iron sword" if has_sword else "bare fists"

    if game.enemy_hp <= 0:
        return _accepted(
            f"You strike the {room.enemy} with your {weapon} for {damage} damage. "
            f"The {room.enemy} collapses, defeated! The path north from the hall is now open.",
            enemy_hp=0,
            enemy_defeated=True,
        )

    counter = world.ENEMY_ATTACK
    game.hp = max(0, game.hp - counter)
    _check_win_lose(game)
    return _accepted(
        f"You hit the {room.enemy} with your {weapon} for {damage} damage "
        f"(enemy HP now {game.enemy_hp}). The {room.enemy} retaliates for {counter} damage "
        f"(your HP now {game.hp}).",
        enemy_hp=game.enemy_hp,
        player_hp=game.hp,
        player_dead=game.hp <= 0,
    )


def handle_pick_up_item(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    item = str(args.get("item", "")).lower().strip()
    room = world.WORLD[game.location]
    key = f"{room.id}:{item}"

    if item not in room.items:
        return _rejected(f"There is no '{item}' to pick up in {room.name}.")
    if key in (game.collected_items or []):
        return _rejected(f"The {item} here has already been taken.")

    state.add_inventory(db, game, item, 1)
    game.collected_items = list(game.collected_items or []) + [key]
    flag_modified(game, "collected_items")
    return _accepted(f"Picked up {item}.", item=item)


def handle_drop_item(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    item = str(args.get("item", "")).lower().strip()
    if not state.has_item(game, item):
        return _rejected(f"You are not carrying a '{item}'.")

    state.remove_inventory(db, game, item, 1)
    return _accepted(f"Dropped {item}.", item=item)


def handle_heal_player(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    if not state.has_item(game, world.ITEM_HEALTH_POTION):
        return _rejected("You have no health potion to drink.")
    if game.hp >= world.MAX_HP:
        return _rejected("You are already at full health.")

    state.remove_inventory(db, game, world.ITEM_HEALTH_POTION, 1)
    healed_from = game.hp
    game.hp = min(world.MAX_HP, game.hp + world.POTION_HEAL_AMOUNT)
    return _accepted(
        f"Drank a health potion, restoring {game.hp - healed_from} HP (now {game.hp}).",
        player_hp=game.hp,
    )


def handle_apply_damage(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    target = str(args.get("target", "")).lower().strip()
    if target != "player":
        return _rejected("apply_damage can only target 'player'.")

    amount = args.get("amount")
    if not isinstance(amount, int) or amount <= 0:
        return _rejected("Damage amount must be a positive integer.")
    if amount > MAX_ENV_DAMAGE:
        return _rejected(f"Damage amount exceeds the maximum allowed ({MAX_ENV_DAMAGE}).")

    game.hp = max(0, game.hp - amount)
    _check_win_lose(game)
    return _accepted(
        f"The player takes {amount} damage (HP now {game.hp}).",
        player_hp=game.hp,
        player_dead=game.hp <= 0,
    )


HANDLERS = {
    "move_player": handle_move_player,
    "attack": handle_attack,
    "pick_up_item": handle_pick_up_item,
    "drop_item": handle_drop_item,
    "heal_player": handle_heal_player,
    "apply_damage": handle_apply_damage,
}


def execute_tool(db: Session, game: Game, name: str, args: dict) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        return _rejected(f"Unknown tool '{name}'.")
    return handler(db, game, args)
