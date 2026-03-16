"""
Create real agent folders for all synthetic agents: CORE.json, SOUL.md, STATES.md, MEMORY.json, BIO.md.
Updates roster.json so these agents are type "real" and are loaded from disk.

Usage:
  python create_real_agent_folders.py
  python create_real_agent_folders.py --refresh-states   # regenerate STATES.md from CORE for all agents

Does not overwrite existing files (except roster.json is updated with new agents; STATES.md if --refresh-states).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

AGENTS_DIR = ROOT / "agents"
BIO_PLACEHOLDER = """# Біографія

Тут можна додати біографію персонажа. Текст буде використовуватись у симуляції (контекст для діалогів та ситуацій).
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create real agent folders with CORE, SOUL, STATES, MEMORY, BIO.")
    parser.add_argument("--refresh-states", action="store_true", help="Regenerate STATES.md from CORE for all agents with CORE.json")
    args = parser.parse_args()

    from run_simulation_live import SYNTH_AGENT_CONFIGS
    from pipeline.state_machine import initial_state_from_core, save_states
    from pipeline.memory import AgentMemory, save_memory

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    all_ids = list(SYNTH_AGENT_CONFIGS.keys())

    for agent_id, cfg in SYNTH_AGENT_CONFIGS.items():
        agent_dir = AGENTS_DIR / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # CORE.json
        core_path = agent_dir / "CORE.json"
        if not core_path.exists():
            core = dict(cfg["core"])
            core["version"] = "1.0.0"
            core["name"] = cfg.get("name", agent_id)
            core.setdefault("point_buy", {"budget": 100, "spent": 0, "refund": 0, "notes": ""})
            core.setdefault("meta", {"agent_id": agent_id})
            core.setdefault("trait_log", [])
            core_path.write_text(
                json.dumps(core, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  {agent_id}: CORE.json")
        else:
            print(f"  {agent_id}: CORE.json (skip)")

        # SOUL.md
        soul_path = agent_dir / "SOUL.md"
        if not soul_path.exists():
            soul_path.write_text(cfg["soul_md"].strip(), encoding="utf-8")
            print(f"  {agent_id}: SOUL.md")
        else:
            print(f"  {agent_id}: SOUL.md (skip)")

        # STATES.md — initial state derived from CORE (different per agent)
        peers = [x for x in all_ids if x != agent_id]
        if not (agent_dir / "STATES.md").exists():
            state = initial_state_from_core(agent_id, cfg["core"], peers)
            save_states(state, agent_dir, display_name=cfg.get("name", agent_id))
            print(f"  {agent_id}: STATES.md")
        else:
            print(f"  {agent_id}: STATES.md (skip)")

        # MEMORY.json
        if not (agent_dir / "MEMORY.json").exists():
            memory = AgentMemory(agent_id=agent_id)
            save_memory(memory, agent_dir)
            print(f"  {agent_id}: MEMORY.json")
        else:
            print(f"  {agent_id}: MEMORY.json (skip)")

        # BIO.md — placeholder for biography
        bio_path = agent_dir / "BIO.md"
        if not bio_path.exists():
            bio_path.write_text(BIO_PLACEHOLDER.strip(), encoding="utf-8")
            print(f"  {agent_id}: BIO.md")
        else:
            print(f"  {agent_id}: BIO.md (skip)")

    # roster.json
    roster_path = AGENTS_DIR / "roster.json"
    roster = {
        "version": "1.0",
        "description": "Реєстр персонажів.",
        "agents": [],
        "default_count": 4,
        "min_participants": 2,
        "max_participants": 8,
    }
    if roster_path.exists():
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster.setdefault("agents", [])

    existing_ids = {a["id"] for a in roster["agents"]}
    added = 0
    for agent_id, cfg in SYNTH_AGENT_CONFIGS.items():
        if agent_id in existing_ids:
            # Ensure type is real and source is correct
            for a in roster["agents"]:
                if a["id"] == agent_id:
                    a["type"] = "real"
                    a["source"] = f"agents/{agent_id}"
                    a["name"] = cfg.get("name", agent_id)
                    a.setdefault("profile", {"connections": "", "profession": "", "bio": ""})
                    break
            continue
        roster["agents"].append({
            "id": agent_id,
            "name": cfg.get("name", agent_id),
            "type": "real",
            "source": f"agents/{agent_id}",
            "profile": {"connections": "", "profession": "", "bio": ""},
        })
        added += 1

    roster_path.write_text(json.dumps(roster, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nroster.json: {len(roster['agents'])} agents ({added} added)")

    # Add BIO.md to any existing agent folder that has CORE but no BIO
    for child in AGENTS_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "CORE.json").exists() and not (child / "BIO.md").exists():
            (child / "BIO.md").write_text(BIO_PLACEHOLDER.strip(), encoding="utf-8")
            print(f"  {child.name}: BIO.md (added)")

    # --refresh-states: regenerate STATES.md from CORE for every agent that has CORE.json
    if args.refresh_states:
        all_with_core = [
            d.name for d in AGENTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".") and (d / "CORE.json").exists()
        ]
        for agent_id in sorted(all_with_core):
            agent_dir = AGENTS_DIR / agent_id
            core = json.loads((agent_dir / "CORE.json").read_text(encoding="utf-8"))
            peers = [p for p in all_with_core if p != agent_id]
            state = initial_state_from_core(agent_id, core, peers)
            display_name = core.get("name", agent_id)
            save_states(state, agent_dir, display_name=display_name)
            print(f"  {agent_id}: STATES.md (refreshed)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
