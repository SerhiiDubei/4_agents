"""
Backfill BIO.md for all agents that have CORE.json and SOUL.md.
Generates biography from CORE stats + SOUL text via LLM and overwrites BIO.md.

Usage:
  python scripts/backfill_bios.py
  python scripts/backfill_bios.py --dry-run
  python scripts/backfill_bios.py --agent agent_synth_d,agent_synth_g
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

BIO_SYSTEM = """Ти пишеш біографію персонажа українською.
На основі короткого опису особистості та числових характеристик створи цілісну біографію.
Пиши від третьої особи. Використовуй заголовки ## для розділів.

Обов'язкові розділи (усі мають бути присутні):
- ## Походження
- ## Дитинство та формування
- ## Соціальні патерни
- ## Внутрішній конфлікт
- ## Суперсила
- ## Страх

Стиль: конкретні факти, без поетики. Уникай епітетів і метафор («краса Карпат», «шум річок»). Пиши факти: місце народження, родина, професія, ключові події. 2–4 речення на розділ. Без технічних термінів (cooperation_bias тощо)."""


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


def generate_bio(name: str, soul_preview: str, core: dict, model: str) -> str:
    from pipeline.seed_generator import call_openrouter

    coop = core.get("cooperation_bias", 50)
    dec = core.get("deception_tendency", 50)
    horizon = core.get("strategic_horizon", 50)
    risk = core.get("risk_appetite", 50)

    user = f"""Ім'я персонажа: {name}

Опис особистості (SOUL):
{soul_preview}

Числові характеристики (не цитуй їх буквально, перетвори на характер):
- cooperation_bias: {coop} (0 = егоїст, 100 = альтруїст)
- deception_tendency: {dec} (0 = прямолінійний, 100 = схильний обманювати)
- strategic_horizon: {horizon} (0 = короткостроковий, 100 = думає наперед)
- risk_appetite: {risk} (0 = обережний, 100 = ризиковий)

Напиши біографію цього персонажа з обов'язковими розділами. Тільки текст біографії, без пояснень."""

    return call_openrouter(
        system_prompt=BIO_SYSTEM,
        user_prompt=user,
        model=model,
        temperature=0.7,
        max_tokens=1400,
        timeout=90,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill BIO.md from CORE.json + SOUL.md via LLM.")
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
        soul_preview = (soul_text[:800] + "…") if len(soul_text) > 800 else soul_text

        print(f"  {aid} ({name})…", flush=True)
        if args.dry_run:
            print(f"    [dry-run] would generate and write {bio_path}")
            continue

        try:
            bio_text = generate_bio(name, soul_preview, core, args.model)
            bio_path.write_text(bio_text, encoding="utf-8")
            print(f"    wrote BIO.md ({len(bio_text)} chars)")
        except Exception as e:
            print(f"    ERROR: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
