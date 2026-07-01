"use client";

import type { GameState } from "@/lib/types";

function hpColor(ratio: number): string {
  if (ratio > 0.5) return "var(--hp)";
  if (ratio > 0.25) return "var(--accent)";
  return "var(--hp-low)";
}

export function StatsPanel({ game }: { game: GameState }) {
  const ratio = game.max_hp > 0 ? game.hp / game.max_hp : 0;

  return (
    <aside className="panel stats-panel">
      <div className="stat-row">
        <span className="label">Status</span>
        <span className={`badge ${game.status}`}>{game.status}</span>
      </div>

      <div className="stat-row">
        <span className="label">HP</span>
        <span>
          {game.hp} / {game.max_hp}
        </span>
      </div>
      <div className="hp-bar">
        <div
          className="hp-bar-fill"
          style={{
            width: `${Math.max(0, Math.min(100, ratio * 100))}%`,
            background: hpColor(ratio),
          }}
        />
      </div>

      <div className="stat-row">
        <span className="label">Location</span>
        <span>{game.room?.name ?? game.location}</span>
      </div>

      {game.objective && (
        <div className="objective">
          <span className="label">Objective</span>
          <p>{game.objective}</p>
        </div>
      )}

      {game.room?.enemy && (
        <div className="enemy-panel">
          <div className="section-title" style={{ margin: "0 0 8px" }}>
            Enemy
          </div>
          <div className="enemy-row">
            <span className="enemy-name">{game.room.enemy}</span>
            <span className="enemy-hp-text">
              {game.enemy_hp} / {game.enemy_max_hp}
            </span>
          </div>
          <div className="enemy-bar">
            <div
              className="enemy-bar-fill"
              style={{
                width: `${Math.max(
                  0,
                  Math.min(100, (game.enemy_hp / game.enemy_max_hp) * 100),
                )}%`,
              }}
            />
          </div>
        </div>
      )}

      {game.progress?.length > 0 && (
        <>
          <div className="section-title">Quest Progress</div>
          <ul className="progress-list">
            {game.progress.map((step) => (
              <li key={step.label} className={step.done ? "done" : ""}>
                <span className="check">{step.done ? "\u2611" : "\u2610"}</span>
                {step.label}
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="section-title">Exits</div>
      {game.room && Object.keys(game.room.exits).length > 0 ? (
        <ul className="inventory-list">
          {Object.entries(game.room.exits).map(([dir, dest]) => (
            <li key={dir}>
              <span>{dir}</span>
              <span className="label">{dest}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No obvious exits.</p>
      )}

      <div className="section-title">Items here</div>
      {game.room?.items?.length ? (
        <ul className="inventory-list">
          {game.room.items.map((it) => (
            <li key={it}>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">Nothing on the ground.</p>
      )}

      <div className="section-title">Inventory</div>
      {game.inventory.length > 0 ? (
        <ul className="inventory-list">
          {game.inventory.map((it) => (
            <li key={it.item}>
              <span>{it.item}</span>
              <span className="label">x{it.quantity}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">Empty-handed.</p>
      )}
    </aside>
  );
}
