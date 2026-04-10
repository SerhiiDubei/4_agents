"""
run_emulation_html.py

Запускає одну емуляцію гри (без LLM), будує лог і експортує його в HTML.
Не потребує OPENROUTER_API_KEY чи agents/roster — тільки генерація фіктивного логу.

Usage:
    python run_emulation_html.py [--rounds N] [--out path.html]
"""

from __future__ import annotations

import argparse
import random
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Учасники як останній раз (8 осіб)
DEFAULT_AGENT_NAMES_8 = [
    "Павло", "Вова", "Ліля", "Вождь", "Марта", "Артурчик", "Чорна Кішка", "Роман Романюк",
]
DEFAULT_AGENT_NAMES_4 = ["Кира", "Надя", "Марко", "Олег"]


def _action_label(val: float) -> str:
    if val <= 0.15:
        return "betray"
    if val <= 0.45:
        return "soft-D"
    if val <= 0.75:
        return "soft-C"
    return "coop"


def build_emulation_log(n_rounds: int = 3, n_agents: int = 4, agent_names: list[str] | None = None) -> dict:
    """Побудувати фіктивний лог гри для експорту в HTML."""
    agent_ids = [f"agent_em_{uuid.uuid4().hex[:8]}" for _ in range(n_agents)]
    if agent_names is not None and len(agent_names) >= n_agents:
        name_list = agent_names[:n_agents]
    elif n_agents == 8:
        name_list = DEFAULT_AGENT_NAMES_8
    else:
        name_list = (DEFAULT_AGENT_NAMES_4 + [f"Агент_{i+1}" for i in range(4, n_agents)])[:n_agents]
    names = {aid: name_list[i] for i, aid in enumerate(agent_ids)}

    rounds = []
    cumulative: dict[str, float] = {a: 0.0 for a in agent_ids}

    for rnum in range(1, n_rounds + 1):
        # Actions: each agent -> each other (0..1)
        actions = {}
        for aid in agent_ids:
            actions[aid] = {
                other: round(random.uniform(0.2, 0.95), 2)
                for other in agent_ids
                if other != aid
            }

        # Simple payoff: sum of (action toward me + my action toward them) / 2 style
        payoffs_per_agent = {}
        for aid in agent_ids:
            total = 0.0
            for other in agent_ids:
                if other == aid:
                    continue
                my_act = actions[aid].get(other, 0.5)
                their_act = actions[other].get(aid, 0.5)
                # Coop gives small positive, defect gives mixed
                total += (my_act + their_act) * 2.0 - 1.5
            payoffs_per_agent[aid] = round(total, 3)
            cumulative[aid] = round(cumulative[aid] + total, 2)

        payoffs_block = {
            "round": rnum,
            "payoffs": payoffs_per_agent,
            "total": payoffs_per_agent,
            "pair_outcomes": [],
        }

        messages = []
        for aid in agent_ids:
            name = names[aid]
            msgs = [
                f"Я пропоную діяти разом у цьому раунді.",
                f"Обережно — хтось може зрадити.",
                f"Давайте довіримося один одному.",
            ]
            messages.append({
                "sender": aid,
                "text": random.choice(msgs),
                "channel": "public",
            })

        round_data = {
            "round": rnum,
            "situation": (
                f"Раунд {rnum}. Усі {n_agents} на місці. Потрібно вирішити, кому довіритися, а від кого стерегтися."
            ),
            "dialog": {"messages": messages},
            "actions": actions,
            "payoffs": payoffs_block,
            "round_narrative": (
                f"Раунд {rnum}. Агенти обмінялися думками. "
                "Деякі вирішили підтримати інших, деякі діяли обережно."
            ),
            "situation_reflections": {
                aid: f"Я оцінюю ситуацію як {'напружену' if rnum == 1 else 'розвивається'}."
                for aid in agent_ids
            },
            "notes": {
                aid: f"Після раунду {rnum}: я бачу зміни в поведінці."
                for aid in agent_ids
            },
            "reasonings": {
                aid: {
                    "thought": f"Вирішую чи кооперувати з іншими у раунді {rnum}.",
                    "intents": actions.get(aid, {}),
                }
                for aid in agent_ids
            },
        }
        rounds.append(round_data)

    winner_id = max(cumulative, key=cumulative.get)
    sim_id = f"emulation_{uuid.uuid4().hex[:12]}"

    log = {
        "simulation_id": sim_id,
        "agents": agent_ids,
        "agent_names": names,
        "total_rounds": n_rounds,
        "final_scores": dict(cumulative),
        "winner": winner_id,
        "rounds": rounds,
        "score_range": {
            "n_rounds": n_rounds,
            "n_agents": n_agents,
            "max_possible": 50.0,
            "min_possible": -50.0,
            "mutual_coop_score": 25.0,
            "mutual_defect_score": -25.0,
        },
        "agent_reflections": {
            aid: [{"round": r["round"], "notes": r["notes"].get(aid, "")} for r in rounds if r["notes"].get(aid)]
            for aid in agent_ids
        },
        "agent_reasonings": {
            aid: [
                {"round": r["round"], "reasoning": r["reasonings"].get(aid, {})}
                for r in rounds
            ]
            for aid in agent_ids
        },
        "game_conclusions": {
            aid: "Емуляція завершена. Це була тестова партія без реальних LLM-викликів."
            for aid in agent_ids
        },
        "story_params": {
            "year": "1943",
            "place": "острів у Тихому океані",
            "setup": "Корабель потонув. Чотири персонажі на березі.",
        },
    }
    return log


def main():
    ap = argparse.ArgumentParser(description="Emit one emulation and export HTML.")
    ap.add_argument("--rounds", type=int, default=3, help="Number of rounds")
    ap.add_argument("--agents", type=int, default=8, help="Number of agents (default: 8, same participants as last run)")
    ap.add_argument("--out", type=str, default="", help="Output HTML path (default: logs/emulation_<timestamp>.html)")
    args = ap.parse_args()

    log = build_emulation_log(n_rounds=args.rounds, n_agents=args.agents)

    sys_path = str(ROOT)
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    from export_game_log import export_to_html

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    if args.out:
        out_path = Path(args.out)
    else:
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = logs_dir / f"emulation_{ts}.html"

    export_to_html(log, output_path=out_path)
    print(f"Emulation: {log['simulation_id']}")
    print(f"Rounds: {args.rounds}, Agents: {len(log['agents'])}")
    print(f"HTML: {out_path.resolve()}")
    return out_path


if __name__ == "__main__":
    main()
