"""
Expand SOUL.md for each agent: generate full SOUL with 8 required sections
(Identity, How You See Others, What You Never Say Out Loud, What Makes You Feel Safe,
Under Pressure, Decision Instinct, Voice, Body Language) from current SOUL + CORE + optional BIO.
Overwrites SOUL.md. Does not change soul_compiler or template.

Usage:
  python scripts/expand_souls.py
  python scripts/expand_souls.py --dry-run
  python scripts/expand_souls.py --agent agent_synth_d,agent_synth_g
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AGENTS_DIR = ROOT / "agents"
DEFAULT_MODEL = "google/gemini-2.0-flash-001"

REQUIRED_SECTIONS = [
    "## Identity",
    "## How You See Others",
    "## What You Never Say Out Loud",
    "## What Makes You Feel Safe",
    "## Under Pressure",
    "## Decision Instinct",
    "## Voice",
    "## Body Language",
]

SOUL_SYSTEM = """You write a SOUL.md file for an AI agent. It defines personality in second person ("You..." / "Ти...").
Section headers must be in English (copy exactly). All section BODY text must be in Ukrainian.

You MUST include exactly these 8 section headers:
## Identity
## How You See Others
## What You Never Say Out Loud
## What Makes You Feel Safe
## Under Pressure
## Decision Instinct
## Voice
## Body Language

Under each header write 2-4 short sentences in second person, in Ukrainian. Be specific and behavioral, not abstract.
Describe concrete behavior, not abstract values: e.g. "Ти шукаєш, в чому людина сильна, навіть коли вона сама не бачить" not "Ти віриш у потенціал людей"; "Ти автоматично ділиш порівну; якщо візьмеш більше — тілу незручно" not "Ти цінуєш справедливість".
Voice = how they speak (rhythm, tone, typical phrases). Body Language = gestures, posture, facial expressions (for UI/avatar).
No trait labels like "smart" or "cold" — show behavior. Tone: grounded, slightly understated.
If the input already has good content for a section, expand or refine it; do not drop it."""


def load_env_openrouter(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if k == "OPENROUTER_API_KEY" and v:
                os.environ["OPENROUTER_API_KEY"] = v
                break


def generate_expanded_soul(name: str, soul_text: str, core: dict, bio_text: str | None, model: str) -> str:
    from pipeline.seed_generator import call_openrouter

    soul_preview = (soul_text[:1200] + "…") if len(soul_text) > 1200 else soul_text
    bio_preview = ""
    if bio_text and bio_text.strip():
        bio_preview = (bio_text.strip()[:600] + "…") if len(bio_text.strip()) > 600 else bio_text.strip()

    user_parts = [
        f"Agent name: {name}",
        "",
        "Current SOUL (may be one paragraph or already with sections):",
        soul_preview,
    ]
    if bio_preview:
        user_parts.extend(["", "Biography (for context):", bio_preview])
    user_parts.extend([
        "",
        "Core stats (for tone only, do not cite): cooperation_bias=%s, deception_tendency=%s, strategic_horizon=%s, risk_appetite=%s"
        % (core.get("cooperation_bias", 50), core.get("deception_tendency", 50),
           core.get("strategic_horizon", 50), core.get("risk_appetite", 50)),
        "",
        "Output the full SOUL.md with all 8 sections (Identity, How You See Others, What You Never Say Out Loud, What Makes You Feel Safe, Under Pressure, Decision Instinct, Voice, Body Language). Use the exact headers. Body text in Ukrainian. Only the SOUL text, no explanation.",
    ])
    user = "\n".join(user_parts)

    return call_openrouter(
        system_prompt=SOUL_SYSTEM,
        user_prompt=user,
        model=model,
        temperature=0.6,
        max_tokens=1800,
        timeout=90,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand SOUL.md with 8 sections from CORE + SOUL + optional BIO.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, do not write files.")
    parser.add_argument("--agent", type=str, default="", help="Comma-separated agent IDs to process (default: all).")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="OpenRouter model for generation.")
    args = parser.parse_args()

    load_env_openrouter(ROOT)

    if not AGENTS_DIR.exists():
        print("agents/ not found.", file=sys.stderr)
        return 1

    agent_ids = None
    if args.agent:
        agent_ids = [x.strip() for x in args.agent.split(",") if x.strip()]

    candidates = []
    for path in sorted(AGENTS_DIR.iterdir()):
        if not path.is_dir():
            continue
        aid = path.name
        if agent_ids is not None and aid not in agent_ids:
            continue
        core_path = path / "CORE.json"
        soul_path = path / "SOUL.md"
        if not core_path.exists() or not soul_path.exists():
            continue
        candidates.append((aid, path))

    if not candidates:
        print("No agents with both CORE.json and SOUL.md found.", file=sys.stderr)
        return 0

    for aid, agent_dir in candidates:
        core_path = agent_dir / "CORE.json"
        soul_path = agent_dir / "SOUL.md"
        bio_path = agent_dir / "BIO.md"

        core = json.loads(core_path.read_text(encoding="utf-8"))
        soul_text = soul_path.read_text(encoding="utf-8").strip()
        name = core.get("name", aid)
        bio_text = bio_path.read_text(encoding="utf-8").strip() if bio_path.exists() else None
        if bio_text and bio_text.startswith("# Біографія") and len(bio_text) < 200:
            bio_text = None  # skip placeholder

        print(f"  {aid} ({name})…", flush=True)
        if args.dry_run:
            print(f"    [dry-run] would generate and write {agent_dir / 'SOUL.md'}")
            continue

        try:
            out = generate_expanded_soul(name, soul_text, core, bio_text, args.model)
            # Ensure all required section headers exist (LLM might use different wording)
            for sec in REQUIRED_SECTIONS:
                if sec not in out:
                    print(f"    WARNING: missing '{sec}' in output, appending placeholder", file=sys.stderr)
                    out += f"\n\n{sec}\n(To be filled.)"
            if "You" not in out and "Ти" not in out:
                out += "\n\nТи дієш відповідно до свого характеру."
            soul_path.write_text(out, encoding="utf-8")
            print(f"    wrote SOUL.md ({len(out)} chars)")
        except Exception as e:
            print(f"    ERROR: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
