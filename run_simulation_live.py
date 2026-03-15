"""
run_simulation_live.py

Live simulation runner for Island — runs the full game loop with real Grok LLM
and prints a formatted live log to the terminal.

Uses:
  - 2 real agents from disk (agents/ directory)
  - 2 synthetic agents (created in memory)

Usage:
    python3 run_simulation_live.py             # 3 rounds (default)
    python3 run_simulation_live.py --rounds 1  # quick single round
    python3 run_simulation_live.py --rounds 5  # full game
"""

import argparse
import sys
import time
import random
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
BLUE   = "\033[94m"
MAGENTA = "\033[95m"
WHITE  = "\033[97m"


def bar(value: float, width: int = 12) -> str:
    filled = round(max(0.0, min(1.0, value)) * width)
    return "█" * filled + "░" * (width - filled)


def mood_color(mood: str) -> str:
    colors = {
        "dominant":  GREEN,
        "confident": GREEN,
        "calm":      CYAN,
        "neutral":   WHITE,
        "uncertain": YELLOW,
        "fearful":   YELLOW,
        "hostile":   RED,
        "paranoid":  RED,
    }
    return colors.get(mood, WHITE)


def action_label(val: float) -> str:
    if val <= 0.1:   return f"{RED}full_defect{RESET}"
    if val <= 0.4:   return f"{YELLOW}soft_defect{RESET}"
    if val <= 0.75:  return f"{CYAN}cond_cooperate{RESET}"
    return f"{GREEN}full_cooperate{RESET}"


def tone_color(tone: str) -> str:
    return {
        "cooperative": GREEN,
        "neutral":     WHITE,
        "threatening": RED,
        "deceptive":   MAGENTA,
    }.get(tone, WHITE)


def sep(char="━", width=54):
    print(f"{DIM}{char * width}{RESET}", flush=True)


def header(text: str, width=54):
    print(f"\n{BOLD}{BLUE}{text}{RESET}", flush=True)
    sep()


# ---------------------------------------------------------------------------
# Build agents: 2 real from disk + 2 synthetic
# ---------------------------------------------------------------------------

def build_agents():
    from pipeline.state_machine import AgentState, initialize_states
    from pipeline.memory import AgentMemory, initialize_memory
    from simulation.game_engine import SimAgent, load_agents_from_disk, AGENTS_DIR

    # Real agents from disk
    real_ids = ["agent_3165685c", "agent_511a6f9e"]
    real_agents = load_agents_from_disk(real_ids)

    # Two synthetic agents with distinct personalities
    synth_configs = [
        {
            "agent_id": "agent_synth_c",
            "soul_md": "You are impulsive and confrontational. You speak before thinking and escalate tensions quickly. You trust no one but pretend otherwise.",
            "core": {
                "cooperation_bias": 25,
                "deception_tendency": 72,
                "strategic_horizon": 30,
                "risk_appetite": 85,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        {
            "agent_id": "agent_synth_d",
            "soul_md": "You are calm and diplomatic. You prefer long-term alliances and genuine cooperation. You read people well and rarely show your hand.",
            "core": {
                "cooperation_bias": 78,
                "deception_tendency": 20,
                "strategic_horizon": 90,
                "risk_appetite": 35,
                "model": "google/gemini-2.0-flash-001",
            },
        },
    ]

    all_ids = real_ids + ["agent_synth_c", "agent_synth_d"]

    synth_agents = []
    for cfg in synth_configs:
        aid = cfg["agent_id"]
        peers = [x for x in all_ids if x != aid]
        state = AgentState(
            agent_id=aid,
            tension=0.2 + random.random() * 0.2,
            fear=0.1,
            dominance=0.4 + random.random() * 0.2,
            anger=0.05,
            interest=0.5,
            talk_cooldown=0,
            trust={p: 0.5 for p in peers},
            mood="neutral",
            round_number=0,
        )
        synth_agents.append(SimAgent(
            agent_id=aid,
            soul_md=cfg["soul_md"],
            core=cfg["core"],
            states=state,
            memory=AgentMemory(agent_id=aid),
        ))

    # Re-init real agent trust to include synth peers
    for agent in real_agents:
        peers = [x for x in all_ids if x != agent.agent_id]
        for p in peers:
            if p not in agent.states.trust:
                agent.states.trust[p] = 0.5

    return real_agents + synth_agents, all_ids


# ---------------------------------------------------------------------------
# Live log helpers
# ---------------------------------------------------------------------------

def print_agent_table(agents):
    print()
    print(f"  {'Agent':20s}  {'coop':6s}  {'deception':10s}  {'horizon':8s}  {'mood':12s}  {'type':10s}")
    print(f"  {'-'*20}  {'-'*6}  {'-'*10}  {'-'*8}  {'-'*12}  {'-'*10}")
    real_ids = {"agent_3165685c", "agent_511a6f9e"}
    for a in agents:
        tag = "real" if a.agent_id in real_ids else f"{DIM}synthetic{RESET}"
        mc = mood_color(a.states.mood)
        print(
            f"  {a.agent_id:20s}  "
            f"{a.core.get('cooperation_bias', '?'):6}  "
            f"{a.core.get('deception_tendency', '?'):10}  "
            f"{a.core.get('strategic_horizon', '?'):8}  "
            f"{mc}{a.states.mood:12s}{RESET}  "
            f"{tag}",
            flush=True,
        )
    print()


def print_round_dialog(round_result, agent_ids):
    dialog = round_result.dialog
    if not dialog or not dialog.messages:
        print(f"  {DIM}(no dialog this round){RESET}", flush=True)
        return

    pub = [m for m in dialog.messages if m.channel == "public"]
    dms = [m for m in dialog.messages if m.channel.startswith("dm_")]
    signals = dialog.talk_signals if hasattr(dialog, "talk_signals") else {}

    for i, msg in enumerate(pub):
        step_label = f"[step {i+1}]"
        print(f"\n  {BOLD}{CYAN}{step_label}{RESET}  {YELLOW}{msg.sender_id}{RESET}:", flush=True)
        # Wrap text
        text = msg.text.strip()
        for line in _wrap(f'"{text}"', 60, "    "):
            print(line, flush=True)
        # Signals
        if signals:
            sig_out = []
            for lid, sig in signals.items():
                if lid != msg.sender_id:
                    col = tone_color(sig)
                    sig_out.append(f"{lid[-8:]}: {col}{sig}{RESET}")
            if sig_out:
                print(f"    {DIM}→ signals: {', '.join(sig_out)}{RESET}", flush=True)

    if dms:
        print(flush=True)
        for dm in dms:
            target = dm.channel.replace("dm_", "")
            print(f"  {MAGENTA}[DM]{RESET}  {YELLOW}{dm.sender_id}{RESET} → {YELLOW}{target}{RESET}:", flush=True)
            for line in _wrap(f'"{dm.text.strip()}"', 60, "    "):
                print(line, flush=True)


def _wrap(text: str, width: int, indent: str) -> list:
    """Simple word wrap."""
    words = text.split()
    lines = []
    current = indent
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = indent + w
        else:
            current = current + (" " if current != indent else "") + w
    if current.strip():
        lines.append(current)
    return lines or [indent]


def print_decisions(round_result, agent_ids):
    actions = round_result.actions
    print(flush=True)
    for src_id in agent_ids:
        src_acts = actions.get(src_id, {})
        for tgt_id, val in sorted(src_acts.items()):
            label = action_label(val)
            src_short = src_id[-8:] if len(src_id) > 8 else src_id
            tgt_short = tgt_id[-8:] if len(tgt_id) > 8 else tgt_id
            print(
                f"  {YELLOW}{src_short:12s}{RESET} → {YELLOW}{tgt_short:12s}{RESET}  "
                f"{val:.2f}  {label}",
                flush=True,
            )


def print_payoffs(round_result, agent_ids):
    payoffs = round_result.payoffs
    if not payoffs:
        return
    totals = payoffs.total
    max_score = max(totals.values()) if totals else 1.0

    print(flush=True)
    for aid in agent_ids:
        score = totals.get(aid, 0.0)
        b = bar(max(0.0, score / max(max_score, 1.0)))
        short = aid[-12:] if len(aid) > 12 else aid
        color = GREEN if score == max_score else WHITE
        print(f"  {short:15s}  {color}{score:+7.2f}{RESET}  {b}", flush=True)


def print_reasoning(round_result, agent_ids):
    reasonings = getattr(round_result, "reasonings", {})
    if not reasonings:
        return
    any_content = any(
        r and (r.get("thought") or r.get("intents")) if isinstance(r, dict) else bool(r)
        for r in reasonings.values()
    )
    if not any_content:
        print(f"  {DIM}(no reasoning this round){RESET}", flush=True)
        return
    for aid in agent_ids:
        r = reasonings.get(aid, {})
        short = aid[-12:] if len(aid) > 12 else aid
        if isinstance(r, dict):
            thought = r.get("thought", "").strip()
            intents = r.get("intents", {})
        else:
            thought = str(r).strip() if r else ""
            intents = {}

        if thought or intents:
            print(f"\n  {MAGENTA}{short}{RESET}", flush=True)
            if thought:
                for line in _wrap(f'"{thought}"', 60, "    "):
                    print(line, flush=True)
            if intents:
                intent_parts = []
                for target, val in sorted(intents.items()):
                    t_short = target[-8:] if len(target) > 8 else target
                    if val <= 0.1:
                        col = RED
                    elif val <= 0.4:
                        col = YELLOW
                    elif val <= 0.75:
                        col = CYAN
                    else:
                        col = GREEN
                    intent_parts.append(f"{t_short}:{col}{val:.2f}{RESET}")
                print(f"    {DIM}→ intents:{RESET} {', '.join(intent_parts)}", flush=True)
        else:
            print(f"  {DIM}{short:15s}  (no reasoning){RESET}", flush=True)


def print_reflections(round_result, agent_ids):
    notes = getattr(round_result, "notes", {})
    if not notes:
        return
    non_empty = {aid: txt for aid, txt in notes.items() if txt and txt.strip()}
    if not non_empty:
        print(f"  {DIM}(no reflections this round){RESET}", flush=True)
        return
    for aid in agent_ids:
        txt = non_empty.get(aid, "")
        short = aid[-12:] if len(aid) > 12 else aid
        if txt:
            print(f"\n  {CYAN}{short}{RESET}", flush=True)
            for line in _wrap(f'"{txt.strip()}"', 60, "    "):
                print(line, flush=True)
        else:
            print(f"  {DIM}{short:15s}  (no reflection){RESET}", flush=True)


def print_state_changes(round_result, prev_snapshots, agent_ids):
    curr = round_result.state_snapshots
    print(flush=True)
    for aid in agent_ids:
        c = curr.get(aid, {})
        p = prev_snapshots.get(aid, {})
        if not c:
            continue

        changes = []
        short = aid[-12:] if len(aid) > 12 else aid

        mood_c = c.get("mood", "?")
        mood_p = p.get("mood", "neutral")
        if mood_c != mood_p:
            mc = mood_color(mood_c)
            changes.append(f"mood {DIM}{mood_p}{RESET}→{mc}{mood_c}{RESET}")

        for field in ["tension", "fear", "anger", "dominance"]:
            vc = c.get(field, 0)
            vp = p.get(field, 0)
            if abs(vc - vp) >= 0.03:
                delta = vc - vp
                col = RED if delta > 0 and field in ("tension", "fear", "anger") else \
                      GREEN if delta < 0 and field in ("tension", "fear", "anger") else \
                      GREEN if delta > 0 else RED
                changes.append(f"{field} {vp:.2f}→{col}{vc:.2f}{RESET}")

        # Trust changes
        trust_c = c.get("trust", {})
        trust_p = p.get("trust", {})
        for peer, tv in trust_c.items():
            tp = trust_p.get(peer, 0.5)
            if abs(tv - tp) >= 0.03:
                col = GREEN if tv > tp else RED
                short_peer = peer[-6:] if len(peer) > 6 else peer
                changes.append(f"trust[{short_peer}] {tp:.2f}→{col}{tv:.2f}{RESET}")

        if changes:
            print(f"  {YELLOW}{short:15s}{RESET}  " + "  ".join(changes), flush=True)
        else:
            print(f"  {DIM}{short:15s}  (no significant changes){RESET}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Island — Live Simulation")
    parser.add_argument("--rounds", type=int, default=20, help="Number of rounds (default: 20)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--html", action="store_true", help="Export HTML + JSON log after simulation")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"\n{BOLD}{'═'*54}{RESET}", flush=True)
    print(f"{BOLD}{'ISLAND SIMULATION':^54s}{RESET}", flush=True)
    subtitle = "( expanded prisoner's dilemma )"
    print(f"{BOLD}{subtitle:^54s}{RESET}", flush=True)
    print(f"{BOLD}{f'{args.rounds} rounds  •  4 agents  •  Gemini Flash':^54s}{RESET}", flush=True)
    print(f"{BOLD}{'═'*54}{RESET}\n", flush=True)

    print("Loading agents...", flush=True)
    agents, agent_ids = build_agents()
    print_agent_table(agents)

    # Capture initial snapshots for state diff
    prev_snapshots = {
        a.agent_id: a.states.to_dict() for a in agents
    }

    print(f"Starting simulation ({args.rounds} rounds)...", flush=True)
    print(f"{DIM}Each round: dialog phase (Grok) → decisions → payoffs → state update{RESET}\n", flush=True)

    # Monkey-patch run_simulation to get per-round live output
    from simulation import game_engine as _ge
    original_run = _ge.run_simulation

    # We run simulation normally but intercept round results via a wrapper
    # that prints after each round completes
    import functools

    class LiveGameResult:
        """Wrapper that prints live output as each round completes."""

        def __init__(self, total_rounds, prev_snaps, agent_ids_list):
            self.total_rounds = total_rounds
            self.prev_snaps = prev_snaps
            self.agent_ids = agent_ids_list

        def on_round(self, round_result):
            rn = round_result.round_number

            header(f"ROUND {rn}/{self.total_rounds}  /  DIALOG PHASE")
            print_round_dialog(round_result, self.agent_ids)

            header(f"ROUND {rn}/{self.total_rounds}  /  REASONING")
            print_reasoning(round_result, self.agent_ids)

            header(f"ROUND {rn}/{self.total_rounds}  /  DECISIONS")
            print_decisions(round_result, self.agent_ids)

            header(f"ROUND {rn}/{self.total_rounds}  /  PAYOFFS")
            print_payoffs(round_result, self.agent_ids)

            header(f"ROUND {rn}/{self.total_rounds}  /  STATE CHANGES")
            print_state_changes(round_result, self.prev_snaps, self.agent_ids)

            header(f"ROUND {rn}/{self.total_rounds}  /  REFLECTIONS")
            print_reflections(round_result, self.agent_ids)

            # Update prev snapshots for next round diff
            self.prev_snaps = dict(round_result.state_snapshots)

            print(flush=True)

    live = LiveGameResult(args.rounds, prev_snapshots, agent_ids)

    # Patch run_simulation to call live.on_round after each round
    def patched_run(agents_list, total_rounds=10, model="google/gemini-2.0-flash-001",
                    use_dialog=True, simulation_id=None, reveal_requests=None):
        result = original_run(
            agents_list,
            total_rounds=total_rounds,
            model=model,
            use_dialog=use_dialog,
            simulation_id=simulation_id,
            reveal_requests=reveal_requests,
        )
        for rr in result.rounds:
            live.on_round(rr)
        return result

    # Live progress callback — prints to terminal immediately as each phase completes
    _phase_start = [time.time()]  # mutable container for closure

    def live_progress(event: str):
        parts = event.split(":")
        if len(parts) < 4:
            return
        rnum, total, stage = int(parts[1]), int(parts[2]), parts[3]
        now = time.time()
        elapsed = now - _phase_start[0]
        _phase_start[0] = now

        if stage == "dialog_start":
            _phase_start[0] = now  # reset timer at round start
            print(f"  {DIM}Round {rnum}/{total}{RESET}  dialog...", end="", flush=True)
        elif stage == "dialog_done":
            print(f" {DIM}({elapsed:.1f}s){RESET}  reasoning...", end="", flush=True)
        elif stage == "reasoning_done":
            print(f" {DIM}({elapsed:.1f}s){RESET}  decisions...", end="", flush=True)
        elif stage == "decisions_done":
            print(f" {DIM}({elapsed:.1f}s){RESET}  payoffs...", end="", flush=True)
        elif stage == "complete":
            print(f" {DIM}({elapsed:.1f}s){RESET}  {GREEN}✓{RESET}", flush=True)

    # Since run_simulation runs all rounds internally, we call it directly
    # and then render each round from the result
    print(f"{DIM}Running simulation with Gemini Flash (fast)...{RESET}\n", flush=True)
    t_start = time.time()

    from simulation.game_engine import run_simulation
    result = run_simulation(
        agents,
        total_rounds=args.rounds,
        model="google/gemini-2.0-flash-001",
        use_dialog=True,
        simulation_id="live_run",
        on_progress=live_progress,
    )

    elapsed = time.time() - t_start
    print(flush=True)

    # Print all rounds
    for rr in result.rounds:
        live.on_round(rr)

    # Final results
    print(f"\n{BOLD}{'═'*54}{RESET}", flush=True)
    print(f"{BOLD}  FINAL RESULTS  ({elapsed:.0f}s elapsed){RESET}", flush=True)
    print(f"{BOLD}{'═'*54}{RESET}\n", flush=True)

    sorted_scores = sorted(result.final_scores.items(), key=lambda x: -x[1])
    max_score = sorted_scores[0][1] if sorted_scores else 1.0

    for i, (aid, score) in enumerate(sorted_scores):
        b = bar(max(0.0, score / max(max_score, 1.0)))
        agent = next((a for a in agents if a.agent_id == aid), None)
        mood = agent.states.mood if agent else "?"
        mc = mood_color(mood)
        medal = ["🥇", "🥈", "🥉", " 4"][min(i, 3)]
        short = aid[-15:] if len(aid) > 15 else aid
        winner_mark = f"  {BOLD}{GREEN}← WINNER{RESET}" if i == 0 else ""
        print(
            f"  {medal}  {short:17s}  {score:+8.2f}  {b}  {mc}{mood}{RESET}{winner_mark}",
            flush=True,
        )

    print(f"\n  Winner: {BOLD}{GREEN}{result.winner}{RESET}", flush=True)

    # Score range context
    sr = result.score_range()
    print(f"\n  {DIM}Score context ({sr['n_rounds']} rounds, {sr['n_agents']} agents):", flush=True)
    print(f"  Max possible (always exploit): {sr['max_possible']:+.1f}", flush=True)
    print(f"  Mutual coop:                   {sr['mutual_coop_score']:+.1f}", flush=True)
    print(f"  Mutual defect:                 {sr['mutual_defect_score']:+.1f}", flush=True)
    print(f"  Min possible (always sucker):  {sr['min_possible']:+.1f}{RESET}", flush=True)
    print(flush=True)

    # HTML / JSON export
    if args.html:
        from export_game_log import export_to_html
        logs_dir = ROOT / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Build extended log with reflections and conclusions
        extended_log = result.to_dict()
        extended_log["score_range"] = sr

        # Collect per-round notes and reasoning from RoundResult (populated before archive_game)
        agent_reflections = {a.agent_id: [] for a in agents}
        agent_reasonings = {a.agent_id: [] for a in agents}
        for rr in result.rounds:
            for aid in agent_reflections:
                note = rr.notes.get(aid, "")
                if note:
                    agent_reflections[aid].append({"round": rr.round_number, "notes": note})
                reasoning = rr.reasonings.get(aid)
                if reasoning:
                    agent_reasonings[aid].append({"round": rr.round_number, "reasoning": reasoning})

        extended_log["agent_reflections"] = agent_reflections

        # Collect post-game conclusions from game_history
        extended_log["game_conclusions"] = {}
        for a in agents:
            if a.memory.game_history:
                last = a.memory.game_history[-1]
                if last.get("conclusion"):
                    extended_log["game_conclusions"][a.agent_id] = last["conclusion"]

        extended_log["agent_reasonings"] = agent_reasonings

        sim_id = result.simulation_id or "run"

        json_path = logs_dir / f"game_{sim_id}.json"
        json_path.write_text(
            __import__("json").dumps(extended_log, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  JSON log: {json_path}", flush=True)

        html_path = logs_dir / f"game_{sim_id}.html"
        export_to_html(extended_log, output_path=html_path)
        print(f"  HTML log: {html_path}", flush=True)
        print(f"\n  {BOLD}{GREEN}Open in browser:{RESET} open \"{html_path}\"", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
