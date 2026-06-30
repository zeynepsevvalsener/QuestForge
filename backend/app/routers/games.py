from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent import loop
from app.auth.dependencies import get_current_user
from app.database import SessionLocal, get_db
from app.game import state
from app.models import Game, GameStatus, User
from app.schemas.game import ActionRequest, GameStateResponse

router = APIRouter(prefix="/games", tags=["games"])


def _active_game_for_user(db: Session, user: User) -> Game | None:
    return (
        db.query(Game)
        .filter(Game.user_id == user.id)
        .order_by(Game.id.desc())
        .first()
    )


def _owned_game_or_404(db: Session, user: User) -> Game:
    game = _active_game_for_user(db, user)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No game found")
    if game.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")
    return game


@router.post("", response_model=GameStateResponse, status_code=status.HTTP_201_CREATED)
def new_game(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    game = state.create_new_game(db, current_user.id)
    db.commit()
    db.refresh(game)
    return state.serialize_game(game)


@router.get("/current", response_model=GameStateResponse)
def current_game(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    game = _owned_game_or_404(db, current_user)
    return state.serialize_game(game)


@router.delete("/current", response_model=GameStateResponse, status_code=status.HTTP_201_CREATED)
def reset_game(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    """Start a fresh game (the previous one is left in history)."""
    game = state.create_new_game(db, current_user.id)
    db.commit()
    db.refresh(game)
    return state.serialize_game(game)


@router.post("/current/action")
def take_action(
    payload: ActionRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    action = payload.action.strip()
    if not action:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty action")

    # Use a dedicated session for the lifetime of the stream so it stays open
    # while tokens are produced, then is reliably closed afterward.
    db = SessionLocal()
    game = _active_game_for_user(db, current_user)
    if game is None:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No game found")
    if game.user_id != current_user.id:
        db.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game")
    if game.status != GameStatus.active:
        db.close()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Game is over (status: {game.status.value}). Start a new game.",
        )

    def event_stream():
        try:
            yield from loop.run_turn(db, game, action)
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
