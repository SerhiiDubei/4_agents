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

def _cooperation_value(val) -> float:
    """Extract cooperation from legacy float or per-dim dict."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5


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


def _display_name(agent_id: str, names: dict) -> str:
    """Return display name if available, otherwise short ID."""
    return names.get(agent_id) or _short_id(agent_id)


def _payoff_class(val: float) -> str:
    return "pos" if val >= 0 else "neg"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_character_profiles_block(log: dict) -> str:
    """Character profiles — connections, profession, bio. Показується всім."""
    agent_profiles = log.get("agent_profiles", {})
    agents = log.get("agents", [])
    names = log.get("agent_names", {})
    if not agent_profiles and not agents:
        return ""

    rows = []
    for aid in agents:
        prof = agent_profiles.get(aid, {})
        disp = escape(_display_name(aid, names))
        conn = escape(prof.get("connections", "—"))
        prof_text = escape(prof.get("profession", "—"))
        bio = escape(prof.get("bio", "—"))
        rows.append(
            f"<tr><td><span class='agent-name'>{disp}</span></td>"
            f"<td>{conn}</td><td>{prof_text}</td><td>{bio}</td></tr>"
        )
    if not rows:
        return ""

    return f"""
<div class="character-profiles-block">
    <div class="section-label">ПРОФІЛІ ПЕРСОНАЖІВ (зв'язки, професія, біо)</div>
    <table class="character-profiles-table">
        <thead><tr><th>Персонаж</th><th>Зв'язки</th><th>Професія</th><th>Біографія</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
    </table>
</div>"""


def _build_character_status_block(log: dict) -> str:
    """Character status — cumulative stats per agent (games, wins, total_score)."""
    agent_stats = log.get("agent_stats", {})
    agents = log.get("agents", [])
    names = log.get("agent_names", {})
    if not agent_stats and not agents:
        return ""

    # Build rows for agents in this game
    rows = []
    for aid in agents:
        rec = agent_stats.get(aid, {})
        disp = escape(_display_name(aid, names))
        games = rec.get("games_played", 0)
        wins = rec.get("wins", 0)
        total = rec.get("total_score", 0.0)
        win_rate = f"{(wins/games*100):.0f}%" if games else "—"
        rows.append(
            f"<tr><td><span class='agent-name'>{disp}</span></td>"
            f"<td>{games}</td><td>{wins}</td><td>{win_rate}</td>"
            f"<td class='score {'pos' if total >= 0 else 'neg'}'>{total:+.1f}</td></tr>"
        )
    if not rows:
        return ""

    return f"""
<div class="character-status-block">
    <div class="section-label">СТАТУС ПЕРСОНАЖІВ (накопичувальна статистика)</div>
    <table class="character-status-table">
        <thead><tr><th>Персонаж</th><th>Ігор</th><th>Перемог</th><th>Win rate</th><th>Сума очок</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
    </table>
</div>"""


def _build_story_block(log: dict) -> str:
    """Story block — overall story params (year, place, setup, problem)."""
    sp = log.get("story_params", {})
    if not sp:
        return ""
    parts = []
    if sp.get("year"):
        parts.append(f"Рік: {escape(sp['year'])}")
    if sp.get("place"):
        parts.append(f"Місце: {escape(sp['place'])}")
    if sp.get("setup"):
        parts.append(f"Завязка: {escape(sp['setup'])}")
    if sp.get("problem"):
        parts.append(f"Проблема: {escape(sp['problem'])}")
    if sp.get("characters"):
        chars = ", ".join(escape(str(c)) for c in sp["characters"])
        parts.append(f"Ролі: {chars}")
    if sp.get("stakes"):
        parts.append(f"На кону: {escape(sp['stakes'])}")
    if not parts:
        return ""
    return f"""
<div class="story-block">
    <div class="section-label">ІСТОРІЯ</div>
    <div class="story-params">{escape(" — ").join(parts)}</div>
</div>"""


def _build_header(log: dict) -> str:
    sim_id = escape(log.get("simulation_id", "unknown"))
    n_rounds = log.get("total_rounds", len(log.get("rounds", [])))
    agents = log.get("agents", [])
    final_scores = log.get("final_scores", {})
    names = log.get("agent_names", {})
    winner_id = log.get("winner", "?")
    winner_disp = escape(_display_name(winner_id, names))

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
        disp = escape(_display_name(aid, names))
        short = escape(_short_id(aid))
        winner_mark = " <span class='winner-mark'>WINNER</span>" if aid == winner_id else ""
        rows += f"<tr class='{'winner-row' if aid == winner_id else ''}'>"
        rows += f"<td>{rank + 1}</td>"
        rows += f"<td><span class='agent-name'>{disp}</span> <span class='agent-id-small'>{short}</span></td>"
        rows += f"<td class='score {'pos' if score >= 0 else 'neg'}'>{score:+.2f}{winner_mark}</td>"
        rows += "</tr>\n"

    # Per-round positions table
    rounds_data = log.get("rounds", [])
    cumulative: dict[str, float] = {aid: 0.0 for aid in agents}
    pos_header = "<tr><th>Agent</th>" + "".join(f"<th>R{r.get('round','?')}</th>" for r in rounds_data) + "</tr>"
    pos_rows = ""
    per_round_scores: list[dict] = []
    for r in rounds_data:
        payoffs = r.get("payoffs", {}).get("total", {})
        for aid in agents:
            cumulative[aid] = round(cumulative.get(aid, 0.0) + payoffs.get(aid, 0.0), 2)
        per_round_scores.append(dict(cumulative))

    for aid in agents:
        disp = escape(_display_name(aid, names))
        cells = ""
        for i, rscores in enumerate(per_round_scores):
            ranked = sorted(rscores.items(), key=lambda x: -x[1])
            rank = next((j + 1 for j, (a, _) in enumerate(ranked) if a == aid), "?")
            score = rscores.get(aid, 0)
            rank_cls = f"rank-{rank}" if isinstance(rank, int) and rank <= 4 else ""
            cells += f"<td class='{rank_cls}'><b>#{rank}</b><br><small>{score:+.1f}</small></td>"
        pos_rows += f"<tr><td><span class='agent-name'>{disp}</span></td>{cells}</tr>\n"

    positions_table = f"""
    <div class="section-label" style="margin-top:16px">POSITIONS BY ROUND (cumulative)</div>
    <table class="positions-table">
        <thead>{pos_header}</thead>
        <tbody>{pos_rows}</tbody>
    </table>"""

    story_block = _build_story_block(log)
    character_profiles = _build_character_profiles_block(log)
    character_status = _build_character_status_block(log)
    return f"""
<div class="header-block">
    <div class="sim-title">ISLAND SIMULATION</div>
    {story_block}
    {character_profiles}
    {character_status}
    <div class="sim-meta">
        <span>ID: <code>{sim_id}</code></span>
        <span>{n_rounds} rounds</span>
        <span>{len(agents)} agents</span>
    </div>
    <div class="winner-banner">Winner: <strong>{winner_disp}</strong></div>
    {sr_html}
    <table class="agents-table">
        <thead><tr><th>#</th><th>Agent</th><th>Final Score</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    {positions_table}
</div>"""


def _build_round(round_data: dict, agent_reflections: dict, agent_reasonings: dict = None, names: dict = None) -> str:
    names = names or {}
    rnum = round_data.get("round", "?")
    dialog_data = round_data.get("dialog", {})
    actions = round_data.get("actions", {})
    payoffs_data = round_data.get("payoffs", {})

    def dn(agent_id: str) -> str:
        return escape(_display_name(agent_id, names))

    # Round narrative — широкий опис що відбулося для кожного і всіх
    round_narrative_html = ""
    round_narrative = round_data.get("round_narrative", "")
    if round_narrative:
        round_narrative_html = (
            f'<div class="round-narrative-block">'
            f'<div class="section-label">ЩО ВІДБУЛОСЬ ДАЛІ (продовження історії)</div>'
            f'<div class="round-narrative-text">{escape(round_narrative)}</div>'
            f'</div>'
        )

    # Round-level story block (event + participants)
    round_story_html = ""
    round_event = round_data.get("round_event", {})
    participants_per_agent = round_data.get("participants_per_agent", {})
    if round_event or participants_per_agent:
        round_story_html = '<div class="round-story-block"><div class="section-label">ПОДІЯ РАУНДУ</div>'
        if round_event.get("template"):
            round_story_html += f'<div class="round-event-template">{escape(round_event["template"])}</div>'
        formatted = round_event.get("formatted_per_agent", {})
        if formatted:
            round_story_html += '<div class="round-event-per-agent">'
            for aid, ev_text in sorted(formatted.items(), key=lambda x: x[0]):
                if ev_text:
                    round_story_html += f'<div class="agent-event"><span class="agent-name">{dn(aid)}</span>: {escape(ev_text)}</div>'
            round_story_html += "</div>"
        if participants_per_agent:
            round_story_html += '<div class="participants-per-agent">'
            for aid, parts in sorted(participants_per_agent.items(), key=lambda x: x[0]):
                part_names = ", ".join(dn(p) for p in parts) if parts else "—"
                round_story_html += f'<div class="agent-participants"><span class="agent-name">{dn(aid)}</span> вирішує щодо: {part_names}</div>'
            round_story_html += "</div>"
        round_story_html += "</div>"

    # Situation section — per-agent (500+ chars each) with agent-specific highlighting
    agent_colors = ["agent-color-1", "agent-color-2", "agent-color-3", "agent-color-4"]
    situations_per_agent = round_data.get("situations_per_agent", {})
    if situations_per_agent:
        situation_html = '<div class="section-label">ЩО БАЧИТЬ КОЖЕН АГЕНТ (ситуація)</div><div class="situations-per-agent">'
        for i, (agent_id, text) in enumerate(sorted(situations_per_agent.items(), key=lambda x: x[0])):
            if text:
                sid = dn(agent_id)
                color_cls = agent_colors[i % len(agent_colors)]
                situation_html += f'<div class="situation-per-agent {color_cls}"><span class="agent-name">{sid}</span>:<pre class="situation-text">{escape(text)}</pre></div>\n'
        situation_html += "</div>"
    elif round_data.get("situation"):
        situation_html = f'<div class="section-label">SITUATION</div><div class="situation">{escape(round_data["situation"])}</div>'
    else:
        situation_html = ""

    # Situation reactions (each agent's reaction to the situation, before dialog)
    situation_reactions_html = ""
    sit_reflections = round_data.get("situation_reflections", {})
    if sit_reflections:
        situation_reactions_html = '<div class="section-label">РЕАКЦІЯ НА СИТУАЦІЮ (що кожен відчуває)</div><div class="situation-reactions">'
        for i, (agent_id, text) in enumerate(sorted(sit_reflections.items(), key=lambda x: x[0])):
            if text:
                sid = dn(agent_id)
                color_cls = agent_colors[i % len(agent_colors)]
                situation_reactions_html += f'<div class="situation-reaction {color_cls}"><span class="agent-name">{sid}</span>: &ldquo;{escape(text)}&rdquo;</div>\n'
        situation_reactions_html += "</div>"

    # Dialog section
    messages = dialog_data.get("messages", [])
    dialog_html = ""
    if messages:
        dialog_html = '<div class="section-label">DIALOG</div><div class="dialog">'
        for msg in messages:
            sender = dn(msg.get("sender", "?"))
            text = escape(msg.get("text", ""))
            channel = msg.get("channel", "public")
            if channel == "public":
                dialog_html += f'<div class="msg public"><span class="sender">{sender}</span>: &ldquo;{text}&rdquo;</div>\n'
            elif channel.startswith("dm_"):
                target = dn(channel[3:])
                dialog_html += f'<div class="msg dm"><span class="dm-label">[DM]</span> <span class="sender">{sender}</span> → <span class="sender">{target}</span>: &ldquo;{text}&rdquo;</div>\n'
        dialog_html += "</div>"

    # Decisions section — matrix (усі рішення в таблиці) + детальний список
    decisions_html = ""
    if actions:
        agent_ids = list(actions.keys())
        targets = agent_ids  # кожен гравець приймає рішення щодо всіх інших

        # Матриця рішень: рядки = хто рішує, стовпці = щодо кого, клітинка = cooperation
        decisions_html = '<div class="section-label">РІШЕННЯ (матриця: хто → щодо кого, 0=зрада 1=співпраця)</div>'
        decisions_html += '<div class="decisions-matrix-wrap"><table class="decisions-matrix">'
        decisions_html += "<thead><tr><th></th>"
        for t_id in targets:
            decisions_html += f'<th title="{escape(t_id)}">{dn(t_id)}</th>'
        decisions_html += "</tr></thead><tbody>"
        for agent_id in agent_ids:
            decisions_html += f'<tr><th>{dn(agent_id)}</th>'
            agent_acts = actions.get(agent_id, {})
            for target_id in targets:
                if target_id == agent_id:
                    decisions_html += '<td class="self-cell">—</td>'
                else:
                    val = agent_acts.get(target_id, 0.5)
                    coop = _cooperation_value(val)
                    color_cls = _action_color_class(coop)
                    label = _action_label(coop)
                    decisions_html += f'<td class="{color_cls}" title="{label}">{coop:.2f}</td>'
            decisions_html += "</tr>"
        decisions_html += "</tbody></table></div>"

        # Детальний список (розгорнутий)
        decisions_html += '<div class="section-label">РІШЕННЯ (детально)</div><div class="decisions">'
        for agent_id, agent_acts in actions.items():
            sid = dn(agent_id)
            decisions_html += f'<div class="decision-row"><span class="agent-name">{sid}</span> →'
            for target_id, val in sorted(agent_acts.items(), key=lambda x: x[0]):
                tid = dn(target_id)
                coop = _cooperation_value(val)
                label = _action_label(coop)
                color_cls = _action_color_class(coop)
                bar_h = _bar_html(coop, width=8)
                decisions_html += (
                    f' <span class="action-item">'
                    f'<span class="target-name">{tid}</span>: '
                    f'<span class="{color_cls}">{coop:.2f} {label}</span> {bar_h}'
                )
                if isinstance(val, dict) and len(val) > 1:
                    extra = " | ".join(f"{k}: {v:.2f}" for k, v in sorted(val.items()) if k != "cooperation")
                    if extra:
                        decisions_html += f' <span class="dim-extra">({extra})</span>'
                decisions_html += "</span>"
            decisions_html += "</div>\n"
        decisions_html += "</div>"

    # Payoffs section
    payoffs_html = ""
    pair_outcomes = payoffs_data.get("pair_outcomes", [])
    total_payoffs = payoffs_data.get("payoffs", {})
    if total_payoffs:
        payoffs_html = '<div class="section-label">PAYOFFS</div><div class="payoffs">'
        for aid, delta in sorted(total_payoffs.items(), key=lambda x: -x[1]):
            sid = dn(aid)
            cls = _payoff_class(delta)
            payoffs_html += f'<div class="payoff-row"><span class="agent-name">{sid}</span> <span class="{cls}">{delta:+.3f} pts</span></div>\n'
        payoffs_html += "</div>"

    # Consequences section (optional — after PAYOFFS, before REFLECTIONS)
    consequences_html = ""
    if round_data.get("consequences"):
        consequences_html = f'<div class="section-label">CONSEQUENCES</div><div class="consequences">{escape(round_data["consequences"])}</div>'

    # Reflections section
    reflections_html = ""
    round_notes = []
    for agent_id, notes_list in agent_reflections.items():
        for entry in notes_list:
            if entry.get("round") == rnum and entry.get("notes"):
                round_notes.append((agent_id, entry["notes"]))

    if round_notes:
        reflections_html = '<div class="section-label">REFLECTIONS</div><div class="reflections">'
        for i, (agent_id, notes) in enumerate(round_notes):
            sid = dn(agent_id)
            note_text = escape(notes)
            color_cls = agent_colors[i % len(agent_colors)]
            reflections_html += f'<div class="reflection {color_cls}"><span class="agent-name">{sid}</span>: &ldquo;{note_text}&rdquo;</div>\n'
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
            reasoning_html = '<div class="section-label">REASONING (думки перед рішенням)</div><div class="reasonings">'
            for i, (agent_id, r_data) in enumerate(round_reasonings):
                color_cls = agent_colors[i % len(agent_colors)]
                sid = dn(agent_id)
                if isinstance(r_data, dict):
                    thought = r_data.get("thought", "").strip()
                    intents = r_data.get("intents", {})
                else:
                    thought = str(r_data).strip()
                    intents = {}

                thought_esc = escape(thought)
                reasoning_html += f'<div class="reasoning-entry {color_cls}"><span class="agent-name">{sid}</span>: &ldquo;{thought_esc}&rdquo;'
                if intents:
                    reasoning_html += '<div class="intents">'
                    for target_id, val in sorted(intents.items()):
                        t_disp = dn(target_id)
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
                        reasoning_html += f'<span class="intent-pill {cls}">{t_disp}: {v:.2f}</span> '
                    reasoning_html += "</div>"
                reasoning_html += "</div>\n"
            reasoning_html += "</div>"

    # Social Fabric section — social actions + budget state + trust delta
    _ACTION_ICONS = {
        "alliance": "🤝", "betray": "🗡", "deceive": "🎭",
        "share_food": "🍎", "ignore": "○", "warn": "⚠", "reciprocate": "↩",
    }
    social_actions = round_data.get("🔷_social_actions", {})
    budget_state   = round_data.get("🔷_budget_state", {})
    trust_delta    = round_data.get("🔷_trust_delta", {})
    social_fabric_html = ""
    if social_actions or budget_state or trust_delta:
        sf = '<div class="section-label">SOCIAL FABRIC (соціальні дії · бюджет · довіра)</div>'
        sf += '<div class="social-fabric-block">'
        if social_actions:
            sf += '<div class="sf-actions">'
            for aid, acts in sorted(social_actions.items()):
                for act in acts:
                    tgt   = dn(act.get("target", "?"))
                    atype = act.get("type", "?")
                    icon  = _ACTION_ICONS.get(atype, "●")
                    val   = act.get("value", 0)
                    vis   = act.get("visibility", "public")
                    sf += (
                        f'<div class="sf-action-row">'
                        f'<span class="agent-name">{dn(aid)}</span> {icon} '
                        f'<span class="sf-action-type sf-{atype}">{atype}</span> → '
                        f'<span class="agent-name">{tgt}</span> '
                        f'<span class="sf-value">val={val:.2f}</span> '
                        f'<span class="sf-vis sf-vis-{vis}">[{vis}]</span></div>\n'
                    )
            sf += "</div>"
        if budget_state:
            sf += '<div class="sf-budget">'
            for aid, bs in sorted(budget_state.items()):
                pool  = float(bs.get("pool", bs.get("budget_pool", 0)) or 0)
                spent = float(bs.get("spent", bs.get("budget_spent_last", 0)) or 0)
                # received може бути dict {agent_id: value} або float
                received_raw = bs.get("received", bs.get("received_last_round", 0))
                if isinstance(received_raw, dict):
                    received_total = sum(received_raw.values())
                    received_detail = " ".join(
                        f'<span class="dim">{dn(src)}:{v:.2f}</span>'
                        for src, v in sorted(received_raw.items())
                    )
                    received_str = (
                        f'<span class="sf-received">{received_total:.2f}</span> '
                        f'<span class="sf-received-detail">({received_detail})</span>'
                    )
                else:
                    received_str = f'<span class="sf-received">{float(received_raw or 0):.2f}</span>'
                sf += (
                    f'<div class="sf-budget-row"><span class="agent-name">{dn(aid)}</span>: '
                    f'пул=<span class="sf-pool">{pool:.2f}</span> '
                    f'витрачено=<span class="sf-spent">{spent:.2f}</span> '
                    f'отримано={received_str}</div>\n'
                )
            sf += "</div>"
        if trust_delta:
            delta_rows = [
                (aid, pid, d)
                for aid, peers in sorted(trust_delta.items())
                for pid, d in sorted(peers.items())
                if abs(d) > 0.001
            ]
            if delta_rows:
                sf += '<div class="sf-trust">'
                for aid, pid, d in delta_rows:
                    sign = "+" if d >= 0 else ""
                    cls  = "sf-trust-pos" if d >= 0 else "sf-trust-neg"
                    sf += (
                        f'<div class="sf-trust-row"><span class="agent-name">{dn(aid)}</span> → '
                        f'<span class="agent-name">{dn(pid)}</span>: '
                        f'довіра <span class="{cls}">{sign}{d:.3f}</span></div>\n'
                    )
                sf += "</div>"
        sf += "</div>"
        social_fabric_html = sf

    return f"""
<div class="round" id="round-{rnum}">
    <div class="round-header">── Round {rnum} ──────────────────────────────────</div>
    {round_narrative_html}
    {round_story_html}
    {situation_html}
    {situation_reactions_html}
    {dialog_html}
    {reasoning_html}
    {decisions_html}
    {payoffs_html}
    {consequences_html}
    {reflections_html}
    {social_fabric_html}
</div>"""


def _build_game_conclusions(log: dict) -> str:
    conclusions = log.get("game_conclusions", {})
    if not conclusions:
        return ""
    names = log.get("agent_names", {})
    html = '<div class="section-label" style="margin-top:30px; font-size:1.1em;">POST-GAME CONCLUSIONS</div>'
    for agent_id, conclusion in conclusions.items():
        sid = escape(_display_name(agent_id, names))
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

/* Decisions matrix (heatmap) */
.decisions-matrix-wrap { overflow-x: auto; margin: 10px 0; }
.decisions-matrix {
    width: 100%; min-width: 400px; border-collapse: collapse; font-size: 0.9em;
}
.decisions-matrix th, .decisions-matrix td {
    border: 1px solid #334155; padding: 4px 8px; text-align: center;
}
.decisions-matrix th { background: #1e293b; color: #94a3b8; min-width: 60px; }
.decisions-matrix td.self-cell { background: #1a1a1a; color: #4b5563; }
.decisions-matrix td.act-betray { background: #7f1d1d; color: #fca5a5; }
.decisions-matrix td.act-softd { background: #78350f; color: #fde68a; }
.decisions-matrix td.act-softc { background: #14532d; color: #86efac; }
.decisions-matrix td.act-coop { background: #1e3a5f; color: #93c5fd; font-weight: bold; }

/* Payoffs */
.payoff-row { margin: 2px 0; }
.pos { color: #4ade80; }
.neg { color: #f87171; }

/* Character profiles (connections, profession, bio) */
.character-profiles-block {
    margin: 14px 0;
    padding: 10px 12px;
    background: #0f172a;
    border-left: 3px solid #8b5cf6;
}
.character-profiles-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9em;
}
.character-profiles-table th,
.character-profiles-table td {
    border: 1px solid #334155;
    padding: 4px 10px;
    text-align: left;
    vertical-align: top;
}
.character-profiles-table th {
    background: #1e293b;
    color: #94a3b8;
}
.character-profiles-table td:first-child {
    font-weight: bold;
}

/* Character status (cumulative stats) */
.character-status-block {
    margin: 14px 0;
    padding: 10px 12px;
    background: #0f172a;
    border-left: 3px solid #10b981;
}
.character-status-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9em;
}
.character-status-table th,
.character-status-table td {
    border: 1px solid #334155;
    padding: 4px 10px;
    text-align: left;
}
.character-status-table th {
    background: #1e293b;
    color: #94a3b8;
}
.character-status-table td:first-child {
    font-weight: bold;
}

/* Story block (header) */
.story-block {
    margin: 12px 0;
    padding: 10px 14px;
    background: #0f172a;
    border-left: 4px solid #3b82f6;
}
.story-params {
    color: #93c5fd;
    font-size: 0.95em;
}

/* Round narrative — широкий опис що відбулося */
.round-narrative-block {
    margin: 12px 0;
    padding: 12px 14px;
    background: #0c1222;
    border-left: 4px solid #a78bfa;
}
.round-narrative-text {
    color: #c4b5fd;
    font-size: 0.95em;
    line-height: 1.6;
    white-space: pre-wrap;
}

/* Round-level story (event + participants) */
.round-story-block {
    margin: 10px 0;
    padding: 10px 12px;
    background: #0c1222;
    border-left: 3px solid #6366f1;
}
.round-event-template {
    color: #a5b4fc;
    font-style: italic;
    margin-bottom: 6px;
}
.round-event-per-agent, .participants-per-agent {
    margin-top: 6px;
    font-size: 0.9em;
}
.agent-event, .agent-participants {
    margin: 2px 0;
    color: #94a3b8;
}

/* Per-agent color highlighting (consistent across situation, reaction, reflection, reasoning) */
.agent-color-1 { border-left-color: #3b82f6 !important; background: rgba(59, 130, 246, 0.06) !important; }
.agent-color-2 { border-left-color: #10b981 !important; background: rgba(16, 185, 129, 0.06) !important; }
.agent-color-3 { border-left-color: #f59e0b !important; background: rgba(245, 158, 11, 0.06) !important; }
.agent-color-4 { border-left-color: #ec4899 !important; background: rgba(236, 72, 153, 0.06) !important; }

/* Situation, Consequences */
.situation, .consequences {
    color: #94a3b8;
    border-left: 2px solid #334155;
    padding: 3px 8px;
    margin: 4px 0;
    font-style: italic;
}

/* Per-agent situations (500+ chars each, full display) */
.situations-per-agent { margin: 8px 0; }
.situation-per-agent {
    border-left: 3px solid #555;
    padding: 0.5em 1em;
    margin: 0.5em 0;
}
.situation-text {
    white-space: pre-wrap;
    margin: 0.3em 0;
    font-family: inherit;
    font-size: 0.95em;
}

/* Situation reactions (agent reactions to situation before dialog) */
.situation-reactions { margin: 6px 0; }
.situation-reaction {
    color: #94a3b8;
    border-left: 2px solid #334155;
    padding: 3px 8px;
    margin: 4px 0;
    font-style: italic;
}

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
.agent-name { color: #f0abfc; font-weight: bold; }
.agent-id-small { color: #7c3aed; font-size: 0.8em; }
.target-name { color: #a78bfa; }
.score { font-weight: bold; }

/* Positions table */
.positions-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85em; }
.positions-table th, .positions-table td { border: 1px solid #334155; padding: 4px 8px; text-align: center; }
.positions-table th { background: #1e293b; color: #94a3b8; }
.positions-table td:first-child { text-align: left; }
.rank-1 { background: #422006; color: #fbbf24; }
.rank-2 { background: #1e293b; color: #94a3b8; }
.rank-3 { background: #1c1917; color: #78716c; }
.rank-4 { background: #0f0f10; color: #4b5563; }

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

/* ── Social Fabric block ── */
.social-fabric-block {
    border-left: 3px solid #7c3aed;
    background: #0d0a1a;
    padding: 10px 14px;
    margin: 6px 0;
}
.sf-actions, .sf-budget, .sf-trust {
    margin-bottom: 8px;
}
.sf-action-row, .sf-budget-row, .sf-trust-row {
    padding: 3px 0;
    font-size: 0.92em;
    color: #c4b5fd;
}
.sf-action-type { font-weight: 600; text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.5px; }
.sf-alliance   { color: #34d399; }
.sf-betray     { color: #f87171; }
.sf-deceive    { color: #fbbf24; }
.sf-share_food { color: #a3e635; }
.sf-ignore     { color: #6b7280; }
.sf-warn       { color: #fb923c; }
.sf-reciprocate { color: #60a5fa; }
.sf-value      { color: #9ca3af; font-size: 0.85em; }
.sf-vis        { font-size: 0.78em; padding: 1px 5px; border-radius: 8px; margin-left: 4px; }
.sf-vis-public  { background: #1e3a5f; color: #7dd3fc; }
.sf-vis-private { background: #3b1f2a; color: #f9a8d4; }
.sf-pool       { color: #a78bfa; }
.sf-spent      { color: #f87171; }
.sf-received   { color: #34d399; }
.sf-trust-pos  { color: #4ade80; font-weight: 600; }
.sf-trust-neg  { color: #f87171; font-weight: 600; }
.sf-received-detail { font-size: 0.82em; color: #6b7280; }
.dim { color: #6b7280; }
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

    agent_names = game_log.get("agent_names", {})

    # Build sections
    header_html = _build_header(game_log)
    rounds_html = "\n".join(_build_round(r, agent_reflections, agent_reasonings, agent_names) for r in rounds)
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
