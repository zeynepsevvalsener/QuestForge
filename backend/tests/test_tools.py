"""Anti-cheat tests: the backend must reject illegal tool calls and never let
the AI mutate state directly. These exercise the authoritative tool handlers.
"""

from app.game import state, tools, world
from app.models import Game, GameStatus
from sqlalchemy.orm import Session


def _exec(db: Session, game: Game, name: str, **args) -> dict:
    result = tools.execute_tool(db, game, name, args)
    db.commit()
    db.refresh(game)
    return result


def test_move_valid_exit(db: Session, game: Game):
    res = _exec(db, game, "move_player", direction="north")
    assert res["accepted"] is True
    assert game.location == "hall"


def test_move_invalid_exit_rejected(db: Session, game: Game):
    res = _exec(db, game, "move_player", direction="west")
    assert res["accepted"] is False
    assert game.location == "entrance"  # unchanged


def test_locked_exit_blocked_until_enemy_dead(db: Session, game: Game):
    _exec(db, game, "move_player", direction="north")  # hall
    res = _exec(db, game, "move_player", direction="north")  # treasure locked
    assert res["accepted"] is False
    assert game.location == "hall"


def test_pickup_only_present_items(db: Session, game: Game):
    # No iron_sword at entrance.
    res = _exec(db, game, "pick_up_item", item="iron_sword")
    assert res["accepted"] is False
    assert state.inventory_map(game) == {}


def test_pickup_then_cannot_pickup_twice(db: Session, game: Game):
    _exec(db, game, "move_player", direction="north")  # hall has health_potion
    first = _exec(db, game, "pick_up_item", item="health_potion")
    assert first["accepted"] is True
    assert state.has_item(game, "health_potion")
    second = _exec(db, game, "pick_up_item", item="health_potion")
    assert second["accepted"] is False


def test_heal_requires_potion(db: Session, game: Game):
    game.hp = 50
    db.commit()
    res = _exec(db, game, "heal_player")
    assert res["accepted"] is False
    assert game.hp == 50  # no self-heal without a potion


def test_heal_consumes_potion_and_caps(db: Session, game: Game):
    game.hp = 90
    state.add_inventory(db, game, "health_potion", 1)
    db.commit()
    res = _exec(db, game, "heal_player")
    assert res["accepted"] is True
    assert game.hp == world.MAX_HP  # capped, not 90 + 30
    assert not state.has_item(game, "health_potion")  # consumed


def test_attack_requires_enemy_present(db: Session, game: Game):
    res = _exec(db, game, "attack", target="goblin")
    assert res["accepted"] is False  # no goblin at entrance


def test_attack_dead_enemy_rejected(db: Session, game: Game):
    game.location = "goblin_lair"
    game.enemy_hp = 0
    db.commit()
    res = _exec(db, game, "attack", target="goblin")
    assert res["accepted"] is False


def test_apply_damage_only_player_and_bounded(db: Session, game: Game):
    assert _exec(db, game, "apply_damage", target="goblin", amount=10)["accepted"] is False
    assert _exec(db, game, "apply_damage", target="player", amount=9999)["accepted"] is False
    assert _exec(db, game, "apply_damage", target="player", amount=-5)["accepted"] is False
    ok = _exec(db, game, "apply_damage", target="player", amount=10)
    assert ok["accepted"] is True
    assert game.hp == world.STARTING_HP - 10


def test_hp_never_below_zero_and_loses(db: Session, game: Game):
    game.hp = 5
    db.commit()
    _exec(db, game, "apply_damage", target="player", amount=tools.MAX_ENV_DAMAGE)
    assert game.hp == 0
    assert game.status == GameStatus.lost


def test_no_actions_after_game_over(db: Session, game: Game):
    game.status = GameStatus.lost
    db.commit()
    res = _exec(db, game, "move_player", direction="north")
    assert res["accepted"] is False


def test_full_win_path(db: Session, game: Game):
    # entrance -> hall -> armory (sword) -> hall -> goblin_lair (kill) -> hall -> treasure
    _exec(db, game, "move_player", direction="north")
    _exec(db, game, "move_player", direction="east")
    assert _exec(db, game, "pick_up_item", item="iron_sword")["accepted"] is True
    _exec(db, game, "move_player", direction="west")
    _exec(db, game, "move_player", direction="west")  # goblin_lair
    # Sword does 20 dmg; goblin has 50 hp -> 3 hits.
    for _ in range(5):
        if not state.enemy_alive(game):
            break
        _exec(db, game, "attack", target="goblin")
    assert game.enemy_hp == 0
    _exec(db, game, "move_player", direction="east")  # hall
    res = _exec(db, game, "move_player", direction="north")  # treasure, now unlocked
    assert res["accepted"] is True
    assert game.status == GameStatus.won
