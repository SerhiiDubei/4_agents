"""
MCS simulation runner — CLI entry point.

Usage:
    python -m simulation.mcs.runner --agents agent_synth_c agent_synth_d --ticks 5

Loads agents from roster.json, initialises NpcState for each,
runs N ticks and prints what happened at each step.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from simulation.mcs.state import NpcState
from simulation.mcs.tick_processor import TickProcessor
from simulation.mcs.world_engine import WorldConfig, WorldEngine

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcs.runner")

REPO_ROOT = Path(__file__).parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
ROSTER_PATH = AGENTS_DIR / "roster.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_roster() -> dict[str, dict]:
    """Return {agent_id: roster_entry} from roster.json."""
    if not ROSTER_PATH.exists():
        logger.warning("roster.json not found at %s", ROSTER_PATH)
        return {}
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data.get("agents", [])}


def _load_agent_state(agent_id: str) -> NpcState | None:
    """Build initial NpcState for one agent from SOUL.md + CORE.json."""
    agent_dir = AGENTS_DIR / agent_id
    core_path = agent_dir / "CORE.json"
    soul_path = agent_dir / "SOUL.md"

    if not core_path.exists():
        logger.warning("CORE.json missing for %s — skipping", agent_id)
        return None

    core = json.loads(core_path.read_text(encoding="utf-8"))
    soul_text = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

    return NpcState.from_soul_and_core(agent_id, soul_text, core)


def _format_tick_summary(agent_id: str, state: NpcState, tick: int) -> str:
    """Build a one-line summary for one agent at one tick."""
    dominant = state.personas.dominant()
    mood = state.mood
    last_event = state.recent_events[-1] if state.recent_events else "—"
    pending = ""
    if state.pending_action:
        action_data = state.pending_action
        if isinstance(action_data, dict):
            thought = action_data.get("thought", "")[:60]
            action = action_data.get("action", "")
            pending = f"  [LLM] думка: '{thought}...' дія: {action}"
        else:
            pending = f"  [LLM] {str(action_data)[:80]}"

    return (
        f"  Тік {tick:>3} | {state.agent_name:<18} | "
        f"персона={dominant:<10} | "
        f"енергія={mood.energy:.2f} страх={mood.fear:.2f} напруга={mood.tension:.2f} | "
        f"подія: {last_event}"
        f"{pending}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(agent_ids: list[str], n_ticks: int) -> None:
    """Run the MCS simulation for the given agents and number of ticks."""
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        print("[runner] OPENROUTER_API_KEY not set — Level 2 (LLM) ticks will be skipped.")
    else:
        print(f"[runner] OpenRouter key found — Level 2 ticks enabled (model: google/gemini-2.0-flash-001)")

    # Load states
    states: dict[str, NpcState] = {}
    for aid in agent_ids:
        state = _load_agent_state(aid)
        if state is not None:
            states[aid] = state
            print(f"[runner] Loaded agent: {state.agent_name} ({aid})")

    if not states:
        print("[runner] No agents loaded. Exiting.")
        return

    # Build world + processor
    config = WorldConfig(agents=list(states.keys()))
    engine = WorldEngine(config)
    processor = TickProcessor(llm_interval=10)

    print(f"\n[runner] Starting simulation: {len(states)} agents, {n_ticks} ticks\n")
    print("-" * 90)

    for tick in range(1, n_ticks + 1):
        states = engine.run_simulation_step(states, processor, AGENTS_DIR, openrouter_key)

        for aid, state in states.items():
            print(_format_tick_summary(aid, state, tick))

        print()

    print("-" * 90)
    print("[runner] Simulation complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="MCS simulation runner")
    parser.add_argument(
        "--agents",
        nargs="+",
        required=True,
        help="Agent IDs to simulate (e.g. agent_synth_c agent_synth_d)",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=5,
        help="Number of ticks to run (default: 5)",
    )
    args = parser.parse_args()
    run(args.agents, args.ticks)


if __name__ == "__main__":
    main()
