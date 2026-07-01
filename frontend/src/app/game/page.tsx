"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { GameLog, LiveTurn } from "@/components/GameLog";
import { StatsPanel } from "@/components/StatsPanel";
import {
  UnauthorizedError,
  getCurrentGame,
  newGame,
  resetGame,
  streamAction,
} from "@/lib/api";
import type { GameState, ToolCallRecord } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";

function suggestedCommands(game: GameState): string[] {
  const cmds: string[] = ["look around"];
  const exits = game.room?.exits ? Object.keys(game.room.exits) : [];
  for (const dir of ["north", "south", "east", "west"]) {
    if (exits.includes(dir)) cmds.push(`go ${dir}`);
  }
  const itemsHere = game.room?.items ?? [];
  if (itemsHere.includes("iron_sword")) cmds.push("take sword");
  if (itemsHere.includes("health_potion")) cmds.push("take potion");
  if (itemsHere.includes("ancient_relic")) cmds.push("take reward");
  if (game.room?.enemy === "goblin") cmds.push("attack goblin");
  if (game.inventory.some((i) => i.item === "health_potion")) cmds.push("drink potion");
  cmds.push("check inventory");
  return cmds;
}

export default function GamePage() {
  const { ready, isAuthenticated, logout } = useAuth(true);
  const queryClient = useQueryClient();

  const [action, setAction] = useState("");
  const [live, setLive] = useState<LiveTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const {
    data: game,
    isLoading,
    error,
  } = useQuery<GameState | null>({
    queryKey: ["game"],
    queryFn: getCurrentGame,
    enabled: ready && isAuthenticated,
  });

  const startMutation = useMutation({
    mutationFn: newGame,
    onSuccess: (data) => {
      queryClient.setQueryData(["game"], data);
      setLive(null);
    },
  });

  const resetMutation = useMutation({
    mutationFn: resetGame,
    onSuccess: (data) => {
      queryClient.setQueryData(["game"], data);
      setLive(null);
    },
  });

  if (error instanceof UnauthorizedError) {
    logout();
  }

  async function submitAction(e: FormEvent) {
    e.preventDefault();
    const text = action.trim();
    if (!text || busy) return;

    setActionError(null);
    setBusy(true);
    setAction("");
    setLive({ player: text, gm: "", tools: [], streaming: true });

    try {
      await streamAction(text, {
        onTool: (record) =>
          setLive((prev) =>
            prev ? { ...prev, tools: [...prev.tools, record as ToolCallRecord] } : prev,
          ),
        onToken: (token) =>
          setLive((prev) => (prev ? { ...prev, gm: prev.gm + token } : prev)),
        onError: (message) => setActionError(message),
        onDone: () => {},
      });
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        logout();
        return;
      }
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
      setLive((prev) => (prev ? { ...prev, streaming: false } : prev));
      await queryClient.invalidateQueries({ queryKey: ["game"] });
      setLive(null);
    }
  }

  if (!ready || isLoading) {
    return (
      <div className="center-screen">
        <div className="loader">
          <span className="loader-spinner" />
          <p className="empty">Loading your quest...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="game-shell">
      <header className="topbar">
        <div className="brand">
          <h1>QuestForge</h1>
          <span className="tagline">AI Game Master &middot; text-adventure RPG</span>
        </div>
        <div className="topbar-actions">
          {game && (
            <button
              className="btn-secondary"
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending || busy}
            >
              New game
            </button>
          )}
          <button className="btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      {!game ? (
        <div className="hero">
          <div className="hero-card">
            <div className="hero-emblem">&#9876;</div>
            <h2>Your quest awaits</h2>
            <p className="hero-lead">
              A torch-lit dungeon lies ahead, narrated by an AI Game Master. Explore
              the rooms, claim the iron sword, defeat the goblin, and reach the
              Treasure Vault.
            </p>
            <ol className="hero-steps">
              <li>Head north into the Great Hall</li>
              <li>Grab the iron sword from the armory</li>
              <li>Defeat the goblin in its lair</li>
              <li>Return and go north to the Treasure Vault</li>
            </ol>
            <button
              className="btn-primary hero-start"
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
            >
              {startMutation.isPending ? "Forging your quest..." : "Start a new game"}
            </button>
          </div>
        </div>
      ) : (
        <div className="game-grid">
          <StatsPanel game={game} />

          <main className="panel log">
            {game.status === "won" && (
              <div className="banner won">Victory! You cleared the dungeon.</div>
            )}
            {game.status === "lost" && (
              <div className="banner lost">You have fallen. Game over.</div>
            )}

            <GameLog turns={game.turns} live={live} />

            {actionError && <div className="error-box">{actionError}</div>}

            {game.status === "active" && (
              <div className="suggestions">
                {suggestedCommands(game).map((cmd) => (
                  <button
                    key={cmd}
                    type="button"
                    className="suggestion-chip"
                    disabled={busy}
                    onClick={() => setAction(cmd)}
                  >
                    {cmd}
                  </button>
                ))}
              </div>
            )}

            <form className="action-bar" onSubmit={submitAction}>
              <input
                type="text"
                placeholder={
                  game.status === "active"
                    ? "What do you do? (e.g. go north, attack the goblin)"
                    : "The game is over. Start a new game to play again."
                }
                value={action}
                onChange={(e) => setAction(e.target.value)}
                disabled={busy || game.status !== "active"}
              />
              <button
                className="btn-primary act-btn"
                type="submit"
                disabled={busy || game.status !== "active" || !action.trim()}
              >
                {busy ? "..." : "Act"}
              </button>
            </form>
          </main>
        </div>
      )}
    </div>
  );
}
