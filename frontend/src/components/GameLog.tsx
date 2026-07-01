"use client";

import { useEffect, useRef } from "react";

import type { ToolCallRecord, Turn } from "@/lib/types";

export interface LiveTurn {
  player: string;
  gm: string;
  tools: ToolCallRecord[];
  streaming: boolean;
}

function ToolChips({ tools }: { tools: ToolCallRecord[] }) {
  if (!tools?.length) return null;
  return (
    <div className="tool-chips">
      {tools.map((t, i) => {
        const ok = (t.ok ?? t.accepted) ?? false;
        const label = t.action ?? t.tool;
        const title = t.ok
          ? t.message || (t.events ?? []).join(" ")
          : t.error || t.reason || t.result || "";
        return (
          <span
            key={i}
            className={`chip ${ok ? "accepted" : "rejected"}`}
            title={title}
          >
            {label} {ok ? "ok" : "failed"}
          </span>
        );
      })}
    </div>
  );
}

export function GameLog({ turns, live }: { turns: Turn[]; live: LiveTurn | null }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, live?.gm, live?.player]);

  return (
    <div className="log-entries">
      {turns.map((turn) => (
        <div key={turn.id} className={`entry ${turn.role}`}>
          <div className="who">{turn.role === "player" ? "You" : "Game Master"}</div>
          <div className="text">{turn.content}</div>
          {turn.role === "gm" && turn.tool_calls && (
            <ToolChips tools={turn.tool_calls} />
          )}
        </div>
      ))}

      {live && (
        <>
          {live.player && (
            <div className="entry player">
              <div className="who">You</div>
              <div className="text">{live.player}</div>
            </div>
          )}
          <div className="entry gm">
            <div className="who">Game Master</div>
            <div className="text">
              {live.gm}
              {live.streaming && <span className="cursor-blink">{"\u258a"}</span>}
            </div>
            <ToolChips tools={live.tools} />
          </div>
        </>
      )}

      <div ref={endRef} />
    </div>
  );
}
