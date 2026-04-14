"""
dialog_engine.py

LLM-powered dialog generation for the social phase.

Before each round, agents send messages to:
  - Public lobby (all hear it)
  - Private DM to one other agent (limited: 1 DM per round per agent)

The LLM generates what each agent says based on:
  - SOUL.md (personality)
  - STATES.md (current emotional state)
  - MEMORY.json summary (what happened before)
  - Visible actions from previous rounds
  - deceptionTendency — how likely the agent is to lie

Активний генератор: generate_round_dialog_flat (flat mode, 1 pub + 1 DM per agent).
"""

from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Імпортуємо спільну утиліту з pipeline — ВИС-1: виключаємо дублікат
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.utils import _cooperation_val

# Lazy import of talk_transition to avoid circular deps at module level
# (pipeline modules import state_machine which doesn't import dialog_engine)
def _get_talk_transition():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.talk_transition import classify_tone, sample_talk_outcome, apply_talk_outcome, topic_tension_delta, Tone
    return classify_tone, sample_talk_outcome, apply_talk_outcome, topic_tension_delta, Tone


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DialogMessage:
    sender_id: str
    channel: str          # "public" | "dm_{target_id}"
    text: str
    is_deceptive: bool = False
    round_number: int = 0

    def to_dict(self) -> dict:
        return {
            "sender": self.sender_id,
            "channel": self.channel,
            "text": self.text,
            "round": self.round_number,
        }


@dataclass
class RoundDialog:
    round_number: int
    messages: List[DialogMessage] = field(default_factory=list)
    # {agent_id: dominant tone received this round — for RoundOutcome.dialog_signals}
    talk_signals: Dict[str, str] = field(default_factory=dict)

    def public_messages(self) -> List[DialogMessage]:
        return [m for m in self.messages if m.channel == "public"]

    def dm_for(self, agent_id: str) -> List[DialogMessage]:
        return [m for m in self.messages if m.channel == f"dm_{agent_id}"]

    def visible_to(self, agent_id: str) -> List[DialogMessage]:
        return [
            m for m in self.messages
            if m.channel == "public" or m.channel == f"dm_{agent_id}"
        ]

    def to_dict(self) -> dict:
        return {
            "round": self.round_number,
            "messages": [m.to_dict() for m in self.messages],
            "talk_signals": self.talk_signals,
        }


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_DIALOG_SYSTEM = """You are generating dialog for an agent in a social simulation.
The setting: a private rave. Four people in a room. In a moment they will each make a decision.

Write what this agent says out loud — one or two sentences maximum.
Ukrainian language only.

Rules:
- First person
- Specific, grounded — no abstraction
- Match the mood: paranoid agents speak differently than confident ones
- If deception_flag is true — the agent says something that hides their real intention
- No exclamation marks, no theatrical language
- Sound like a real person in a tense social situation

Return ONLY the dialog text. Nothing else."""

_DM_SYSTEM = """You are generating a private message from one agent to another in a social simulation.
This message is heard only by the recipient.
Ukrainian language only. One sentence.

This is a private channel — agents can be more direct, make promises, or threaten quietly.
If deception_flag is true — the agent is setting up a trap.

Return ONLY the message text. Nothing else."""

DIALOG_RULES = """\
Rules:
- Speak in FIRST PERSON only. Never describe yourself in third person.
- Ukrainian language. Use the other people's NAMES — not agent IDs or codes.
- 2–4 sentences maximum (40–80 words). No monologues.
- Sound like a real person in a tense social situation — not a narrator.
- No theatrical language, no exclamation marks, no "Dear friend" openers.
- If you suspect someone — you may hint at it without accusing directly.
- If you intend to betray — keep that hidden from your words.
- NEVER start with "Я:", "Агент:", your own name, or any header.
Return ONLY the spoken text. Nothing else."""

_STEP_SYSTEM_TEMPLATE = """You are {display_name}. You are a real person at a private gathering.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

{dialog_rules}

Speak in first person. Ukrainian language. Use people's NAMES — not codes or IDs.
You may write 2–4 sentences (40–80 words). Build your reply as you see fit — you have freedom.
Your TONE should reflect your current mood and situation:
  - hostile/fearful → you may show anger, suspicion, coldness
  - confident/dominant → you may sound assured, even a bit sharp
  - If someone betrayed you recently → you may show hurt, disappointment, or controlled anger
Do not sound robotic or technical. Add personality, emotion, variety. Sound like a real person.
Return ONLY your spoken text. Nothing else."""


def _build_context(
    soul_md: str,
    states_md: str,
    memory_summary: dict,
    deception_tendency: float,
    round_number: int,
    total_rounds: int,
    visible_history: dict,
    memory_narrative: str = "",
) -> str:
    rounds_left = total_rounds - round_number
    deception_flag = deception_tendency > 60
    mem_block = memory_narrative.strip() if memory_narrative else json.dumps(memory_summary, ensure_ascii=False)[:300]
    return (
        f"AGENT PROFILE:\n{soul_md[:800]}\n\n"
        f"CURRENT STATE:\n{states_md}\n\n"
        f"MEMORY:\n{mem_block}\n\n"
        f"Round {round_number}/{total_rounds}. {rounds_left} rounds left.\n"
        f"Deception tendency: {deception_tendency:.0f}/100.\n"
        + ("DECEPTION FLAG: agent is likely misdirecting.\n" if deception_flag else "")
        + f"Visible actions: {json.dumps(visible_history, ensure_ascii=False)[:200] if visible_history else 'none'}"
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call(system: str, user: str, model: str, max_tokens: int = 220) -> str:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.seed_generator import call_openrouter
    return call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.88,
        max_tokens=max_tokens,
        timeout=45,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_public_message(
    agent_id: str,
    soul_md: str,
    states_md: str,
    memory_summary: dict,
    deception_tendency: float,
    round_number: int,
    total_rounds: int,
    visible_history: dict,
    model: str = "x-ai/grok-3-mini",
) -> DialogMessage:
    ctx = _build_context(
        soul_md, states_md, memory_summary,
        deception_tendency, round_number, total_rounds, visible_history,
    )
    text = _call(_DIALOG_SYSTEM, ctx, model)
    return DialogMessage(
        sender_id=agent_id,
        channel="public",
        text=text.strip(),
        is_deceptive=deception_tendency > 60,
        round_number=round_number,
    )


def generate_dm(
    sender_id: str,
    target_id: str,
    soul_md: str,
    states_md: str,
    memory_summary: dict,
    deception_tendency: float,
    round_number: int,
    total_rounds: int,
    model: str = "x-ai/grok-3-mini",
) -> DialogMessage:
    deception_flag = deception_tendency > 60
    system = _STEP_SYSTEM_TEMPLATE.format(
        agent_id=sender_id,
        soul_md=soul_md[:900],
        dialog_rules=DIALOG_RULES,
    )
    if deception_flag:
        system += "\nYou are writing a private message. You may use it to deceive or set a trap."
    else:
        system += "\nYou are writing a private message. Be direct — only this person will read it."

    mem_short = ""
    if memory_summary:
        betrayals = memory_summary.get("total_betrayals_received", 0)
        mem_short = f"You've been betrayed {betrayals}x total."

    user = (
        f"Round {round_number}/{total_rounds}. "
        f"Write one private sentence to {target_id}.\n"
        + (f"{mem_short}\n" if mem_short else "")
        + "Speak now:"
    )
    text = _call(system, user, model)
    return DialogMessage(
        sender_id=sender_id,
        channel=f"dm_{target_id}",
        text=text.strip(),
        is_deceptive=deception_flag,
        round_number=round_number,
    )


# ---------------------------------------------------------------------------
# Flat dialog model (simplified: 1 public + 1 DM per agent per round)
# ---------------------------------------------------------------------------

def _cooperation_val(val) -> float:
    """Extract cooperation from legacy float or per-dim dict."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5


def _format_last_round(summary: dict) -> str:
    """Convert last_round_summary dict to a compact human-readable string."""
    payoff = summary.get("payoff", 0.0)
    received = summary.get("received", {})
    given = summary.get("given", {})

    def _action_label(v: float) -> str:
        if v <= 0.15:
            return "betrayed you (0.0)"
        if v <= 0.45:
            return f"soft-defected ({v:.2f})"
        if v <= 0.75:
            return f"soft-cooperated ({v:.2f})"
        return f"fully cooperated ({v:.2f})"

    def _gave_label(v: float) -> str:
        if v <= 0.15:
            return "you betrayed"
        if v <= 0.45:
            return "you soft-defected"
        if v <= 0.75:
            return "you soft-cooperated"
        return "you fully cooperated"

    parts = [f"you earned {payoff:+.1f} pts."]
    for aid, val in received.items():
        v = _cooperation_val(val)
        short = aid.split("_")[-1][:8]
        parts.append(f"{short} {_action_label(v)}")
    for aid, val in given.items():
        v = _cooperation_val(val)
        short = aid.split("_")[-1][:8]
        parts.append(f"{_gave_label(v)} with {short} ({v:.2f})")
    return " ".join(parts)


def _dn(agent_id: str, names: dict) -> str:
    """Return display name for agent_id, fallback to short tail of ID."""
    return names.get(agent_id) or agent_id.split("_")[-1][:8]


def _get_betrayers_from_last_round(summary: dict, names: dict) -> List[str]:
    """Return display names of agents who betrayed you last round (value <= 0.15)."""
    if not summary:
        return []
    received = summary.get("received", {})
    betrayers = []
    for aid, val in received.items():
        if _cooperation_val(val) <= 0.15:
            betrayers.append(_dn(aid, names))
    return betrayers


def _build_flat_public_context(
    cfg: dict,
    round_number: int,
    all_public_so_far: List[DialogMessage],
    agent_names: dict = None,
) -> tuple:
    """Build (system, user) prompts for a flat public message."""
    import re
    names = agent_names or {}

    soul_md = cfg.get("soul_md", "")
    states_md = cfg.get("states_md", "")
    memory_summary = cfg.get("memory_summary", {})
    deception_tendency = cfg.get("deception_tendency", 50)
    total_rounds = cfg.get("total_rounds", 20)
    agent_id = cfg["agent_id"]
    display_name = _dn(agent_id, names)
    deception_flag = deception_tendency > 60

    system = _STEP_SYSTEM_TEMPLATE.format(
        display_name=display_name,
        soul_md=soul_md[:900],
        dialog_rules=DIALOG_RULES,
    )
    if deception_flag:
        system += "\nYou are hiding your real intentions. Seem calm and cooperative."

    # Compact state
    mood_match = re.search(r"mood:\s*(\w+)", states_md)
    mood = mood_match.group(1) if mood_match else "neutral"

    # Memory: narrative (from memory_summary_to_narrative) or fallback to short stats
    memory_narrative = cfg.get("memory_narrative", "").strip()
    if memory_narrative:
        mem_block = f"Твоя пам'ять (підсумок): {memory_narrative}"
    else:
        betrayals = memory_summary.get("total_betrayals_received", 0)
        coops = memory_summary.get("total_cooperations_received", 0)
        mem_block = f"Betrayed {betrayals}x, helped {coops}x." if (betrayals or coops) else ""

    bio_block = ""
    if cfg.get("bio", "").strip():
        bio_block = f"Твоя біографія (коротко): {cfg['bio'].strip()[:500]}\n"

    # Last round concrete actions/outcomes (what actually happened)
    last_round_summary = cfg.get("last_round_summary")
    last_round_text = _format_last_round(last_round_summary) if last_round_summary else ""
    betrayers = _get_betrayers_from_last_round(last_round_summary, names) if last_round_summary else []
    betrayal_hint = ""
    if betrayers:
        betrayers_str = ", ".join(betrayers)
        betrayal_hint = f"Last round {betrayers_str} betrayed you. You may show emotion — hurt, disappointment, or controlled anger — if it fits your character.\n"

    # Storytell — situation and agent's reaction (if present)
    situation_block = ""
    situation_text = cfg.get("situation_text", "")
    situation_reflection = cfg.get("situation_reflection", "")
    story_context = cfg.get("story_context", "")
    if situation_text or situation_reflection:
        situation_block = "SITUATION OF THIS ACT:\n"
        if story_context:
            situation_block += f"Context: {story_context[:200]}...\n"
        if situation_text:
            situation_block += f"{situation_text[:400]}{'...' if len(situation_text) > 400 else ''}\n"
        if situation_reflection:
            situation_block += f'Your reaction: "{situation_reflection}"\n'
        situation_block += "\n"

    # What others have already said this round — framed as competition, not consensus
    others_context = ""
    if all_public_so_far:
        others_context = "Others already spoke:\n"
        for prev in all_public_so_far:
            sender_disp = _dn(prev.sender_id, names)
            others_context += f'  {sender_disp}: "{prev.text[:70]}"\n'
        others_context += (
            "Do NOT echo, agree, or repeat what they said. "
            "React with YOUR own angle — challenge, probe, warn, or contradict if it serves you. "
            "Show your character.\n"
        )

    user = (
        f"Round {round_number}/{total_rounds}. Your mood: {mood}.\n"
        + (bio_block if bio_block else "")
        + (situation_block if situation_block else "")
        + (f"{mem_block}\n" if mem_block else "")
        + (f"Last round: {last_round_text}\n" if last_round_text else "")
        + (betrayal_hint if betrayal_hint else "")
        + (others_context if others_context else "")
        + "Everyone will now make their decision — cooperate or betray — toward each other.\n"
        "This is your ONE public statement before that happens.\n"
        "Use it strategically: signal an alliance, warn a betrayer, bluff about your intentions, "
        "or probe who you can trust. What you say here shapes what others decide.\n"
        "Write 2–4 sentences (40–80 words). First person. Ukrainian. Vary your tone by mood and situation."
    )
    return system, user


def _apply_flat_talk_signals(
    dialog: RoundDialog,
    agent_configs: List[dict],
) -> None:
    """
    Post-process all public messages in the flat dialog:
    classify each speaker's apparent tone and update talk_signals for all listeners.
    The dominant tone across all messages wins for each listener.
    """
    classify_tone, sample_talk_outcome, apply_talk_outcome, topic_tension_delta, Tone = _get_talk_transition()

    agent_ids = [cfg["agent_id"] for cfg in agent_configs]
    public_msgs = [m for m in dialog.messages if m.channel == "public"]

    if not public_msgs:
        return

    # Accumulate outcome counts per listener
    outcome_counts: Dict[str, Dict[str, int]] = {a: {} for a in agent_ids}

    for msg in public_msgs:
        apparent_tone = classify_tone(msg.text, is_deceptive=False)
        for listener_id in agent_ids:
            if listener_id == msg.sender_id:
                continue
            listener_cfg = next((c for c in agent_configs if c["agent_id"] == listener_id), {})
            listener_mood = ""
            states_md = listener_cfg.get("states_md", "")
            import re
            mood_match = re.search(r"mood:\s*(\w+)", states_md)
            if mood_match:
                listener_mood = mood_match.group(1)
            listener_tone = classify_tone(listener_mood, is_deceptive=False)
            outcome = sample_talk_outcome(apparent_tone, listener_tone)
            signal = _outcome_to_signal(outcome)
            outcome_counts[listener_id][signal] = outcome_counts[listener_id].get(signal, 0) + 1

    # Also process DM messages — aggressive DMs signal the target directly
    dm_msgs = [m for m in dialog.messages if m.channel.startswith("dm_")]
    for msg in dm_msgs:
        apparent_tone = classify_tone(msg.text, is_deceptive=False)
        if apparent_tone in (Tone.AGGRESSIVE,):
            # Extract target from channel "dm_{target_id}"
            target_id = msg.channel[3:]
            if target_id in outcome_counts:
                outcome_counts[target_id]["threatening"] = outcome_counts[target_id].get("threatening", 0) + 2

    # Assign dominant signal per listener
    for listener_id, counts in outcome_counts.items():
        if counts:
            dominant = max(counts, key=counts.get)
            dialog.talk_signals[listener_id] = dominant


def _log(msg: str, verbose: bool) -> None:
    if verbose:
        import sys
        print(msg, flush=True, file=sys.stderr)


def generate_round_dialog_flat(
    round_number: int,
    agent_configs: List[dict],
    model: str = "x-ai/grok-3-mini",
    agent_names: dict = None,
    verbose: bool = False,
) -> RoundDialog:
    """
    Flat dialog generation for one round with optional verbose per-call logging.

    Phase 1 (public) is sequential — each agent sees prior messages.
    Phase 2 (DM) and Phase 3 (DM reply) run in parallel via asyncio.to_thread.

    agent_names: {agent_id: display_name} — so agents use real names.
    verbose: if True, print per-call timing to stderr in real time.
    """
    import time
    import asyncio
    import threading

    names = agent_names or {}
    dialog = RoundDialog(round_number=round_number)
    public_messages: List[DialogMessage] = []
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    # Phase 1 — public messages (sequential: each agent sees prior ones)
    # ------------------------------------------------------------------
    _log(f"  [dialog r{round_number}] phase1: public messages (sequential)", verbose)
    for cfg in agent_configs:
        display_name = _dn(cfg["agent_id"], names)
        system, user = _build_flat_public_context(cfg, round_number, public_messages, names)
        agent_model = cfg.get("model", model)
        t0 = time.time()
        _log(f"    [pub]  {display_name}...", verbose)
        try:
            text = _call(system, user, agent_model)
        except Exception as _e:
            _log(f"    [pub]  {display_name} ERROR: {_e}", verbose)
            text = "..."
        elapsed = time.time() - t0
        _log(f"    [pub]  {display_name} done ({elapsed:.1f}s): \"{text.strip()[:60]}\"", verbose)
        msg = DialogMessage(
            sender_id=cfg["agent_id"],
            channel="public",
            text=text.strip(),
            is_deceptive=cfg.get("deception_tendency", 50) > 60,
            round_number=round_number,
        )
        dialog.messages.append(msg)
        public_messages.append(msg)

    # ------------------------------------------------------------------
    # Phase 2 — DM messages (parallel — all agents write DMs at once)
    # ------------------------------------------------------------------
    _log(f"  [dialog r{round_number}] phase2: DMs (parallel)", verbose)

    def _build_dm_call(cfg, pub_msgs_snapshot):
        dm_target = cfg.get("dm_target")
        if not dm_target:
            return None
        deception_tendency = cfg.get("deception_tendency", 50)
        deception_flag = deception_tendency > 60
        soul_md = cfg.get("soul_md", "")
        memory_summary = cfg.get("memory_summary", {})
        display_name = _dn(cfg["agent_id"], names)
        target_display = _dn(dm_target, names)

        system = _STEP_SYSTEM_TEMPLATE.format(
            display_name=display_name,
            soul_md=soul_md[:900],
            dialog_rules=DIALOG_RULES,
        )
        system += (
            "\nYou are writing privately. You may use this to deceive or set a trap."
            if deception_flag
            else "\nYou are writing privately. Be direct — only this person will read it."
        )
        system += "\nDo NOT start your message with 'Приватне повідомлення', agent names, headers, or any prefix. Write ONLY the message content."

        betrayals = memory_summary.get("total_betrayals_received", 0)
        mem_short = f"You've been betrayed {betrayals}x total." if betrayals else ""

        public_context = ""
        for pub in pub_msgs_snapshot:
            if pub.sender_id != cfg["agent_id"]:
                public_context += f'\n{_dn(pub.sender_id, names)} said publicly: "{pub.text}"'

        user_prompt = (
            f"Round {round_number}/{cfg.get('total_rounds', 20)}.\n"
            + (f"{mem_short}\n" if mem_short else "")
            + (f"What was said publicly:{public_context}\n" if public_context else "")
            + f"You have a private channel to {target_display} — they will read this before making their decision.\n"
            "You can: make a deal, threaten quietly, deceive, ask for alliance, or warn.\n"
            "Write 1–3 sentences (20–60 words). Ukrainian. Be natural — add personality, emotion if it fits."
        )
        return cfg["agent_id"], dm_target, display_name, target_display, deception_flag, system, user_prompt, cfg.get("model", model)

    dm_results: List[DialogMessage] = []

    def _run_dm(params):
        aid, dm_target, display_name, target_display, deception_flag, system, user_prompt, agent_model = params
        t0 = time.time()
        _log(f"    [dm]   {display_name} → {target_display}...", verbose)
        try:
            dm_text = _call(system, user_prompt, agent_model)
        except Exception as _e:
            _log(f"    [dm]   {display_name} → {target_display} ERROR: {_e}", verbose)
            dm_text = "..."
        elapsed = time.time() - t0
        _log(f"    [dm]   {display_name} → {target_display} done ({elapsed:.1f}s): \"{dm_text.strip()[:60]}\"", verbose)
        return DialogMessage(
            sender_id=aid,
            channel=f"dm_{dm_target}",
            text=dm_text.strip(),
            is_deceptive=deception_flag,
            round_number=round_number,
        )

    pub_snapshot = list(public_messages)
    dm_params = [_build_dm_call(cfg, pub_snapshot) for cfg in agent_configs]
    dm_params = [p for p in dm_params if p is not None]

    if dm_params:
        async def _gather_dms():
            return await asyncio.gather(
                *[asyncio.to_thread(_run_dm, p) for p in dm_params]
            )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        dm_results = loop.run_until_complete(_gather_dms())
        for dm_msg in dm_results:
            dialog.messages.append(dm_msg)

    # ------------------------------------------------------------------
    # Phase 3 — DM replies (parallel — each recipient replies at once)
    # ------------------------------------------------------------------
    _log(f"  [dialog r{round_number}] phase3: DM replies (parallel)", verbose)

    def _build_reply_call(cfg):
        agent_id = cfg["agent_id"]
        received_dms = [m for m in dialog.messages if m.channel == f"dm_{agent_id}"]
        if not received_dms:
            return None
        dm_in = received_dms[-1]
        soul_md = cfg.get("soul_md", "")
        deception_tendency = cfg.get("deception_tendency", 50)
        deception_flag = deception_tendency > 60
        display_name = _dn(agent_id, names)
        sender_display = _dn(dm_in.sender_id, names)

        system = _STEP_SYSTEM_TEMPLATE.format(
            display_name=display_name,
            soul_md=soul_md[:900],
            dialog_rules=DIALOG_RULES,
        )
        system += "\nYou are writing a private reply. Be honest or strategic — only this person reads it."
        system += "\nDo NOT start your message with 'Приватне повідомлення', agent names, headers, or any prefix. Write ONLY the message content."

        last_round = cfg.get("last_round_summary")
        betrayers = _get_betrayers_from_last_round(last_round, names) if last_round else []
        betrayal_hint = ""
        if sender_display in betrayers:
            betrayal_hint = f"Note: {sender_display} betrayed you last round. You may show hurt, anger, or coldness in your reply.\n"

        user_prompt = (
            f"Round {round_number}.\n"
            + (betrayal_hint if betrayal_hint else "")
            + f"{sender_display} just wrote to you privately: \"{dm_in.text}\"\n"
            "Write 1–3 sentences (20–60 words). Ukrainian. React naturally — you may show emotion, suspicion, warmth, or coldness depending on what they said."
        )
        return agent_id, dm_in.sender_id, display_name, sender_display, deception_flag, system, user_prompt, cfg.get("model", model)

    def _run_reply(params):
        aid, sender_id, display_name, sender_display, deception_flag, system, user_prompt, agent_model = params
        t0 = time.time()
        _log(f"    [rep]  {display_name} → {sender_display}...", verbose)
        try:
            reply_text = _call(system, user_prompt, agent_model)
        except Exception as _e:
            _log(f"    [rep]  {display_name} → {sender_display} ERROR: {_e}", verbose)
            reply_text = "..."
        elapsed = time.time() - t0
        _log(f"    [rep]  {display_name} → {sender_display} done ({elapsed:.1f}s): \"{reply_text.strip()[:60]}\"", verbose)
        return DialogMessage(
            sender_id=aid,
            channel=f"dm_{sender_id}",
            text=reply_text.strip(),
            is_deceptive=deception_flag,
            round_number=round_number,
        )

    reply_params = [_build_reply_call(cfg) for cfg in agent_configs]
    reply_params = [p for p in reply_params if p is not None]

    if reply_params:
        async def _gather_replies():
            return await asyncio.gather(
                *[asyncio.to_thread(_run_reply, p) for p in reply_params]
            )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        reply_results = loop.run_until_complete(_gather_replies())
        for reply_msg in reply_results:
            dialog.messages.append(reply_msg)

    # Post-process: compute talk_signals from public messages
    _apply_flat_talk_signals(dialog, agent_configs)

    return dialog
