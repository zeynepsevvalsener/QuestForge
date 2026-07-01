"""AI-facing tools and their authoritative handlers.

Every state change in QuestForge flows through one of these handlers. The
handler validates the request against the database state and the static world;
illegal requests are rejected and nothing is mutated. The AI never mutates
state directly -- it only proposes tool calls, and narrates whatever result
the handler returns.

Every handler returns a structured result:

    success  -> {"ok": True,  "message": str, "events": [str, ...]}
    failure  -> {"ok": False, "error": str}

``execute_tool`` then decorates the result with ``action``, ``previous_state``
and ``updated_state`` so the AI can narrate strictly from the *updated* state.
"""

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from app.game import state, world
from app.models import Game, GameStatus

MAX_ENV_DAMAGE = 40

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


def _fail(error: str) -> dict:
    return {"ok": False, "error": error}


def _ok(message: str, events: list[str] | None = None) -> dict:
    return {"ok": True, "message": message, "events": events or []}


def _check_active(game: Game) -> dict | None:
    if game.status != GameStatus.active:
        return _fail(
            f"The game is over (status: {game.status.value}). No further actions are allowed."
        )
    return None


def _check_win_lose(game: Game) -> None:
    if game.hp <= 0:
        game.hp = 0
        game.status = GameStatus.lost
    elif "treasure_vault:ancient_relic" in (game.collected_items or []):
        game.status = GameStatus.won


def handle_move_player(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    direction = str(args.get("direction", "")).lower().strip()
    room = state.current_room(game)
    available = state.available_exits(game, room)

    if direction not in available:
        if direction in room.locked_exits:
            return _fail(
                f"The path {direction} is sealed while the {room.enemy or 'guardian'} "
                "still lives. Defeat it first."
            )
        return _fail(
            f"There is no exit to the {direction or '(none given)'} from {room.name}. "
            f"Valid exits: {', '.join(available) or 'none'}."
        )

    game.location = available[direction]
    new_room = state.current_room(game)
    _check_win_lose(game)

    events = [f"Moved to {new_room.name}."]
    if game.status == GameStatus.won:
        events.append("You have entered the Treasure Vault. The quest is complete!")

    return _ok(
        f"Player moved from {room.name} to {new_room.name}.",
        events,
    )


def handle_attack(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    room = state.current_room(game)
    if room.enemy is None:
        return _fail("There is no enemy here to attack.")
    if not state.enemy_alive(game):
        return _fail(f"The {room.enemy} is already dead.")

    target = str(args.get("target", "")).lower().strip()
    if target and room.enemy not in target and target not in room.enemy:
        return _fail(f"There is no '{target}' here. The enemy here is the {room.enemy}.")

    has_sword = state.has_item(game, world.ITEM_IRON_SWORD)
    damage = world.SWORD_DAMAGE if has_sword else world.FISTS_DAMAGE
    game.enemy_hp = max(0, game.enemy_hp - damage)
    weapon = "iron sword" if has_sword else "bare fists"

    if game.enemy_hp <= 0:
        return _ok(
            f"You strike the {room.enemy} with your {weapon} for {damage} damage and it collapses, defeated.",
            [
                f"The {room.enemy} is defeated.",
                "The northern door in the Great Hall is now unlocked.",
            ],
        )

    counter = world.ENEMY_ATTACK
    game.hp = max(0, game.hp - counter)
    _check_win_lose(game)

    events = [
        f"Goblin HP is now {game.enemy_hp}.",
        f"You took {counter} damage (HP now {game.hp}).",
    ]
    if game.status == GameStatus.lost:
        events.append("You have fallen in battle.")

    return _ok(
        f"You hit the {room.enemy} with your {weapon} for {damage} damage "
        f"(enemy HP now {game.enemy_hp}); it retaliates for {counter} (your HP now {game.hp}).",
        events,
    )


def handle_pick_up_item(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    item = world.resolve_item(args.get("item", ""))
    room = state.current_room(game)
    key = f"{room.id}:{item}"

    if item not in room.items:
        return _fail(f"There is no '{item}' to pick up in {room.name}.")
    if key in (game.collected_items or []):
        return _fail(f"The {item} here has already been taken.")

    state.add_inventory(db, game, item, 1)
    game.collected_items = list(game.collected_items or []) + [key]
    flag_modified(game, "collected_items")
    events = [f"{item} added to your inventory."]
    if item == world.ITEM_ANCIENT_RELIC and room.id == "treasure_vault":
        game.status = GameStatus.won
        events.append("You claim the Ancient Relic. Quest complete!")
    return _ok(f"Picked up {item}.", events)


def handle_drop_item(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    item = world.resolve_item(args.get("item", ""))
    if not state.has_item(game, item):
        return _fail(f"You are not carrying a '{item}'.")

    state.remove_inventory(db, game, item, 1)
    return _ok(f"Dropped {item}.", [f"{item} removed from your inventory."])


def handle_heal_player(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    if not state.has_item(game, world.ITEM_HEALTH_POTION):
        return _fail("You have no health potion to drink.")
    if game.hp >= world.MAX_HP:
        return _fail("You are already at full health.")

    state.remove_inventory(db, game, world.ITEM_HEALTH_POTION, 1)
    healed_from = game.hp
    game.hp = min(world.MAX_HP, game.hp + world.POTION_HEAL_AMOUNT)
    restored = game.hp - healed_from
    return _ok(
        f"Drank a health potion, restoring {restored} HP (now {game.hp}).",
        [
            f"Restored {restored} HP (now {game.hp}/{world.MAX_HP}).",
            "One health potion consumed.",
        ],
    )


def handle_apply_damage(db: Session, game: Game, args: dict) -> dict:
    if (blocked := _check_active(game)) is not None:
        return blocked

    target = str(args.get("target", "")).lower().strip()
    if target != "player":
        return _fail("apply_damage can only target 'player'.")

    amount = args.get("amount")
    if not isinstance(amount, int) or amount <= 0:
        return _fail("Damage amount must be a positive integer.")
    if amount > MAX_ENV_DAMAGE:
        return _fail(f"Damage amount exceeds the maximum allowed ({MAX_ENV_DAMAGE}).")

    game.hp = max(0, game.hp - amount)
    _check_win_lose(game)

    events = [f"You took {amount} damage (HP now {game.hp})."]
    if game.status == GameStatus.lost:
        events.append("You have fallen.")

    return _ok(f"The player takes {amount} damage (HP now {game.hp}).", events)


HANDLERS = {
    "move_player": handle_move_player,
    "attack": handle_attack,
    "pick_up_item": handle_pick_up_item,
    "drop_item": handle_drop_item,
    "heal_player": handle_heal_player,
    "apply_damage": handle_apply_damage,
}


def execute_tool(db: Session, game: Game, name: str, args: dict) -> dict:
    """Run a tool handler and return a fully-decorated structured result.

    The returned dict always contains ``ok``, ``action``, ``previous_state``
    and ``updated_state`` so the narration step is grounded strictly in the
    server's authoritative state after the mutation.
    """
    previous_state = state.state_summary(game)
    handler = HANDLERS.get(name)
    if handler is None:
        result = _fail(f"Unknown tool '{name}'.")
    else:
        result = handler(db, game, args)

    result.setdefault("events", [])
    result["action"] = name
    result["previous_state"] = previous_state
    result["updated_state"] = state.state_summary(game)
    return result
