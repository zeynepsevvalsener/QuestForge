"""Static, code-seeded world definition.

The world is intentionally tiny (PDF scope): 5 rooms, one enemy (goblin),
and three item types (health_potion, iron_sword, ancient_relic). Per-game mutable state
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
ITEM_ANCIENT_RELIC = "ancient_relic"

POTION_HEAL_AMOUNT = 30
FISTS_DAMAGE = 8
SWORD_DAMAGE = 20

KNOWN_ITEMS = {ITEM_HEALTH_POTION, ITEM_IRON_SWORD, ITEM_ANCIENT_RELIC}

# Natural-language item names the AI (or player) might use, mapped to canonical ids.
ITEM_ALIASES: dict[str, str] = {
    "potion": ITEM_HEALTH_POTION,
    "health potion": ITEM_HEALTH_POTION,
    "health_potion": ITEM_HEALTH_POTION,
    "healing potion": ITEM_HEALTH_POTION,
    "sword": ITEM_IRON_SWORD,
    "iron sword": ITEM_IRON_SWORD,
    "iron_sword": ITEM_IRON_SWORD,
    "relic": ITEM_ANCIENT_RELIC,
    "ancient relic": ITEM_ANCIENT_RELIC,
    "treasure": ITEM_ANCIENT_RELIC,
    "reward": ITEM_ANCIENT_RELIC,
    "loot": ITEM_ANCIENT_RELIC,
}


def resolve_item(name: str) -> str:
    """Map a free-form item name onto a canonical item id."""
    normalized = " ".join(str(name).lower().replace("_", " ").split())
    if normalized in ITEM_ALIASES:
        return ITEM_ALIASES[normalized]
    return normalized.replace(" ", "_")


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
    "cave_entrance": Room(
        id="cave_entrance",
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
        exits={"south": "cave_entrance", "east": "armory", "west": "goblin_lair"},
        locked_exits={"north": "treasure_vault"},
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
    "treasure_vault": Room(
        id="treasure_vault",
        name="Treasure Vault",
        description=(
            "Behind the sealed door lies a glittering vault of gold and gems. "
            "A singular ancient relic rests on a stone dais at the center."
        ),
        exits={"south": "hall"},
        items=(ITEM_ANCIENT_RELIC,),
    ),
}

STARTING_ROOM = "cave_entrance"

# Backward-compatible aliases for games created before rooms were renamed.
LOCATION_ALIASES: dict[str, str] = {
    "entrance": "cave_entrance",
    "treasure_room": "treasure_vault",
}


def normalize_location(location: str) -> str:
    """Map legacy room ids onto their current equivalents."""
    return LOCATION_ALIASES.get(location, location)


def room_for(location: str) -> Room:
    return WORLD[normalize_location(location)]


def get_room(room_id: str) -> Room | None:
    return WORLD.get(normalize_location(room_id))
