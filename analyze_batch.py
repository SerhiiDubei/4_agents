"""
analyze_batch.py — читає logs/batch_results.json і показує:
  1. Betray/coop rate per agent з personality params
  2. Кореляція deception_tendency → betray rate
  3. Чи спрацював T1.1 fix (диференціація за personality)

Usage:
    python analyze_batch.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "logs" / "batch_results.json"
AGENTS_DIR = ROOT / "agents"

BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def load_core(agent_id: str) -> dict:
    f = AGENTS_DIR / agent_id / "CORE.json"
    if f.exists():
        return json.loads(f.read_bytes())
    return {}


def main():
    if not RESULTS.exists():
        print(f"{RED}logs/batch_results.json не знайдено. Запусти run_batch_250.py спочатку.{RESET}")
        return

    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    agents = data.get("agents", {})
    games  = data.get("games", [])
    completed = data.get("completed", 0)
    failed    = data.get("failed", 0)

    if not agents:
        print(f"{RED}Немає даних агентів у results.{RESET}")
        return

    # Load roster for names
    roster_f = ROOT / "agents" / "roster.json"
    roster   = json.loads(roster_f.read_text()) if roster_f.exists() else {}
    name_map = {a["id"]: a.get("name", a["id"][-8:]) for a in roster.get("agents", [])}

    print(f"\n{BOLD}{'═'*72}{RESET}")
    print(f"{BOLD}{'ISLAND BATCH — АНАЛІЗ РЕЗУЛЬТАТІВ':^72}{RESET}")
    print(f"{BOLD}{f'{completed} ігор завершено  |  {failed} провалено':^72}{RESET}")
    print(f"{BOLD}{'═'*72}{RESET}\n")

    # ── Per-agent table ─────────────────────────────────────────────────────
    rows = []
    for aid, s in agents.items():
        g = s["games"]
        if g == 0:
            continue
        core = load_core(aid)
        dec  = core.get("deception_tendency", 50)
        coop_bias = core.get("cooperation_bias", 50)
        total_acts = s["cooperations"] + s["betrayals"]
        betray_pct = s["betrayals"]  / total_acts * 100 if total_acts > 0 else 0
        coop_pct   = s["cooperations"] / total_acts * 100 if total_acts > 0 else 0
        win_pct    = s["wins"] / g * 100
        avg_score  = s["total_score"] / g
        rows.append((aid, name_map.get(aid, aid[-8:]), g, dec, coop_bias,
                     betray_pct, coop_pct, win_pct, avg_score))

    # Sort by deception_tendency desc (high deception first)
    rows.sort(key=lambda r: r[3], reverse=True)

    print(f"  {BOLD}{'Агент':<18} {'dec':>4} {'coop':>5} {'Ігор':>5} "
          f"{'Зрад%':>6} {'Кооп%':>6} {'Win%':>5} {'Avg↑':>6}{RESET}")
    print(f"  {'─'*18} {'─'*4} {'─'*5} {'─'*5} {'─'*6} {'─'*6} {'─'*5} {'─'*6}")

    for aid, name, g, dec, coop_bias, bp, cp, wp, avg in rows:
        # Color: red = high betrayer, green = high cooperator
        bcolor = RED if bp > 45 else YELLOW if bp > 25 else GREEN
        ccolor = GREEN if cp > 55 else YELLOW if cp > 35 else RED
        wcolor = GREEN if wp > 20 else YELLOW if wp > 10 else DIM
        print(
            f"  {name:<18} {dec:>4} {coop_bias:>5} {g:>5} "
            f"{bcolor}{bp:>5.0f}%{RESET} {ccolor}{cp:>5.0f}%{RESET} "
            f"{wcolor}{wp:>4.0f}%{RESET} {avg:>6.1f}"
        )

    # ── Кореляція dec → betray ──────────────────────────────────────────────
    print(f"\n{BOLD}  КОРЕЛЯЦІЯ: deception_tendency → betray rate{RESET}")
    print(f"  {'─'*60}")

    high_dec = [(n, bp) for _, n, g, dec, _, bp, *_ in rows if dec >= 70 and g >= 2]
    low_dec  = [(n, bp) for _, n, g, dec, _, bp, *_ in rows if dec <= 30 and g >= 2]

    if high_dec:
        avg_betray_high = sum(bp for _, bp in high_dec) / len(high_dec)
        print(f"  {RED}Агенти з dec≥70{RESET}: {', '.join(n for n,_ in high_dec)}")
        print(f"    → Середній betray rate: {RED}{avg_betray_high:.0f}%{RESET}")

    if low_dec:
        avg_betray_low = sum(bp for _, bp in low_dec) / len(low_dec)
        print(f"  {GREEN}Агенти з dec≤30{RESET}: {', '.join(n for n,_ in low_dec)}")
        print(f"    → Середній betray rate: {GREEN}{avg_betray_low:.0f}%{RESET}")

    if high_dec and low_dec:
        diff = avg_betray_high - avg_betray_low
        verdict = f"{GREEN}T1.1 СПРАЦЮВАВ ✓{RESET}" if diff > 10 else f"{RED}РІЗНИЦЯ МАЛА — T1.1 потребує доопрацювання{RESET}"
        print(f"\n  Різниця: {diff:+.0f}% → {verdict}")

    # ── Coop bias кластери ──────────────────────────────────────────────────
    print(f"\n{BOLD}  КЛАСТЕРИ ЗА cooperation_bias{RESET}")
    print(f"  {'─'*60}")
    high_coop = [(n, cp) for _, n, g, _, cb, _, cp, *_ in rows if cb >= 65 and g >= 2]
    low_coop  = [(n, cp) for _, n, g, _, cb, _, cp, *_ in rows if cb <= 45 and g >= 2]

    if high_coop:
        avg_cp_high = sum(cp for _, cp in high_coop) / len(high_coop)
        print(f"  {GREEN}coop_bias≥65{RESET}: {', '.join(n for n,_ in high_coop)}")
        print(f"    → Середній coop rate: {GREEN}{avg_cp_high:.0f}%{RESET}")
    if low_coop:
        avg_cp_low = sum(cp for _, cp in low_coop) / len(low_coop)
        print(f"  {RED}coop_bias≤45{RESET}: {', '.join(n for n,_ in low_coop)}")
        print(f"    → Середній coop rate: {RED}{avg_cp_low:.0f}%{RESET}")

    # ── Winner stats ────────────────────────────────────────────────────────
    print(f"\n{BOLD}  ТОП-5 ПЕРЕМОЖЦІВ{RESET}")
    print(f"  {'─'*60}")
    top = sorted(rows, key=lambda r: r[7], reverse=True)[:5]
    for _, name, g, dec, cb, bp, cp, wp, avg in top:
        print(f"  {GREEN}{name:<18}{RESET} win={wp:.0f}%  betray={bp:.0f}%  coop={cp:.0f}%  dec={dec}  coop_bias={cb}")

    print(f"\n  {DIM}Детальні результати: logs/batch_results.json{RESET}")
    print(f"{BOLD}{'═'*72}{RESET}\n")


if __name__ == "__main__":
    main()
