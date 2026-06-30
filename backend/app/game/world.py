"""Static, code-seeded world definition.

The world is intentionally tiny (PDF scope): 5 rooms, one enemy (goblin),
and two item types (health_potion, iron_sword). Per-game mutable state
(HP, location, inventory, enemy HP, collected floor items) lives in Postgres.
This module only describes the immutable layout the backend validates against.
"""

from dataclasses import dataclass, field

STARTING_HP = 100
MAX_HP = 100

ENEMY_ID = "goblin"
ENEMY_MAX_HP = 50
ENEMY_ATTACK = 12

ITEM_HEALTH_POTION = "health_potion"
ITEM_IRON_SWORD = "iron_sword"

POTION_HEAL_AMOUNT = 30
FISTS_DAMAGE = 8
SWORD_DAMAGE = 20

KNOWN_ITEMS = {ITEM_HEALTH_POTION, ITEM_IRON_SWORD}


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    description: str
    exits: dict[str, str]
    items: tuple[str, ...] = ()
    enemy: str | None = None
    is_win: bool = False
    # Exits that are only traversable once the enemy in the world is defeated.
    locked_exits: dict[str, str] = field(default_factory=dict)


WORLD: dict[str, Room] = {
    "entrance": Room(
        id="entrance",
        name="Cave Entrance",
        description=(
            "A damp cave mouth. Faint torchlight flickers to the north, "
            "where a wider hall opens up."
        ),
        exits={"north": "hall"},
    ),
    "hall": Room(
        id="hall",
        name="Great Hall",
        description=(
            "A vast stone hall. A health potion glints on a mossy pedestal. "
            "Passages lead east to an armory and west into a foul-smelling lair. "
            "A heavy door stands to the north."
        ),
        exits={"south": "entrance", "east": "armory", "west": "goblin_lair"},
        locked_exits={"north": "treasure_room"},
        items=(ITEM_HEALTH_POTION,),
    ),
    "armory": Room(
        id="armory",
        name="Old Armory",
        description=(
            "Rusted weapon racks line the walls. A single iron sword still "
            "looks serviceable."
        ),
        exits={"west": "hall"},
        items=(ITEM_IRON_SWORD,),
    ),
    "goblin_lair": Room(
        id="goblin_lair",
        name="Goblin Lair",
        description=(
            "A cramped, reeking den. A snarling goblin guards the way, "
            "blocking any path deeper in."
        ),
        exits={"east": "hall"},
        enemy=ENEMY_ID,
    ),
    "treasure_room": Room(
        id="treasure_room",
        name="Treasure Vault",
        description=(
            "Behind the sealed door lies a glittering vault of gold and gems. "
            "Your quest is complete."
        ),
        exits={"south": "hall"},
        is_win=True,
    ),
}

STARTING_ROOM = "entrance"


def get_room(room_id: str) -> Room | None:
    return WORLD.get(room_id)
