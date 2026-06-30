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
      // Refresh authoritative state, then drop the local live buffer.
      await queryClient.invalidateQueries({ queryKey: ["game"] });
      setLive(null);
    }
  }

  if (!ready || isLoading) {
    return (
      <div className="center-screen">
        <p className="empty">Loading your quest...</p>
      </div>
    );
  }

  return (
    <div className="game-shell">
      <header className="topbar">
        <h1>QuestForge</h1>
        <div style={{ display: "flex", gap: 8 }}>
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
        <div className="panel" style={{ gridColumn: "1 / -1", textAlign: "center" }}>
          <p>You have no active quest.</p>
          <button
            className="btn-primary"
            style={{ maxWidth: 220, margin: "12px auto 0" }}
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
          >
            {startMutation.isPending ? "Forging..." : "Start a new game"}
          </button>
        </div>
      ) : (
        <>
          <StatsPanel game={game} />

          <main className="panel log">
            {game.status === "won" && <div className="banner won">Victory! You cleared the dungeon.</div>}
            {game.status === "lost" && <div className="banner lost">You have fallen. Game over.</div>}

            <GameLog turns={game.turns} live={live} />

            {actionError && <div className="error-box">{actionError}</div>}

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
                className="btn-primary"
                style={{ width: "auto", padding: "0 20px" }}
                type="submit"
                disabled={busy || game.status !== "active" || !action.trim()}
              >
                {busy ? "..." : "Act"}
              </button>
            </form>
          </main>
        </>
      )}
    </div>
  );
}
