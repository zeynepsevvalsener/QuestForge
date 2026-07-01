"""The agentic GM loop.

Flow for one player turn:
  1. Persist the player's message.
  2. Reconstruct conversation context from prior turns + the authoritative state.
  3. Resolve tool calls in bounded, non-streamed rounds. Each accepted tool call
     mutates state inside a DB transaction; rejected calls change nothing.
  4. AFTER all tool handlers finish, reload updated_state from the database and
     make a dedicated streamed narration call whose only inputs are
     (player_action, previous_state, tool_result, updated_state) -- so the words
     the player reads always describe what the server actually did.
"""

import json
import re
from collections.abc import Iterator

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agent import prompts
from app.config import settings
from app.game import state, tools
from app.models import Game, Turn, TurnRole

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _fallback_narration(executed: list[dict]) -> str:
    """Deterministic, server-grounded narration used only if the model returns
    no text. Built straight from the validated tool results, so it can never
    contradict the authoritative state."""
    accepted = [e for e in executed if e.get("ok")]
    if accepted:
        parts: list[str] = []
        for e in accepted:
            if e.get("message"):
                parts.append(e["message"])
            parts.extend(e.get("events") or [])
        return " ".join(parts) or "Done."
    rejected = [e["error"] for e in executed if not e.get("ok") and e.get("error")]
    if rejected:
        return "That didn't work. " + " ".join(rejected)
    return "Nothing happens."


_ACTION_INTENT = re.compile(
    r"\b(go|move|walk|head|travel|enter|return|leave|north|south|east|west|"
    r"attack|hit|fight|strike|kill|slay|stab|swing|"
    r"take|grab|pick|loot|collect|"
    r"drop|discard|"
    r"drink|heal|quaff|consume)\b",
    re.IGNORECASE,
)


def _wants_action(text: str) -> bool:
    """True when the player's message clearly requests a state-changing action.

    Used only to force *some* tool call on the first round; the model still
    decides which tool and arguments (and the handler still validates it).
    """
    return bool(_ACTION_INTENT.search(text or ""))


def _history_messages(game: Game, limit: int = 12) -> list[dict]:
    """Recent turns as plain chat history for narrative continuity.

    The final turn (the current player action, already persisted) is excluded
    because it is appended to the prompt explicitly by the caller.
    """
    messages: list[dict] = []
    prior_turns = game.turns[:-1] if game.turns else []
    for turn in prior_turns[-limit:]:
        role = "user" if turn.role == TurnRole.player else "assistant"
        if turn.content:
            messages.append({"role": role, "content": turn.content})
    return messages


def run_turn(db: Session, game: Game, player_action: str) -> Iterator[str]:
    db.add(Turn(game_id=game.id, role=TurnRole.player, content=player_action))
    db.commit()
    db.refresh(game)

    yield _sse("start", {"action": player_action})

    previous_state = state.state_summary(game)

    messages: list[dict] = [{"role": "system", "content": prompts.SYSTEM_PROMPT}]
    messages.extend(_history_messages(game))
    messages.append({"role": "system", "content": prompts.build_state_message(previous_state)})
    messages.append({"role": "user", "content": player_action})

    executed: list[dict] = []
    last_content = ""
    client = get_client()
    force_first_tool = _wants_action(player_action)

    try:
        for round_index in range(settings.max_tool_rounds):
            tool_choice = (
                "required" if (round_index == 0 and force_first_tool) else "auto"
            )
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools.TOOL_DEFINITIONS,
                tool_choice=tool_choice,
                temperature=0,
            )
            choice = response.choices[0].message
            if choice.content:
                last_content = choice.content

            if not choice.tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.tool_calls
                    ],
                }
            )

            for tc in choice.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                result = tools.execute_tool(db, game, name, args)
                db.commit()
                db.refresh(game)

                record = {
                    "tool": name,
                    "action": result.get("action", name),
                    "args": args,
                    "ok": result.get("ok", False),
                    "message": result.get("message"),
                    "error": result.get("error"),
                    "events": result.get("events", []),
                }
                executed.append(record)
                yield _sse("tool", record)

                tool_payload = {
                    "ok": result.get("ok"),
                    "action": result.get("action", name),
                    "events": result.get("events", []),
                    "updated_state": result.get("updated_state"),
                }
                if result.get("ok"):
                    tool_payload["message"] = result.get("message")
                else:
                    tool_payload["error"] = result.get("error")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_payload),
                    }
                )

            messages.append(
                {
                    "role": "system",
                    "content": prompts.build_state_message(state.state_summary(game)),
                }
            )

        db.refresh(game)
        updated_state = state.state_summary(game)

        narration_messages: list[dict] = [
            {"role": "system", "content": prompts.NARRATION_PROMPT}
        ]
        narration_messages.extend(_history_messages(game))
        narration_messages.append(
            {
                "role": "user",
                "content": prompts.build_narration_input(
                    player_action, previous_state, executed, updated_state
                ),
            }
        )

        narration_parts: list[str] = []
        stream = client.chat.completions.create(
            model=settings.openai_model,
            messages=narration_messages,
            temperature=0.7,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                narration_parts.append(delta)
                yield _sse("token", {"text": delta})

        streamed = "".join(narration_parts).strip()
        narration = streamed or last_content.strip() or _fallback_narration(executed)

        if not streamed and narration:
            yield _sse("token", {"text": narration})

    except Exception as exc:  # noqa: BLE001 - surface AI/transport errors without corrupting state
        db.rollback()
        narration = (
            "The Game Master's vision blurs (the AI service is unavailable). "
            "Your action could not be narrated, but your game state is safe."
        )
        gm_turn = Turn(
            game_id=game.id,
            role=TurnRole.gm,
            content=narration,
            tool_calls=executed or None,
        )
        db.add(gm_turn)
        db.commit()
        yield _sse("error", {"message": str(exc), "narration": narration})
        yield _sse("done", {"status": game.status.value, "hp": game.hp})
        return

    gm_turn = Turn(
        game_id=game.id,
        role=TurnRole.gm,
        content=narration,
        tool_calls=executed or None,
    )
    db.add(gm_turn)
    db.commit()
    db.refresh(game)

    yield _sse(
        "done",
        {
            "status": game.status.value,
            "hp": game.hp,
            "location": game.location,
        },
    )
