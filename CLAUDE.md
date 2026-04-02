# 4 AGENTS — Project Context

> Мова спілкування: **українська**. Ніколи не російська.

## What This Is
Multi-agent social simulation platform — "соціальний острів" де AI-агенти взаємодіють.
Two game modes:
- **Island** (main): Prisoner's dilemma-based rounds, agents cooperate/betray
- **Time Wars** (active development): Tick-based loop, agents gain/lose time, steal/cooperate/use codes

## Key Commands
```bash
# Run TIME WARS server
python serve_time_wars.py --port 5174

# Run all tests
python run_all_tests.py

# Run specific test
pytest tests/test_time_wars.py -v

# Run Island simulation
python run_simulation_live.py --rounds 5

# Start both servers
python start_servers.py
```

## Architecture (Key Systems)

```
agents/{id}/          — Per-agent identity (SOUL.md, CORE.json, BIO.md, STATES.md, MEMORY.json)
game_modes/time_wars/ — TIME WARS game loop, state, skills, shop, codes
simulation/           — Island game engine, dialog engine
pipeline/             — Decision engine, soul compiler, memory, state machine
storytell/            — Narrative generation (DECOUPLED from TIME WARS — needs wiring)
server/main.py        — FastAPI (port 8000): agent init pipeline, auth
serve_time_wars.py    — FastAPI (port 5174): TIME WARS server + SSE streaming
frontend/             — React/TS agent initialization UI (Vite, port 5173 dev)
docs/                 — MCS architecture docs + interactive visualizations (v1-v3)
```

## Agents (17 total)
```
agent_65c37face813, agent_synth_c, agent_synth_d, agent_synth_dimonchyk,
agent_synth_e, agent_synth_f, agent_synth_g, agent_synth_h,
agent_synth_i, agent_synth_j, agent_synth_jesus, agent_synth_k,
agent_synth_l, agent_synth_m, agent_synth_mykyta, agent_synth_n (Sergiy),
agent_synth_natalka
```
- Нові агенти (останній коміт): **Natalka, Dimonchyk, Mykyta**
- Roster: `agents/roster.json`

## Roles & Identity
- `SOUL.md` — Narrative identity (8 sections, 2nd person Ukrainian)
- `CORE.json` — Personality params 0-100: cooperation_bias, deception_tendency, strategic_horizon, risk_appetite
- `ROLE_CORE_OVERLAYS` in `agent_context.py` — Role-based modifications to CORE params applied at runtime
- `roles.json` — Role definitions: role_snake, role_gambler, role_banker, role_peacekeeper

## MCS Architecture (docs/)
- `docs/MCS_ARCHITECTURE.md` — Full architecture documentation
- `docs/mcs_architecture_visual.html` — Interactive 4-layer visualization (v1)
- `docs/mcs_v2.html` — v2 visualization
- `docs/mcs_v3.html` — **v3 (latest)**: NPC Anatomy visualization

## Critical Known Issues (as of 2026-03-27)

1. **Agents always cooperate, never steal** — `decision_engine.py::_action_scores()` strategic_horizon penalty keeps agents at 0.66 regardless of role
   - Fix needed: reduce strategic_score weight OR add risk_appetite as positive factor for steal in high-risk roles
2. **Dialog → Action loop broken** — `last_messages` not passed from loop.py to action decision → communication is decorative
3. **SOUL.md not in decision prompts** — agent_context.build_context() doesn't inject personality → agents decide without identity
4. **storytell/ decoupled from TIME WARS** — round_narrative.py exists but never called in loop.py
5. **Character skills don't affect gameplay** — `skills.py` apply_* functions need verification

## Important File Locations
- Game logs: `logs/time_wars_*.jsonl` + `logs/time_wars_*.html`
- Agent configs: `agents/{agent_id}/`
- Roster: `agents/roster.json`
- Role definitions: `game_modes/time_wars/roles.json`
- Code cards: `game_modes/time_wars/codes.json`
- Game constants: `game_modes/time_wars/constants.py`

## Tech Stack
- Backend: Python, FastAPI, SQLAlchemy
- Frontend: React, TypeScript, Vite, Tailwind, Framer Motion
- LLM calls: OpenRouter (see `.env` for keys)
- DB: SQLite (`timewars.db`)

## Git Info
- **Repo:** https://github.com/SerhiiDubei/4_agents
- **Active branch:** `feature/time-wars-roles`
- **Branches:** main, feature/time-wars-roles

## Railway Deployment

**Цей проект деплоїться на Railway.** Кожен `git push` на підключену гілку = автоматичний редеплой.

```
Repo:    https://github.com/SerhiiDubei/4_agents
Branch:  feature/time-wars-roles  (або main після merge)
Config:  railway.toml  ←  живе в репо, не треба руками
```

**Required Variables у Railway dashboard** (Project → Variables):
- `OPENROUTER_API_KEY` — обов'язково, без нього LLM виклики падають
- `JWT_SECRET_KEY` — обов'язково, без нього токени скидаються при кожному рестарті

**Railway auto-detects:** `PORT` (сам інжектить), Python 3.11 (з `.python-version`)

**Start command:** `python run.py` (з `Procfile` і `railway.toml`)

**Health check:** `GET /health` → `{"status": "ok"}`

**Локально vs Railway:**
- Локально: `.env` файл з ключами
- Railway: Variables у dashboard (`.env` ніколи не комітимо)

## Development Rules
- Never commit `.env` or `openrouter_keys.txt`
- Tests live in `tests/` — run them after any change to game_modes/ or pipeline/
- Game logs in `logs/` — don't commit large jsonl files
- PROGRESS.md tracks current work status
- Communicate in Ukrainian only
