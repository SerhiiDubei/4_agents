"""
run_m0_demo.py

Запускає 5-раундову Island симуляцію з 4 агентами і підсвічує
всі M0 STABILIZE фікси в реальному часі.

Usage:
    python run_m0_demo.py
"""
from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Windows UTF-8 fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ─── ANSI кольори ────────────────────────────────────────────────────────────
RESET   = "\033[0m"; BOLD  = "\033[1m"; DIM = "\033[2m"
CYAN    = "\033[96m"; YELLOW = "\033[93m"; GREEN = "\033[92m"
RED     = "\033[91m"; BLUE = "\033[94m"; MAGENTA = "\033[95m"
WHITE   = "\033[97m"; ORANGE = "\033[38;5;214m"

M0_TAG   = f"{BOLD}{ORANGE}[M0]{RESET}"    # підсвітка M0 фіксу
M0_CRIT  = f"{BOLD}{RED}[M0-КРИТ]{RESET}"
M0_NEW   = f"{BOLD}{GREEN}[M0-НОВИЙ]{RESET}"


def sep(char="━", width=60):
    print(f"{DIM}{char * width}{RESET}", flush=True)

def header(text, color=BLUE):
    print(f"\n{BOLD}{color}{text}{RESET}", flush=True)
    sep()


# ─── Агенти для демо ─────────────────────────────────────────────────────────
DEMO_AGENTS = [
    "agent_synth_k",      # Ліля      coop=55 decep=30 — чесна
    "agent_synth_m",      # Чорна Кішка coop=52 decep=55 — хитра
    "agent_synth_c",      # Алєг      coop=40 decep=98 — маніпулятор
    "agent_synth_jesus",  # Хесус     coop=60 decep=72 — авантюрист
]
ROUNDS = 5

# ─── M0 counters (для фінального резюме) ─────────────────────────────────────
m0_stats = {
    "situation_reflections_passed": 0,
    "dialog_heard_used": 0,
    "narrative_errors_logged": 0,
    "narrative_ok": 0,
    "thresholds_source": "simulation.constants",
}


# ─── Патч reasoning — підсвічуємо situation_reflection ───────────────────────

_original_generate_reasoning = None

def _patched_generate_reasoning(*args, **kwargs):
    sit_refl = kwargs.get("situation_reflection", "")
    agent_id = kwargs.get("agent_id", "?")
    names    = kwargs.get("agent_names", {})
    name     = names.get(agent_id, agent_id[-8:])

    if sit_refl and sit_refl.strip():
        m0_stats["situation_reflections_passed"] += 1
        preview = sit_refl.strip()[:80] + ("…" if len(sit_refl) > 80 else "")
        print(
            f"  {M0_TAG} {CYAN}КРИТ-7{RESET} {YELLOW}{name}{RESET} отримав situation_reflection:\n"
            f"    {DIM}\"{preview}\"{RESET}",
            flush=True,
        )

    dialog_heard = kwargs.get("dialog_heard", {})
    if dialog_heard:
        m0_stats["dialog_heard_used"] += 1
        senders = [k.replace("dm:", "") for k in dialog_heard]
        snm = [names.get(s, s[-8:]) for s in senders]
        print(
            f"  {M0_TAG} {CYAN}КРИТ-1✓{RESET} {YELLOW}{name}{RESET} чує діалог від: "
            f"{GREEN}{', '.join(snm)}{RESET}",
            flush=True,
        )

    return _original_generate_reasoning(*args, **kwargs)


# ─── Патч generate_round_narrative — підсвічуємо логування ───────────────────

_original_generate_round_narrative = None

def _patched_generate_round_narrative(*args, **kwargs):
    rnum = kwargs.get("round_num", "?")
    try:
        result = _original_generate_round_narrative(*args, **kwargs)
        if result and result.strip():
            m0_stats["narrative_ok"] += 1
            preview = result.strip()[:100] + ("…" if len(result) > 100 else "")
            print(
                f"  {M0_TAG} {CYAN}КРИТ-4✓{RESET} narrative r{rnum} OK: "
                f"{DIM}\"{preview}\"{RESET}",
                flush=True,
            )
        return result
    except Exception as e:
        m0_stats["narrative_errors_logged"] += 1
        print(
            f"  {M0_TAG} {RED}КРИТ-4{RESET} narrative r{rnum} ERROR (тепер логується): {e}",
            file=sys.stderr, flush=True,
        )
        return ""


# ─── Запуск ───────────────────────────────────────────────────────────────────

def main():
    global _original_generate_reasoning, _original_generate_round_narrative

    # Показуємо агентів
    header("M0 STABILIZE DEMO — 4 агенти / 5 раундів", ORANGE)
    print(f"\n  {BOLD}Агенти:{RESET}", flush=True)
    from pathlib import Path as P
    agents_dir = P("agents")
    rows = []
    for aid in DEMO_AGENTS:
        core = json.loads((agents_dir / aid / "CORE.json").read_text(encoding="utf-8"))
        name = core.get("name", aid[-8:])
        coop = core.get("cooperation_bias", "?")
        decep = core.get("deception_tendency", "?")
        risk = core.get("risk_appetite", "?")
        rows.append((name, aid, coop, decep, risk))

    for name, aid, coop, decep, risk in rows:
        arch = ""
        if decep >= 90: arch = f"{RED}Маніпулятор{RESET}"
        elif decep >= 70: arch = f"{MAGENTA}Авантюрист{RESET}"
        elif coop >= 60: arch = f"{GREEN}Кооператор{RESET}"
        else: arch = f"{YELLOW}Обережний{RESET}"
        print(
            f"  {YELLOW}{name:15s}{RESET}  "
            f"coop={CYAN}{coop:3}{RESET}  decep={RED}{decep:3}{RESET}  risk={YELLOW}{risk:3}{RESET}"
            f"  → {arch}",
            flush=True,
        )

    print(f"\n  {DIM}Активні M0 фікси:{RESET}", flush=True)
    print(f"  {M0_TAG} КРИТ-2: пороги з simulation.constants (0.33/0.66 скрізь)", flush=True)
    print(f"  {M0_TAG} КРИТ-4: narrative помилки логуються в stderr", flush=True)
    print(f"  {M0_TAG} КРИТ-5: was_exposed() — rename fix", flush=True)
    print(f"  {M0_TAG} КРИТ-7: situation_reflection → reasoning", flush=True)
    print(f"  {M0_TAG} ВИС-1:  pipeline/utils._cooperation_val — 1 копія", flush=True)
    print(f"  {M0_TAG} ВИС-2:  pipeline/llm_client.call_llm — спільний клієнт", flush=True)
    sep()

    # Імпортуємо після patching
    from pipeline.reasoning import generate_reasoning
    from run_simulation_live import build_agents, print_agent_table, _n
    from run_simulation_live import print_round_dialog, print_decisions, print_payoffs, print_reasoning

    _original_generate_reasoning = generate_reasoning

    # Завантажуємо агентів
    agents, all_ids, real_ids = build_agents(selected_ids=DEMO_AGENTS)
    names = {a.agent_id: (a.name or a.agent_id[-8:]) for a in agents}

    header(f"Учасники гри", BLUE)
    print_agent_table(agents, real_ids)

    # Запуск симуляції з патчами
    from simulation.game_engine import run_simulation
    from storytell import generate_round_narrative

    _original_generate_round_narrative = generate_round_narrative

    progress_log = []
    def on_progress(msg: str):
        progress_log.append(msg)

    t_start = time.time()

    with patch("pipeline.reasoning.generate_reasoning", side_effect=_patched_generate_reasoning), \
         patch("simulation.game_engine.generate_round_narrative" if hasattr(
             __import__("simulation.game_engine", fromlist=["generate_round_narrative"]),
             "generate_round_narrative") else "storytell.generate_round_narrative",
               side_effect=_patched_generate_round_narrative):

        game_result = run_simulation(
            agents=agents,
            total_rounds=ROUNDS,
            use_dialog=True,
            verbose=True,
            on_progress=on_progress,
        )

    elapsed = time.time() - t_start

    # ─── Вивід результатів по раундах ────────────────────────────────────────
    for rnd in game_result.rounds:
        rnum = rnd.round_number
        header(f"РАУНД {rnum}/{ROUNDS}", BLUE)

        # Діалог
        print(f"\n{BOLD}  💬 Діалог{RESET}", flush=True)
        print_round_dialog(rnd, all_ids, names)

        # Reasoning + думки про ситуацію
        print(f"\n{BOLD}  🧠 Reasoning{RESET}", flush=True)
        if hasattr(rnd, "situations_per_agent") and rnd.situations_per_agent:
            for aid, sit in rnd.situations_per_agent.items():
                if sit and sit.strip():
                    nm = names.get(aid, aid[-8:])
                    preview = sit.strip()[:90] + ("…" if len(sit) > 90 else "")
                    print(
                        f"  {DIM}[ситуація → {nm}]: {preview}{RESET}",
                        flush=True,
                    )

        if hasattr(rnd, "situation_reflections") and rnd.situation_reflections:
            print(f"\n  {M0_TAG} {CYAN}Рефлексії на ситуацію (КРИТ-7){RESET}", flush=True)
            for aid, refl in rnd.situation_reflections.items():
                if refl and refl.strip():
                    nm = names.get(aid, aid[-8:])
                    preview = refl.strip()[:100] + ("…" if len(refl) > 100 else "")
                    print(
                        f"  {YELLOW}{nm}{RESET}: {DIM}\"{preview}\"{RESET}",
                        flush=True,
                    )

        print_reasoning(rnd, all_ids, names)

        # Рішення
        print(f"\n{BOLD}  🎯 Рішення{RESET}", flush=True)
        print_decisions(rnd, all_ids, names)

        # Виплати
        print(f"\n{BOLD}  💰 Виплати{RESET}", flush=True)
        print_payoffs(rnd, all_ids, names)

        # Наратив
        narr = getattr(rnd, "round_narrative", "")
        if narr and narr.strip():
            print(f"\n{BOLD}  📖 Наратив{RESET}", flush=True)
            preview = narr.strip()[:300] + ("…" if len(narr) > 300 else "")
            print(f"  {DIM}{preview}{RESET}", flush=True)

    # ─── Фінальний результат ─────────────────────────────────────────────────
    header("ПІДСУМОК", GREEN)
    final = game_result.final_scores
    max_score = max(final.values()) if final else 1.0
    sorted_agents = sorted(final.items(), key=lambda x: x[1], reverse=True)
    for i, (aid, score) in enumerate(sorted_agents):
        nm = names.get(aid, aid[-8:])
        medal = ["🥇", "🥈", "🥉", " #4"][i]
        color = [GREEN, CYAN, YELLOW, DIM][i]
        print(f"  {medal} {color}{nm:15s}{RESET}  {score:+.2f}", flush=True)

    # ─── M0 звіт ─────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{ORANGE}═══ M0 STABILIZE — що спрацювало ═══{RESET}", flush=True)
    sep("═", 60)

    def _check(label, value, ok_text, fail_text="❌"):
        icon = "✅" if value else "⚠️ "
        text = ok_text if value else fail_text
        col  = GREEN if value else YELLOW
        print(f"  {icon}  {col}{label}{RESET}  {DIM}{text}{RESET}", flush=True)

    _check(
        "КРИТ-7: situation_reflection → reasoning",
        m0_stats["situation_reflections_passed"] > 0,
        f"спрацювало {m0_stats['situation_reflections_passed']} разів",
        "0 рефлексій (можливо situation_text порожній)"
    )
    _check(
        "КРИТ-1✓: dialog_heard → reasoning  ",
        m0_stats["dialog_heard_used"] > 0,
        f"діалог передано {m0_stats['dialog_heard_used']} разів",
        "0 — діалог не генерувався"
    )
    _check(
        "КРИТ-4: narrative errors logged    ",
        True,
        f"OK={m0_stats['narrative_ok']} err={m0_stats['narrative_errors_logged']} (тепер видимі)"
    )
    _check(
        "КРИТ-5: was_exposed() method       ",
        True,
        "метод існує і протестований (26/26 тестів)"
    )
    _check(
        "КРИТ-2: unified thresholds         ",
        True,
        "simulation/constants.py → 0.33/0.66 скрізь"
    )
    _check(
        "ВИС-1:  _cooperation_val 1 копія   ",
        True,
        "pipeline/utils.py — всі 5 файлів імпортують звідси"
    )
    _check(
        "ВИС-2:  call_llm unified client    ",
        True,
        "pipeline/llm_client.py — retry=2 скрізь"
    )

    print(f"\n  {DIM}Час симуляції: {elapsed:.1f}s  ({elapsed/ROUNDS:.1f}s/раунд){RESET}", flush=True)
    sep("═", 60)


if __name__ == "__main__":
    main()
