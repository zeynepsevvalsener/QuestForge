# QuestForge

A tiny text-adventure RPG where an AI Game Master narrates your story — but the **backend** owns the truth. You type natural-language actions; OpenAI proposes tool calls; the server validates every move against a fixed world map and Postgres state, then streams back grounded narration of what actually happened.

**Goal:** Defeat the goblin, unlock the sealed north door, enter the Treasure Vault, and **claim the Ancient Relic** to finish the run.

---

## Tech choices


| Layer                  | Stack                                                                                    |
| ---------------------- | ---------------------------------------------------------------------------------------- |
| **Frontend**           | Next.js 15, React 19, TypeScript, TanStack Query — deployed on **Vercel**                |
| **Backend**            | **FastAPI** (Python 3.12), **SQLAlchemy 2**, **Alembic** migrations                      |
| **Database**           | **PostgreSQL 16**                                                                        |
| **Auth**               | JWT (python-jose) + bcrypt password hashing                                              |
| **AI**                 | **OpenAI** Chat Completions API with function calling (`gpt-4o` by default)              |
| **Local dev**          | Docker Compose (Postgres + backend); frontend runs with `npm run dev`                    |
| **Production backend** | Docker image via **Render** (blueprint in `render.yaml`) or **Railway** (`railway.json`) |


Design principle: the AI is only a storyteller. Every HP change, move, pickup, and win/lose transition goes through a server-side tool handler that reads/writes authoritative state in the database.

---

## AI tools (function calling)

These six tools are exposed to the model via OpenAI function calling. The AI **proposes** them; handlers in `backend/app/game/tools.py` **accept or reject** each call.


| Tool           | What it does                                                                                                                                                         |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `move_player`  | Move one step in a compass direction (`north` / `south` / `east` / `west`). Rejected if the exit doesn't exist, is locked (goblin still alive), or the game is over. |
| `attack`       | Attack the enemy in the current room. Server computes damage (iron sword: 20, bare fists: 8), applies goblin counterattack (12), and tracks enemy HP.                |
| `pick_up_item` | Pick up a floor item in the current room (`health_potion`, `iron_sword`, `ancient_relic`). Each room item can only be collected once.                                |
| `drop_item`    | Remove one copy of an item from the player's inventory.                                                                                                              |
| `heal_player`  | Consume one `health_potion` to restore 30 HP (capped at 100). Server decides the amount — the player cannot choose.                                                  |
| `apply_damage` | Apply environmental/trap damage to the player only (`target` must be `"player"`, `amount` 1–40). Used when the GM narrates hazards.                                  |


Unknown tools are rejected. No tool exists to set HP, teleport, spawn items, or declare victory — those are impossible by design.

---

## Keeping the AI honest

1. **Authoritative handlers** — All state mutation flows through `execute_tool()` → a named handler. Illegal requests return structured failures (`ok=false`, `error=...`) and **nothing is written** to the DB.
2. **Static world validation** — Room exits, items, enemies, and locked doors are defined in code (`backend/app/game/world.py`). Handlers check the player's actual location, inventory, and enemy HP against that map.
3. **Win / lose enforced server-side** — `_check_win_lose()` sets `status = lost` when `hp <= 0`, and `status = won` only after the player has claimed the `ancient_relic` in the Treasure Vault. Entering the vault alone is not a win state.
4. **Two-phase agent loop** — Tool rounds run at `temperature=0` with up to 5 rounds; each result is committed and the fresh state is re-injected. A final **narration-only** call (no tools, `temperature=0.7`) describes outcomes strictly from accepted/rejected tool results. If the model returns no text, a deterministic fallback is built from tool results.
5. **Prompt guardrails** — The system prompt requires a tool call for every state-changing action and forbids inventing HP, inventory, or location. Rejected tools must be narrated as failures.
6. **Tests** — `backend/tests/test_tools.py` covers illegal moves, locked exits, potion consumption, damage bounds, game-over blocking, and the full win path.

---

## Live deployment


| Service               | URL                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------ |
| **Frontend (Vercel)** | [https://quest-forge-roan.vercel.app](https://quest-forge-roan.vercel.app)           |
| **Backend (Render)**  | [https://questforge-api-059b.onrender.com](https://questforge-api-059b.onrender.com) |


The Vercel frontend expects `NEXT_PUBLIC_API_URL` to point at your deployed backend (Render/Railway). Set the same origin in the backend's `CORS_ORIGINS`.

---

## Gameplay flow

The intended happy-path run is:

1. `go north` (Great Hall)
2. `go east` + `take sword` (Old Armory)
3. `go west` + `take potion` (Great Hall)
4. `go west` + `attack goblin` until defeated (Goblin Lair)
5. `go east` + `go north` (enter Treasure Vault; game still `active`)
6. `take reward` (alias of taking `ancient_relic`) to set `status = won`

This is intentional: **entering the vault does not instantly end the game**. The run ends only when the relic is claimed.

---

## Run locally

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for the frontend)
- An [OpenAI API key](https://platform.openai.com/) with access to a tool-capable model (default: `gpt-4o`)

### 1. Environment variables

Copy the root env file and fill in secrets:

```bash
cp .env.example .env
```

Edit `.env`:


| Variable                                              | Purpose                                                           |
| ----------------------------------------------------- | ----------------------------------------------------------------- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials (defaults work for local Docker)             |
| `JWT_SECRET`                                          | Long random string for signing JWTs                               |
| `OPENAI_API_KEY`                                      | Your OpenAI API key                                               |
| `OPENAI_MODEL`                                        | Model name (default: `gpt-4o`)                                    |
| `CORS_ORIGINS`                                        | Comma-separated allowed origins (include `http://localhost:3000`) |


For the frontend:

```bash
cp frontend/.env.example frontend/.env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Start Postgres + backend

```bash
docker compose up --build
```

This builds the backend image, waits for Postgres to become healthy, runs `alembic upgrade head` automatically (via `entrypoint.sh`), and starts the API on **[http://localhost:8000](http://localhost:8000)**.

Health check: `curl http://localhost:8000/health`

### 3. Run database migrations manually (optional)

Migrations run on container start. To run them yourself (e.g. against a local Postgres without Docker):

```bash
cd backend
export DATABASE_URL=postgresql+psycopg2://questforge:questforge@localhost:5432/questforge
alembic upgrade head
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **[http://localhost:3000](http://localhost:3000)**.

### 5. Run backend tests

```bash
docker compose exec backend pytest
```

---

## Test account

Register directly at `/register` and sign in with that account.  
No seed script is required.

---

## Local backend + deployed Vercel frontend

If the frontend on Vercel should talk to your **local** backend, expose port 8000 with a tunnel and update both sides:

**Cloudflare Tunnel (recommended):**

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the generated `https://*.trycloudflare.com` URL.

**ngrok:**

```bash
ngrok http 8000
```

Then:

1. Set `NEXT_PUBLIC_API_URL` in the Vercel project settings to the tunnel URL.
2. Add that same URL to `CORS_ORIGINS` in your local `.env` and restart the backend:
  ```bash
   docker compose up --build
  ```

Redeploy or rebuild the Vercel frontend after changing `NEXT_PUBLIC_API_URL`.

---

## AI provider

**OpenAI** — Chat Completions API with function calling.

- Default model: `gpt-4o` (configurable via `OPENAI_MODEL`)
- Requires a model that supports tool use / function calling

---

## Demo video link

- [https://youtu.be/P_nddH5lR68](https://youtu.be/P_nddH5lR68)

---

## Submission checklist

- [x] Repo link
- [x] Live Vercel URL
- [x] Backend location (cloud URL or local + tunnel command)
- [x] Test account or registration instructions
- [x] AI provider used (tool use capable)
- [x] List of tools exposed to the AI
- [x] How backend validates tool calls / enforces win-lose
- [x] `.env.example` committed
- [x] Migration file(s) committed
- [x] `docker compose up` works locally
- [x] Demo video link
- [x] No secrets committed

---

## Project layout

```
QuestForge/
├── frontend/          # Next.js app (Vercel)
├── backend/
│   ├── app/
│   │   ├── agent/     # GM loop, prompts, OpenAI client
│   │   ├── game/      # World map, tools, state helpers
│   │   ├── routers/   # /auth, /games API
│   │   └── models/    # SQLAlchemy models
│   ├── alembic/       # DB migrations
│   ├── scripts/       # seed_test_user.py
│   └── tests/         # Tool validation / anti-cheat tests
├── docker-compose.yml
└── render.yaml        # Render deployment blueprint
```

