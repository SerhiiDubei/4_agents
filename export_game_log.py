"""
export_game_log.py

Generates a self-contained HTML file from an Island simulation log.

Usage:
    # From run_simulation_live.py with --html flag (automatic)
    python3 run_simulation_live.py --rounds 3 --html

    # Or directly from a saved JSON log:
    python3 export_game_log.py logs/game_live_run.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from html import escape
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_label(val: float) -> str:
    if val <= 0.15:
        return "betray"
    if val <= 0.45:
        return "soft-D"
    if val <= 0.75:
        return "soft-C"
    return "coop"


def _action_color_class(val: float) -> str:
    if val <= 0.15:
        return "act-betray"
    if val <= 0.45:
        return "act-softd"
    if val <= 0.75:
        return "act-softc"
    return "act-coop"


def _bar_html(val: float, width: int = 10) -> str:
    filled = max(0, min(width, round(val * width)))
    filled_s = "█" * filled
    empty_s = "░" * (width - filled)
    return f'<span class="bar-filled">{escape(filled_s)}</span><span class="bar-empty">{escape(empty_s)}</span>'


def _short_id(agent_id: str) -> str:
    return agent_id[-12:] if len(agent_id) > 12 else agent_id


def _payoff_class(val: float) -> str:
    return "pos" if val >= 0 else "neg"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(log: dict) -> str:
    sim_id = escape(log.get("simulation_id", "unknown"))
    n_rounds = log.get("total_rounds", len(log.get("rounds", [])))
    winner = escape(log.get("winner", "?"))
    agents = log.get("agents", [])
    final_scores = log.get("final_scores", {})

    # Score range
    sr = log.get("score_range", {})
    sr_html = ""
    if sr:
        sr_html = f"""
        <div class="score-range">
            <span class="label">Score range ({n_rounds} rounds, {len(agents)} agents):</span>
            <span class="sr-item">Max exploit: <b>{sr.get('max_possible', '?')}</b></span>
            <span class="sr-item">Mutual coop: <b>{sr.get('mutual_coop_score', '?')}</b></span>
            <span class="sr-item">Mutual defect: <b>{sr.get('mutual_defect_score', '?')}</b></span>
            <span class="sr-item">Min sucker: <b>{sr.get('min_possible', '?')}</b></span>
        </div>"""

    # Agent summary table
    sorted_agents = sorted(final_scores.items(), key=lambda x: -x[1])
    rows = ""
    for rank, (aid, score) in enumerate(sorted_agents):
        winner_mark = " <span class='winner-mark'>WINNER</span>" if aid == log.get("winner") else ""
        rows += f"<tr class='{'winner-row' if aid == log.get('winner') else ''}'>"
        rows += f"<td>{rank + 1}</td>"
        rows += f"<td class='agent-id'>{escape(_short_id(aid))}</td>"
        rows += f"<td class='score {'pos' if score >= 0 else 'neg'}'>{score:+.2f}{winner_mark}</td>"
        rows += "</tr>\n"

    return f"""
<div class="header-block">
    <div class="sim-title">ISLAND SIMULATION</div>
    <div class="sim-meta">
        <span>ID: <code>{sim_id}</code></span>
        <span>{n_rounds} rounds</span>
        <span>{len(agents)} agents</span>
    </div>
    <div class="winner-banner">Winner: <strong>{winner}</strong></div>
    {sr_html}
    <table class="agents-table">
        <thead><tr><th>#</th><th>Agent</th><th>Final Score</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
</div>"""


def _build_round(round_data: dict, agent_reflections: dict, agent_reasonings: dict = None) -> str:
    rnum = round_data.get("round", "?")
    dialog_data = round_data.get("dialog", {})
    actions = round_data.get("actions", {})
    payoffs_data = round_data.get("payoffs", {})

    # Dialog section
    messages = dialog_data.get("messages", [])
    dialog_html = ""
    if messages:
        dialog_html = '<div class="section-label">DIALOG</div><div class="dialog">'
        for msg in messages:
            sender = escape(_short_id(msg.get("sender", "?")))
            text = escape(msg.get("text", ""))
            channel = msg.get("channel", "public")
            if channel == "public":
                dialog_html += f'<div class="msg public"><span class="sender">{sender}</span>: &ldquo;{text}&rdquo;</div>\n'
            elif channel.startswith("dm_"):
                target = escape(_short_id(channel[3:]))
                dialog_html += f'<div class="msg dm"><span class="dm-label">[DM]</span> <span class="sender">{sender}</span> → <span class="sender">{target}</span>: &ldquo;{text}&rdquo;</div>\n'
        dialog_html += "</div>"

    # Decisions section
    decisions_html = ""
    if actions:
        decisions_html = '<div class="section-label">DECISIONS</div><div class="decisions">'
        for agent_id, agent_acts in actions.items():
            sid = escape(_short_id(agent_id))
            decisions_html += f'<div class="decision-row"><span class="agent-id">{sid}</span> →'
            for target_id, val in agent_acts.items():
                tid = escape(_short_id(target_id))
                label = _action_label(val)
                color_cls = _action_color_class(val)
                bar = _bar_html(val, width=8)
                decisions_html += (
                    f' <span class="action-item">'
                    f'<span class="target-id">{tid}</span>: '
                    f'<span class="{color_cls}">{val:.2f} {label}</span> {bar}'
                    f'</span>'
                )
            decisions_html += "</div>\n"
        decisions_html += "</div>"

    # Payoffs section
    payoffs_html = ""
    pair_outcomes = payoffs_data.get("pair_outcomes", [])
    total_payoffs = payoffs_data.get("payoffs", {})
    if total_payoffs:
        payoffs_html = '<div class="section-label">PAYOFFS</div><div class="payoffs">'
        for aid, delta in sorted(total_payoffs.items(), key=lambda x: -x[1]):
            sid = escape(_short_id(aid))
            cls = _payoff_class(delta)
            payoffs_html += f'<div class="payoff-row"><span class="agent-id">{sid}</span> <span class="{cls}">{delta:+.3f} pts</span></div>\n'
        payoffs_html += "</div>"

    # Reflections section
    reflections_html = ""
    round_notes = []
    for agent_id, notes_list in agent_reflections.items():
        for entry in notes_list:
            if entry.get("round") == rnum and entry.get("notes"):
                round_notes.append((agent_id, entry["notes"]))

    if round_notes:
        reflections_html = '<div class="section-label">REFLECTIONS</div><div class="reflections">'
        for agent_id, notes in round_notes:
            sid = escape(_short_id(agent_id))
            note_text = escape(notes)
            reflections_html += f'<div class="reflection"><span class="agent-id">{sid}</span>: &ldquo;{note_text}&rdquo;</div>\n'
        reflections_html += "</div>"

    # Reasoning section (pre-decision thoughts + per-target intents)
    reasoning_html = ""
    if agent_reasonings:
        round_reasonings = []
        for agent_id, rounds_list in agent_reasonings.items():
            for entry in rounds_list:
                if entry.get("round") == rnum and entry.get("reasoning"):
                    round_reasonings.append((agent_id, entry["reasoning"]))
        if round_reasonings:
            reasoning_html = '<div class="section-label">REASONING</div><div class="reasonings">'
            for agent_id, r_data in round_reasonings:
                sid = escape(_short_id(agent_id))
                # r_data is either a dict {thought, intents} or a legacy plain string
                if isinstance(r_data, dict):
                    thought = r_data.get("thought", "").strip()
                    intents = r_data.get("intents", {})
                else:
                    thought = str(r_data).strip()
                    intents = {}

                thought_esc = escape(thought)
                reasoning_html += f'<div class="reasoning-entry"><span class="agent-id">{sid}</span>: &ldquo;{thought_esc}&rdquo;'
                if intents:
                    reasoning_html += '<div class="intents">'
                    for target_id, val in sorted(intents.items()):
                        t_short = escape(_short_id(target_id))
                        try:
                            v = float(val)
                        except (TypeError, ValueError):
                            v = 0.5
                        if v <= 0.1:
                            cls = "intent-betray"
                        elif v <= 0.4:
                            cls = "intent-defect"
                        elif v <= 0.75:
                            cls = "intent-cooperate"
                        else:
                            cls = "intent-trust"
                        reasoning_html += f'<span class="intent-pill {cls}">{t_short}: {v:.2f}</span> '
                    reasoning_html += "</div>"
                reasoning_html += "</div>\n"
            reasoning_html += "</div>"

    return f"""
<div class="round" id="round-{rnum}">
    <div class="round-header">── Round {rnum} ──────────────────────────────────</div>
    {dialog_html}
    {reasoning_html}
    {decisions_html}
    {payoffs_html}
    {reflections_html}
</div>"""


def _build_game_conclusions(log: dict) -> str:
    conclusions = log.get("game_conclusions", {})
    if not conclusions:
        return ""
    html = '<div class="section-label" style="margin-top:30px; font-size:1.1em;">POST-GAME CONCLUSIONS</div>'
    for agent_id, conclusion in conclusions.items():
        sid = escape(_short_id(agent_id))
        text = escape(conclusion)
        html += f'<div class="conclusion"><span class="agent-id">{sid}</span>: &ldquo;{text}&rdquo;</div>\n'
    return html


# ---------------------------------------------------------------------------
# CSS + HTML template
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: #0a0a0a;
    color: #d4d4d4;
    font-family: 'Courier New', Courier, monospace;
    font-size: 13px;
    line-height: 1.6;
    padding: 20px;
    max-width: 1100px;
    margin: 0 auto;
}
.header-block {
    border: 1px solid #2a2a2a;
    padding: 20px;
    margin-bottom: 30px;
    background: #111;
}
.sim-title {
    color: #7dd3fc;
    font-size: 1.4em;
    font-weight: bold;
    letter-spacing: 4px;
    margin-bottom: 8px;
    text-align: center;
}
.sim-meta {
    color: #6b7280;
    text-align: center;
    margin-bottom: 12px;
}
.sim-meta span { margin: 0 10px; }
.winner-banner {
    background: #14532d;
    color: #4ade80;
    text-align: center;
    padding: 8px;
    margin: 12px 0;
    font-size: 1.1em;
}
.winner-mark {
    background: #166534;
    color: #86efac;
    padding: 1px 6px;
    font-size: 0.8em;
    margin-left: 8px;
}
.score-range {
    color: #6b7280;
    margin: 10px 0;
    font-size: 0.9em;
}
.score-range .label { margin-right: 12px; color: #9ca3af; }
.score-range .sr-item { margin-right: 16px; }
.agents-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 14px;
}
.agents-table th {
    color: #6b7280;
    border-bottom: 1px solid #2a2a2a;
    padding: 4px 10px;
    text-align: left;
}
.agents-table td { padding: 4px 10px; border-bottom: 1px solid #1a1a1a; }
.winner-row { background: #0d1f14; }

/* Navigation */
.nav {
    position: sticky;
    top: 0;
    background: #0a0a0a;
    border-bottom: 1px solid #1e1e1e;
    padding: 6px 0;
    margin-bottom: 16px;
    color: #6b7280;
    font-size: 0.85em;
}
.nav a { color: #7dd3fc; text-decoration: none; margin-right: 6px; }
.nav a:hover { color: #bae6fd; }

/* Rounds */
.round {
    border-left: 3px solid #1e3a5f;
    margin: 16px 0;
    padding: 10px 18px;
    background: #0d0d0d;
}
.round-header {
    color: #7dd3fc;
    font-size: 1.0em;
    margin-bottom: 12px;
    letter-spacing: 1px;
}
.section-label {
    color: #6b7280;
    font-size: 0.8em;
    letter-spacing: 2px;
    margin: 10px 0 5px 0;
    text-transform: uppercase;
}

/* Dialog */
.msg { margin: 3px 0; padding-left: 4px; }
.msg.public { color: #a3e635; }
.msg.dm { color: #fb923c; font-style: italic; }
.dm-label { color: #f59e0b; font-weight: bold; }
.sender { font-weight: bold; }

/* Decisions */
.decision-row { margin: 3px 0; }
.action-item { margin-left: 10px; }
.target-id { color: #94a3b8; }
.act-betray { color: #f87171; }
.act-softd  { color: #fb923c; }
.act-softc  { color: #86efac; }
.act-coop   { color: #4ade80; font-weight: bold; }
.bar-filled { color: #818cf8; }
.bar-empty  { color: #1e293b; }

/* Payoffs */
.payoff-row { margin: 2px 0; }
.pos { color: #4ade80; }
.neg { color: #f87171; }

/* Reflections */
.reflection {
    color: #94a3b8;
    border-left: 2px solid #334155;
    padding: 3px 8px;
    margin: 4px 0;
    font-style: italic;
}

/* Reasoning (pre-decision thinking) */
.reasoning-entry {
    color: #d8b4fe;
    border-left: 2px solid #7c3aed;
    padding: 3px 8px;
    margin: 4px 0;
    font-style: italic;
}
.agent-id { color: #c084fc; font-weight: bold; }
.score { font-weight: bold; }

/* Intent pills */
.intents { margin-top: 4px; font-style: normal; }
.intent-pill {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    margin-right: 4px;
    font-size: 0.85em;
    font-weight: bold;
}
.intent-betray    { background: #7f1d1d; color: #fca5a5; }
.intent-defect    { background: #78350f; color: #fde68a; }
.intent-cooperate { background: #14532d; color: #86efac; }
.intent-trust     { background: #1e3a5f; color: #93c5fd; }

/* Conclusions */
.conclusion {
    border-left: 3px solid #1d4ed8;
    background: #0f172a;
    padding: 8px 14px;
    margin: 8px 0;
    color: #bfdbfe;
}

code { color: #86efac; font-size: 0.9em; }
"""


def export_to_html(
    game_log: dict,
    output_path: Path,
) -> None:
    """
    Generate a self-contained HTML file from a game log dict.

    game_log: GameResult.to_dict() optionally extended with:
      - "agent_reflections": {agent_id: [{round, notes}]}
      - "game_conclusions": {agent_id: conclusion_text}
      - "score_range": dict from GameResult.score_range()
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    agent_reflections = game_log.get("agent_reflections", {})
    agent_reasonings = game_log.get("agent_reasonings", {})
    rounds = game_log.get("rounds", [])
    n_rounds = game_log.get("total_rounds", len(rounds))

    # Navigation links
    nav_links = " ".join(
        f'<a href="#round-{r.get("round", i+1)}">R{r.get("round", i+1)}</a>'
        for i, r in enumerate(rounds)
    )
    nav_html = f'<div class="nav">Jump to round: {nav_links}</div>' if nav_links else ""

    # Build sections
    header_html = _build_header(game_log)
    rounds_html = "\n".join(_build_round(r, agent_reflections, agent_reasonings) for r in rounds)
    conclusions_html = _build_game_conclusions(game_log)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sim_id = game_log.get("simulation_id", "unknown")

    html = f"""<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Island — Game Log {sim_id}</title>
    <style>{_CSS}</style>
</head>
<body>
{header_html}
{nav_html}
<div class="rounds">
{rounds_html}
</div>
{conclusions_html}
<div style="color:#374151; margin-top:40px; font-size:0.8em; text-align:center;">
    Generated {generated_at} &nbsp;|&nbsp; Island Simulation &nbsp;|&nbsp; {n_rounds} rounds
</div>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI — read JSON and export
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 export_game_log.py <game_log.json> [output.html]")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        game_log = json.load(f)

    if len(sys.argv) >= 3:
        out_path = Path(sys.argv[2])
    else:
        out_path = json_path.with_suffix(".html")

    export_to_html(game_log, output_path=out_path)
    print(f"HTML exported: {out_path}")
