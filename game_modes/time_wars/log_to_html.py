"""
TIME WARS: generate HTML visualization from JSONL log (unified state: time + mana, full event fields).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_roster_names() -> dict[str, str]:
    path = ROOT / "agents" / "roster.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {a["id"]: a.get("name", a["id"]) for a in data.get("agents", [])}


def _load_role_names() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "roles.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r.get("name", r["id"]) for r in data.get("roles", [])}


def _read_events(jsonl_path: Path) -> list[dict]:
    events = []
    for line in jsonl_path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def _generate_html_content(jsonl_path: Path, events: list[dict], names: dict, role_names: dict) -> str:
    events_js = json.dumps(events, ensure_ascii=False)
    names_js = json.dumps(names, ensure_ascii=False)
    role_names_js = json.dumps(role_names, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TIME WARS — {jsonl_path.stem}</title>
    <style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: #0a0a0a;
    color: #d4d4d4;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 20px;
    max-width: 1000px;
    margin: 0 auto;
}}
.header-block {{ border: 1px solid #2a2a2a; padding: 16px 20px; margin-bottom: 20px; background: #111; }}
h1 {{ color: #f59e0b; font-size: 1.5em; margin-bottom: 8px; letter-spacing: 2px; }}
.meta {{ color: #6b7280; margin-bottom: 8px; font-size: 0.9em; }}
.timer-line {{ color: #7dd3fc; font-size: 1em; margin: 10px 0; padding: 8px 12px; background: #0d0d0d; border-left: 3px solid #3b82f6; }}
.timer-line .tick {{ color: #a3e635; font-weight: bold; }}
.timer-strip {{ display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 12px; font-size: 0.9em; }}
.timer-strip .player {{ background: #1a1a1a; padding: 6px 12px; border-radius: 4px; }}
.timer-strip .player .label {{ color: #9ca3af; }}
.timer-strip .player .time {{ color: #7dd3fc; font-weight: bold; }}
.timer-strip .player .mana {{ color: #a78bfa; }}
.timer-strip .player.winner {{ border: 1px solid #22c55e; }}
.section {{ margin: 20px 0; border: 1px solid #2a2a2a; background: #111; padding: 16px; }}
.section h2 {{ color: #7dd3fc; font-size: 1em; margin-bottom: 12px; letter-spacing: 1px; }}
table.state {{ width: 100%; border-collapse: collapse; font-size: 0.95em; }}
table.state th, table.state td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #2a2a2a; }}
table.state th {{ color: #9ca3af; font-weight: 600; }}
.state .time {{ color: #7dd3fc; }}
.state .mana {{ color: #a78bfa; }}
.roles-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
.role-card {{ background: #1a1a1a; padding: 10px 12px; border-left: 3px solid #374151; }}
.role-card .agent {{ font-weight: bold; color: #a3e635; }}
.role-card .role {{ color: #f59e0b; font-size: 0.9em; }}
.role-card .skills {{ color: #6b7280; font-size: 0.8em; margin-top: 4px; }}
.event {{ padding: 8px 12px; margin: 6px 0; background: #0d0d0d; border-left: 3px solid #374151; font-size: 0.95em; }}
.event-details {{ margin-top: 6px; font-size: 0.85em; color: #9ca3af; }}
.event-details dl {{ display: grid; grid-template-columns: auto 1fr; gap: 2px 12px; }}
.event-details dt {{ color: #6b7280; }}
.event.tick {{ color: #6b7280; font-size: 0.8em; }}
.event.cooperate {{ border-left-color: #22c55e; }}
.event.steal {{ border-left-color: #ef4444; }}
.event.storm {{ border-left-color: #3b82f6; }}
.event.crisis {{ border-left-color: #f59e0b; }}
.event.elimination {{ border-left-color: #6b7280; }}
.event.code_use {{ border-left-color: #a855f7; }}
.event.code_buy {{ border-left-color: #c084fc; }}
.event.skill_trigger {{ border-left-color: #eab308; }}
.event.game_over {{ border-left-color: #eab308; }}
.event.state_snapshot {{ border-left-color: #22d3ee; }}
.event.round_start {{ border-left-color: #0ea5e9; }}
.event.player_intent {{ border-left-color: #8b5cf6; }}
.event.comm_message {{ border-left-color: #0ea5e9; }}
.event.mcs_mood {{ border-left-color: #a855f7; }}
.event .delta {{ color: #a3e635; }}
.event .delta.neg {{ color: #f87171; }}
/* ── COMM block inside round ── */
.comm-block {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid #1e293b; }}
.comm-block h4 {{ color: #6b7280; font-size: 0.82em; letter-spacing: 0.5px; margin-bottom: 6px; }}
.comm-msg {{ font-size: 0.87em; padding: 4px 8px; margin: 2px 0; border-radius: 3px; color: #94a3b8; line-height: 1.5; }}
.comm-msg.ch-public {{ background: #0d1b2e; }}
.comm-msg.ch-dm {{ background: #120a2e; color: #c084fc; }}
.comm-msg .sender {{ font-weight: 700; color: #a3e635; margin-right: 6px; }}
.comm-msg .ch-tag {{ font-size: 0.75em; color: #4b5563; margin-left: 4px; }}
/* ── MCS Mood block inside round ── */
.mood-section {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid #1e293b; }}
.mood-section h4 {{ color: #6b7280; font-size: 0.82em; letter-spacing: 0.5px; margin-bottom: 8px; }}
.mood-row {{ display: flex; align-items: center; gap: 12px; margin: 5px 0; flex-wrap: wrap; }}
.mood-agent {{ color: #a3e635; min-width: 110px; font-weight: 600; font-size: 0.88em; }}
.mood-bars {{ display: flex; gap: 14px; align-items: flex-end; }}
.mood-bar-item {{ display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }}
.mood-bar-label {{ color: #6b7280; font-size: 0.70em; text-transform: uppercase; letter-spacing: 0.4px; }}
.mood-bar-track {{ width: 64px; height: 5px; background: #1e293b; border-radius: 3px; overflow: hidden; }}
.mood-bar-fill {{ height: 100%; border-radius: 3px; }}
.mood-persona {{ font-size: 0.78em; font-style: italic; color: #c084fc; min-width: 80px; }}
.mood-delta-badge {{ font-size: 0.72em; padding: 1px 5px; border-radius: 8px; font-weight: 600; }}
.mood-delta-badge.stable {{ background: #1e293b; color: #4b5563; }}
.mood-delta-badge.shift {{ background: #1c1a07; color: #f59e0b; }}
.mood-delta-badge.explosive {{ background: #2a0d0d; color: #f87171; }}
.round-block {{ margin: 24px 0; border: 1px solid #334155; background: #0f172a; padding: 16px; border-radius: 6px; }}
.round-block h3 {{ color: #38bdf8; font-size: 1.1em; margin-bottom: 10px; }}
.round-timer {{ color: #7dd3fc; margin-bottom: 8px; font-size: 0.95em; }}
.round-situation {{ color: #94a3b8; margin-bottom: 12px; font-style: italic; padding: 6px 10px; background: #1e293b; border-radius: 4px; }}
.players-in-round {{ display: grid; gap: 10px; margin-bottom: 14px; }}
.player-card {{ background: #1e293b; padding: 10px 12px; border-left: 3px solid #475569; border-radius: 4px; }}
.player-card .agent-id {{ font-weight: bold; color: #a3e635; }}
.player-card .stat {{ color: #94a3b8; font-size: 0.9em; margin-top: 4px; }}
.player-card .intent {{ margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155; font-size: 0.9em; color: #cbd5e1; }}
.player-card .intent dd {{ margin-left: 0; margin-top: 2px; }}
.round-outcomes h4 {{ color: #9ca3af; font-size: 0.95em; margin: 10px 0 6px 0; }}
.final-table {{ width: 100%; border-collapse: collapse; }}
.final-table th, .final-table td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #2a2a2a; }}
.final-table .winner {{ border: 1px solid #22c55e; color: #4ade80; }}
.final-table .eliminated .time {{ color: #6b7280; }}
</style>
</head>
<body>
    <div class="header-block">
        <h1>TIME WARS</h1>
        <div class="meta" id="meta"></div>
        <div class="timer-line" id="timer-line"></div>
        <div class="timer-strip" id="timer-strip"></div>
    </div>
    <div class="section"><h2>Початковий стан (час + мана)</h2><div id="initial-state"></div></div>
    <div class="section"><h2>Ролі</h2><div class="roles-grid" id="roles"></div></div>
    <div class="section" id="rounds-section"><h2>Перегляд по раундах (1 хв)</h2><div id="rounds-view"></div></div>
    <div class="section"><h2>Події по тіках (повні поля)</h2><div id="events"></div></div>
    <div class="section"><h2>Фінал (час + мана)</h2><div id="final"></div></div>
    <script>
const events = {events_js};
const NAMES = {names_js};
const ROLE_NAMES = {role_names_js};
function name(aid) {{ return NAMES[aid] || aid; }}
function roleName(rid) {{ return ROLE_NAMES[rid] || rid; }}
const gameStart = events.find(e => e.event_type === "game_start");
document.getElementById("meta").textContent = gameStart ? `Session: ${{gameStart.session_id}} · Старт: ${{gameStart.base_seconds_per_player}} сек/гравець · Тривалість гри: ${{gameStart.duration_limit_sec}} тіків` : "—";
const gameOver = events.find(e => e.event_type === "game_over");
const tickArr = events.filter(e => e.tick != null).map(e => e.tick);
const maxTick = gameOver && gameOver.tick != null ? gameOver.tick : (tickArr.length ? Math.max(...tickArr) : 0);
const duration = gameStart && gameStart.duration_limit_sec != null ? gameStart.duration_limit_sec : 0;
document.getElementById("timer-line").innerHTML = `⏱ Таймер гри: <span class="tick">${{maxTick}}</span> / ${{duration}} тіків (1 тік = 1 сек)${{gameOver && gameOver.winner_id ? ` · Переможець: ${{name(gameOver.winner_id)}}` : ""}}`;
const finalTimes = gameOver && gameOver.final_times ? gameOver.final_times : {{}};
const finalMana = gameOver && gameOver.final_mana ? gameOver.final_mana : {{}};
const winnerId = gameOver && gameOver.winner_id != null ? gameOver.winner_id : null;
const timerEntries = Object.entries(finalTimes).map(([aid, sec]) => [aid, sec, finalMana[aid]]).sort((a, b) => b[1] - a[1]);
document.getElementById("timer-strip").innerHTML = timerEntries.map(([aid, sec, mana]) => `<div class="player ${{winnerId === aid ? "winner" : ""}}"><span class="label">${{name(aid)}}</span> · <span class="time">${{sec}} сек</span> · <span class="mana">${{mana != null ? mana : "—"}} мани</span></div>`).join("");
const snapshot = events.find(e => e.event_type === "state_snapshot");
if (snapshot && snapshot.players && snapshot.players.length) {{
  document.getElementById("initial-state").innerHTML = `<table class="state"><thead><tr><th>Гравець</th><th>Роль</th><th>Час</th><th>Мана</th><th>Статус</th></tr></thead><tbody>${{snapshot.players.map(p => `<tr><td>${{name(p.agent_id)}}</td><td>${{roleName(p.role_id)}}</td><td class="time">${{p.time_remaining_sec}} сек</td><td class="mana">${{p.mana}}</td><td>${{p.status || "active"}}</td></tr>`).join("")}}</tbody></table>`;
}} else {{
  const roles = events.filter(e => e.event_type === "role_assignment");
  const baseSec = gameStart && gameStart.base_seconds_per_player != null ? gameStart.base_seconds_per_player : 90;
  document.getElementById("initial-state").innerHTML = `<table class="state"><thead><tr><th>Гравець</th><th>Роль</th><th>Час</th><th>Мана</th><th>Статус</th></tr></thead><tbody>${{roles.map(r => `<tr><td>${{name(r.agent_id)}}</td><td>${{roleName(r.role_id)}}</td><td class="time">${{baseSec}} сек</td><td class="mana">20</td><td>active</td></tr>`).join("")}}</tbody></table>`;
}}
const roleAssignments = events.filter(e => e.event_type === "role_assignment");
document.getElementById("roles").innerHTML = roleAssignments.map(e => `<div class="role-card"><span class="agent">${{name(e.agent_id)}}</span><div class="role">${{roleName(e.role_id)}}</div><div class="skills">${{(e.skills || []).join(", ")}}</div></div>`).join("");

const roundStarts = events.filter(e => e.event_type === "round_start").sort((a, b) => (a.round_num || 0) - (b.round_num || 0));
const outcomeTypes = ["cooperate", "steal", "code_buy", "code_use", "storm", "crisis", "elimination", "skill_trigger"];
if (roundStarts.length > 0) {{
  const roundsHtml = roundStarts.map(rs => {{
    const tick = rs.tick;
    const roundNum = rs.round_num != null ? rs.round_num : (tick ? Math.floor(tick / 15) : 0);
    const timerSec = rs.game_timer_sec != null ? rs.game_timer_sec : tick;
    let situationStr = "—";
    if (rs.situation_tie === true) {{
      situationStr = "Усі по " + (rs.situation_leader_time_sec != null ? rs.situation_leader_time_sec : 0) + " сек.";
    }} else if (rs.situation_leader_id != null && rs.situation_leader_id !== "") {{
      const belowThresh = rs.situation_below_threshold || 60;
      situationStr = "Лідер: " + name(rs.situation_leader_id) + " (" + (rs.situation_leader_time_sec != null ? rs.situation_leader_time_sec : 0) + " сек). " + (rs.situation_below_count || 0) + " гравців нижче " + belowThresh + " сек.";
    }} else if (rs.situation) {{
      situationStr = rs.situation;
    }}
    const timerLine = duration > 0 ? "⏱ Таймер: " + timerSec + " / " + duration + " сек · Залишилось: " + (duration - timerSec) + " сек" : "⏱ Таймер: " + timerSec + " сек (тік " + tick + ")";
    const players = rs.players || [];
    const intents = events.filter(e => e.event_type === "player_intent" && e.tick === tick);
    const intentByAgent = {{}};
    intents.forEach(e => {{ intentByAgent[e.agent_id] = e; }});
    const outcomes = events.filter(e => outcomeTypes.includes(e.event_type) && e.tick === tick);
    const commMsgs = events.filter(e => e.event_type === "comm_message" && e.round_num === roundNum);
    const moodEvs  = events.filter(e => e.event_type === "mcs_mood"     && e.round_num === roundNum);
    const playersHtml = players.map(p => {{
      const intent = intentByAgent[p.agent_id];
      const thought = intent && intent.thought ? intent.thought : "";
      const plan = intent && intent.plan ? intent.plan : "";
      const choice = intent && intent.choice ? intent.choice : "";
      const reason = intent && intent.reason ? intent.reason : "";
      let intentHtml = "";
      if (thought || plan || choice || reason) {{
        intentHtml = `<div class="intent"><dl><dt>Думки</dt><dd>${{thought || "—"}}</dd><dt>План</dt><dd>${{plan || "—"}}</dd><dt>Вибір</dt><dd>${{choice || "—"}}</dd><dt>Чому</dt><dd>${{reason || "—"}}</dd></dl></div>`;
      }}
      return `<div class="player-card"><span class="agent-id">${{name(p.agent_id)}}</span><div class="stat">Час: ${{p.time_remaining_sec}} сек · Мана: ${{p.mana != null ? p.mana : "—"}} · ${{p.status || "active"}}</div>${{intentHtml}}</div>`;
    }}).join("");
    let outcomesHtml = "";
    if (outcomes.length > 0) {{
      outcomesHtml = outcomes.map(e => {{
        let text = "";
        if (e.event_type === "cooperate") {{
          text = "🤝 " + name(e.actor_id) + " кооперує з " + name(e.target_id) + " — обом +" + (e.time_delta_seconds != null ? e.time_delta_seconds : 30) + " сек";
          if (e.mana_actor_after != null && e.mana_target_after != null) text += " · мана після: " + name(e.actor_id) + "=" + e.mana_actor_after + ", " + name(e.target_id) + "=" + e.mana_target_after;
        }} else if (e.event_type === "steal" && !e.target_effect) {{
          const d = e.time_delta_seconds;
          const sign = d >= 0 ? "+" : "";
          text = "🎭 " + name(e.actor_id) + " вкрав у " + name(e.target_id) + " — " + (e.outcome || "") + " (roll " + (e.roll || "?") + ") " + sign + d + " сек";
          if (e.mana_actor_after != null) text += " · мана після: " + e.mana_actor_after;
        }} else if (e.event_type === "steal" && e.target_effect) {{
          text = "   → " + name(e.target_id) + " " + (e.time_delta_seconds || 0) + " сек";
        }} else if (e.event_type === "code_buy") {{
          text = "🛒 " + name(e.agent_id) + " купив " + (e.code_id || "") + " за " + (e.cost_mana != null ? e.cost_mana : 0) + " мани";
          if (e.mana_after != null) text += " · мана після: " + e.mana_after;
        }} else if (e.event_type === "code_use") {{
          const codeInfo = e.choice_id ? (e.code_id || "") + " (" + e.choice_id + ")" : (e.code_id || "");
          text = "📦 " + name(e.actor_id) + " використав код " + codeInfo;
          if (e.time_delta_seconds != null) text += " собі " + (e.time_delta_seconds >= 0 ? "+" : "") + e.time_delta_seconds + " сек";
          if (e.target_delta_seconds != null && e.target_id) text += " → " + name(e.target_id) + " " + (e.target_delta_seconds >= 0 ? "+" : "") + e.target_delta_seconds + " сек";
          if (e.mana_actor_after != null) text += " · мана: " + e.mana_actor_after;
        }} else if (e.event_type === "storm") text = "⛈ Шторм: всі " + (e.time_delta_seconds || 0) + " сек";
        else if (e.event_type === "crisis") text = "⚠ Криза: хто < " + (e.threshold_seconds || 60) + " сек → " + (e.time_delta_seconds || 0) + " сек";
        else if (e.event_type === "elimination") text = "💀 " + name(e.target_id) + " вибув";
        else if (e.event_type === "skill_trigger") text = "⚡ " + name(e.actor_id) + " " + (e.skill_id || "") + " +" + (e.time_delta_seconds || 0) + " сек";
        else text = e.event_type + " " + JSON.stringify(e);
        return `<div class="event ${{e.event_type}}">${{text}}</div>`;
      }}).join("");
      outcomesHtml = `<div class="round-outcomes"><h4>Наслідки раунду</h4><div>${{outcomesHtml}}</div></div>`;
    }}
    // ── COMM messages block ──────────────────────────────────────────────
    let commHtml = "";
    if (commMsgs.length > 0) {{
      const msgs = commMsgs.map(m => {{
        const ch = m.channel || "public";
        const isDm = ch.startsWith("dm_");
        const chClass = isDm ? "ch-dm" : "ch-public";
        const chTag = isDm ? `<span class="ch-tag">[DM]</span>` : `<span class="ch-tag">[pub]</span>`;
        const text = (m.text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return `<div class="comm-msg ${{chClass}}"><span class="sender">${{name(m.sender_id || m.sender_id_name || "")}}</span>${{chTag}} ${{text}}</div>`;
      }}).join("");
      commHtml = `<div class="comm-block"><h4>Діалог (COMM)</h4>${{msgs}}</div>`;
    }}
    // ── MCS Mood block ───────────────────────────────────────────────────
    let moodHtml = "";
    if (moodEvs.length > 0) {{
      function renderMoodBar(label, value, color) {{
        const pct = Math.round((value || 0) * 100);
        return `<div class="mood-bar-item"><span class="mood-bar-label">${{label}}</span><div class="mood-bar-track"><div class="mood-bar-fill" style="width:${{pct}}%;background:${{color}}"></div></div></div>`;
      }}
      const moodRows = moodEvs.map(m => {{
        const bars = [
          renderMoodBar("енергія", m.energy || 0, "#22c55e"),
          renderMoodBar("страх",   m.fear    || 0, "#ef4444"),
          renderMoodBar("напруга", m.tension || 0, "#f59e0b"),
        ].join("");
        const deltaClass = m.delta || "stable";
        return `<div class="mood-row"><span class="mood-agent">${{name(m.agent_id)}}</span><div class="mood-bars">${{bars}}</div><span class="mood-persona">${{m.persona || ""}}</span><span class="mood-delta-badge ${{deltaClass}}">${{deltaClass}}</span></div>`;
      }}).join("");
      moodHtml = `<div class="mood-section"><h4>MCS Mood</h4>${{moodRows}}</div>`;
    }}
    return `<div class="round-block" id="round-${{roundNum}}"><h3>Раунд ${{roundNum}}</h3><div class="round-timer">${{timerLine}}</div><div class="round-situation">${{situationStr}}</div><div class="players-in-round">${{playersHtml}}</div>${{outcomesHtml}}${{commHtml}}${{moodHtml}}</div>`;
  }}).join("");
  document.getElementById("rounds-view").innerHTML = roundsHtml;
}} else {{
  document.getElementById("rounds-section").style.display = "none";
}}

const eventTypesToShow = ["cooperate", "steal", "code_buy", "code_use", "storm", "crisis", "elimination", "skill_trigger", "game_over", "comm_message", "mcs_mood"];
const otherEvents = events.filter(e => eventTypesToShow.includes(e.event_type) || (e.event_type === "steal" && e.target_effect));
function rawFields(e) {{ const skip = ["event_type", "timestamp"]; return Object.entries(e).filter(([k]) => !skip.includes(k)).map(([k, v]) => `<dt>${{k}}</dt><dd>${{typeof v === "object" ? JSON.stringify(v) : v}}</dd>`).join(""); }}
let lastTick = -1;
document.getElementById("events").innerHTML = otherEvents.map(e => {{
  const tickStr = e.tick != null ? `Tick ${{e.tick}}` : "";
  const sameTick = e.tick === lastTick;
  lastTick = e.tick != null ? e.tick : lastTick;
  let html = tickStr && !sameTick ? `<div class="event tick">——— ${{tickStr}} ———</div>` : "";
  let text = "";
  if (e.event_type === "cooperate") {{ text = `🤝 ${{name(e.actor_id)}} кооперує з ${{name(e.target_id)}} <span class="delta">+${{e.time_delta_seconds}} сек</span>`; if (e.mana_actor_after != null) text += ` · мана після: ${{e.actor_id}}=${{e.mana_actor_after}}, ${{e.target_id}}=${{e.mana_target_after}}`; if (e.trust_actor_target != null) text += ` · довіра A→T=${{e.trust_actor_target}}, T→A=${{e.trust_target_actor}}`; }}
  else if (e.event_type === "steal" && !e.target_effect) {{ const d = e.time_delta_seconds; const spanClass = d >= 0 ? "delta" : "delta neg"; const sign = d >= 0 ? "+" : ""; text = `🎭 ${{name(e.actor_id)}} вкрав у ${{name(e.target_id)}} — ${{e.outcome || ""}} (roll ${{e.roll || "?"}}) <span class="${{spanClass}}">${{sign}}${{d}} сек</span>`; if (e.mana_actor_after != null) text += ` · мана після: ${{e.mana_actor_after}}`; if (e.skill_triggered && e.skill_triggered.length) text += ` · skills: ${{e.skill_triggered.join(", ")}}`; }}
  else if (e.event_type === "steal" && e.target_effect) text = `   → ${{name(e.target_id)}} <span class="delta neg">${{e.time_delta_seconds}} сек</span>`;
  else if (e.event_type === "code_buy") text = `🛒 ${{name(e.agent_id)}} купив код ${{e.code_id}} за ${{e.cost_mana}} мани · мана після: ${{e.mana_after}}`;
  else if (e.event_type === "code_use") {{ const codeInfo = e.choice_id ? `${{e.code_id}} (${{e.choice_id}})` : (e.code_id || ""); const selfD = e.time_delta_seconds != null ? `<span class="delta">${{e.time_delta_seconds >= 0 ? "+" : ""}}${{e.time_delta_seconds}} сек</span>` : ""; let targetD = ""; if (e.target_id === "all" && e.target_delta_seconds != null) {{ targetD = ` → всі <span class="delta">${{e.target_delta_seconds >= 0 ? "+" : ""}}${{e.target_delta_seconds}} сек</span>`; }} else if (e.target_id && e.target_delta_seconds != null) {{ targetD = ` → ${{name(e.target_id)}} <span class="delta">${{e.target_delta_seconds >= 0 ? "+" : ""}}${{e.target_delta_seconds}} сек</span>`; }} text = `📦 ${{name(e.actor_id)}} використав код ${{codeInfo}} ${{selfD}}${{targetD}}`; if (e.mana_actor_after != null) text += ` · мана: ${{e.mana_actor_after}}`; }}
  else if (e.event_type === "storm") text = `⛈ Шторм: всі <span class="delta neg">${{e.time_delta_seconds}} сек</span>`;
  else if (e.event_type === "crisis") text = `⚠ Криза: хто < ${{e.threshold_seconds}} сек → <span class="delta neg">${{e.time_delta_seconds}} сек</span>`;
  else if (e.event_type === "elimination") text = `💀 ${{name(e.target_id)}} вибув`;
  else if (e.event_type === "skill_trigger") text = `⚡ ${{name(e.actor_id)}} ${{e.skill_id}} <span class="delta">+${{e.time_delta_seconds}} сек</span>`;
  else if (e.event_type === "game_over") text = `🏁 Гра завершена. Переможець: ${{e.winner_id ? name(e.winner_id) : "—"}}`;
  else if (e.event_type === "comm_message") {{
    const isDm = (e.channel || "").startsWith("dm_");
    const msgText = (e.text || "").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const chLabel = isDm ? "[DM]" : "[pub]";
    text = `💬 <b style="color:#a3e635">${{name(e.sender_id || "")}}</b> <span style="color:#4b5563;font-size:0.8em">${{chLabel}}</span> ${{msgText}}`;
  }}
  else if (e.event_type === "mcs_mood") {{
    const en = e.energy != null ? Math.round(e.energy * 100) : "?";
    const fe = e.fear   != null ? Math.round(e.fear   * 100) : "?";
    const te = e.tension!= null ? Math.round(e.tension* 100) : "?";
    const deltaColor = e.delta === "explosive" ? "#f87171" : e.delta === "shift" ? "#f59e0b" : "#4b5563";
    text = `🧠 <b style="color:#a3e635">${{name(e.agent_id)}}</b> · персона: <span style="color:#c084fc">${{e.persona || "—"}}</span> · енергія: <span style="color:#22c55e">${{en}}%</span> · страх: <span style="color:#ef4444">${{fe}}%</span> · напруга: <span style="color:#f59e0b">${{te}}%</span> <span style="color:${{deltaColor}};font-size:0.8em">[${{e.delta || "stable"}}]</span>`;
  }}
  else text = JSON.stringify(e);
  html += `<div class="event ${{e.event_type}}"><div>${{text}}</div><div class="event-details"><dl>${{rawFields(e)}}</dl></div></div>`;
  return html;
}}).join("");
const entries = Object.entries(finalTimes).map(([aid, sec]) => [aid, sec, finalMana[aid]]).sort((a, b) => b[1] - a[1]);
document.getElementById("final").innerHTML = `<table class="final-table"><thead><tr><th>Гравець</th><th>Час</th><th>Мана</th></tr></thead><tbody>${{entries.map(([aid, sec, mana]) => `<tr class="${{winnerId === aid ? "winner" : ""}} ${{sec === 0 ? "eliminated" : ""}}"><td>${{name(aid)}}</td><td class="time">${{sec}} сек</td><td class="mana">${{mana != null ? mana : "—"}}</td></tr>`).join("")}}</tbody></table>`;
</script>
</body>
</html>
"""


def generate_time_wars_html(jsonl_path: Path) -> Path:
    """Read JSONL, generate HTML with full event viz and state (time + mana). Return path to written HTML."""
    events = _read_events(jsonl_path)
    names = _load_roster_names()
    role_names = _load_role_names()
    html = _generate_html_content(jsonl_path, events, names, role_names)
    out_path = jsonl_path.with_suffix(".html")
    out_path.write_text(html, encoding="utf-8")
    return out_path
