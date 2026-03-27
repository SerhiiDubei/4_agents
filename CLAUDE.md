# 4 AGENTS — Project Context

## What This Is
Multi-agent social simulation platform. Two game modes:
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
frontend/             — React/TS agent initialization UI
```

## Critical Known Issues (as of 2026-03-21)

1. **Agents always cooperate, never steal** — `decision_engine.py::_action_scores()` strategic_horizon penalty keeps agents at 0.66 regardless of role
2. **Dialog → Action loop broken** — `last_messages` not passed from loop.py to action decision → communication is decorative
3. **SOUL.md not in decision prompts** — agent_context.build_context() doesn't inject personality → agents decide without identity
4. **storytell/ decoupled from TIME WARS** — round_narrative.py exists but never called in loop.py

## Agent Identity Files
- `SOUL.md` — Narrative identity (8 sections, 2nd person Ukrainian)
- `CORE.json` — Personality params 0-100: cooperation_bias, deception_tendency, strategic_horizon, risk_appetite
- `ROLE_CORE_OVERLAYS` in `agent_context.py` — Role-based modifications to CORE params applied at runtime
- `roles.json` — Role definitions: role_snake, role_gambler, role_banker, role_peacekeeper

## Important File Locations
- Game logs: `logs/time_wars_*.jsonl` + `logs/time_wars_*.html`
- Agent configs: `agents/{agent_id}/`
- Roster: `agents/roster.json`
- Role definitions: `game_modes/time_wars/roles.json`
- Code cards: `game_modes/time_wars/codes.json`
- Game constants: `game_modes/time_wars/constants.py`

## Tech Stack
- Backend: Python, FastAPI, SQLAlchemy
- Frontend: React, TypeScript, Vite
- LLM calls: OpenRouter (see `.env` for keys)
- DB: SQLite (`timewars.db`)

## Development Rules
- Never commit `.env` or `openrouter_keys.txt`
- Tests live in `tests/` — run them after any change to game_modes/ or pipeline/
- Game logs in `logs/` — don't commit large jsonl files
- PROGRESS.md tracks current work status
