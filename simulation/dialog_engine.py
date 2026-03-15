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

Step-based dialog (generate_round_dialog_stepped):
  - 1 round = N steps (default 8)
  - Each step: one speaker selected via urgency formula
  - talk_cooldown prevents same agent from speaking too frequently
  - SceneState tracks topic tension and attention graph
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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

_STEP_SYSTEM_TEMPLATE = """You are {agent_id}. You are a real person at a private gathering.
You do not know you are simulated. You exist fully. You have your own memories, desires, and fears.

{soul_md}

{dialog_rules}

Speak in first person. One sentence only, max 25 words. Ukrainian language.
Sound like yourself — specific, grounded, no theatrical language.
Return ONLY the spoken line. Nothing else."""


def _build_context(
    soul_md: str,
    states_md: str,
    memory_summary: dict,
    deception_tendency: float,
    round_number: int,
    total_rounds: int,
    visible_history: dict,
) -> str:
    rounds_left = total_rounds - round_number
    deception_flag = deception_tendency > 60
    return (
        f"AGENT PROFILE:\n{soul_md[:500]}\n\n"
        f"CURRENT STATE:\n{states_md}\n\n"
        f"MEMORY:\n{json.dumps(memory_summary, ensure_ascii=False)[:300]}\n\n"
        f"Round {round_number}/{total_rounds}. {rounds_left} rounds left.\n"
        f"Deception tendency: {deception_tendency:.0f}/100.\n"
        + ("DECEPTION FLAG: agent is likely misdirecting.\n" if deception_flag else "")
        + f"Visible actions: {json.dumps(visible_history, ensure_ascii=False)[:200] if visible_history else 'none'}"
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call(system: str, user: str, model: str) -> str:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.seed_generator import call_openrouter
    return call_openrouter(
        system_prompt=system,
        user_prompt=user,
        model=model,
        temperature=0.88,
        max_tokens=120,
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
        soul_md=soul_md[:600],
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


def generate_round_dialog(
    round_number: int,
    agent_configs: List[dict],
    model: str = "x-ai/grok-3-mini",
) -> RoundDialog:
    """
    Generate all dialog for one round (legacy, one message per agent).

    agent_configs: list of dicts with keys:
      agent_id, soul_md, states_md, memory_summary,
      deception_tendency, total_rounds, visible_history,
      dm_target (optional)
    """
    dialog = RoundDialog(round_number=round_number)

    for cfg in agent_configs:
        msg = generate_public_message(
            agent_id=cfg["agent_id"],
            soul_md=cfg.get("soul_md", ""),
            states_md=cfg.get("states_md", ""),
            memory_summary=cfg.get("memory_summary", {}),
            deception_tendency=cfg.get("deception_tendency", 50),
            round_number=round_number,
            total_rounds=cfg.get("total_rounds", 10),
            visible_history=cfg.get("visible_history", {}),
            model=model,
        )
        dialog.messages.append(msg)

        if cfg.get("dm_target"):
            dm = generate_dm(
                sender_id=cfg["agent_id"],
                target_id=cfg["dm_target"],
                soul_md=cfg.get("soul_md", ""),
                states_md=cfg.get("states_md", ""),
                memory_summary=cfg.get("memory_summary", {}),
                deception_tendency=cfg.get("deception_tendency", 50),
                round_number=round_number,
                total_rounds=cfg.get("total_rounds", 10),
                model=model,
            )
            dialog.messages.append(dm)

    return dialog


# ---------------------------------------------------------------------------
# Step-based dialog — Variant A
# ---------------------------------------------------------------------------

# Dialog step parameters
_STEPS_PER_ROUND = 8
_COOLDOWN_AFTER_SPEAK = 2
_COOLDOWN_AFTER_INTERRUPT = 1
_MAX_MESSAGES_PER_ROUND = 5
_SILENCE_PROBABILITY = 0.25
_INTERRUPT_CHANCE = 0.15
_INTERRUPT_ANGER_THRESHOLD = 0.6
# Anger cost applied to a speaker who uses aggressive tone (classified post-hoc)
_AGGRESSION_ANGER_COST = 0.08
# Tension penalty on the speaker for aggressive interrupts
_INTERRUPT_TENSION_COST = 0.05

# Dialog rules injected into the system prompt so LLM understands the structure
DIALOG_RULES = """Conversation rules:
- Only one person speaks per step
- After speaking you must wait at least 2 steps before speaking again
- Interrupting is only possible when you are very angry — it costs you tension and anger
- Silence is a valid choice — you may stay quiet
- Aggressive tone toward others increases YOUR own tension
- You may address someone directly or speak to the group"""


def _outcome_to_signal(outcome: str) -> str:
    """Map talk transition outcome to dialog_signal string for RoundOutcome."""
    return {
        "trust_gain":       "cooperative",
        "neutral":          "neutral",
        "misunderstanding": "neutral",
        "conflict":         "threatening",
    }.get(outcome, "neutral")


_STEP_SYSTEM = """You are generating a single spoken line for an agent in a social simulation.
The setting: a private rave. Four people in a tense pre-decision moment.

Write one or two sentences — what this agent says right now in response to the scene.
Ukrainian language only.

Rules:
- First person only
- No abstraction — stay in the moment
- Match the mood and the scene topic
- If DECEPTION FLAG is set — the agent hides their real intention
- No exclamation marks unless anger is very high
- React to the previous speaker if one is provided

Return ONLY the spoken line. Nothing else."""


def _talkativity(deception_tendency: float, cooperation_bias: float) -> float:
    """Map cooperation_bias to talkativity. High cooperation → more talkative."""
    return 0.3 + (cooperation_bias / 100.0) * 0.7


def _social_permission(
    agent_id: str,
    scene: "SceneState",
    agent_states: Dict[str, "AgentState"],
) -> float:
    """
    How socially appropriate it is for this agent to speak right now.
    Returns multiplier 0.0–1.5.
    """
    from pipeline.state_machine import SceneState as _SC

    score = 1.0

    # Being directly addressed gives permission boost
    if scene.attention_graph.get(scene.last_speaker) == agent_id:
        score += 0.5

    # High topic tension makes everyone want to speak
    if scene.topic_tension > 0.6:
        score += 0.2

    # Long silence gives permission to anyone
    if scene.silence_streak >= 2:
        score += 0.4

    # Don't speak twice in a row unless necessary
    if scene.last_speaker == agent_id:
        score -= 0.5

    return max(0.0, score)


def select_speaker(
    agents: List[str],
    scene: "SceneState",
    agent_states: Dict[str, "AgentState"],
    core_params: Dict[str, dict],
) -> Optional[str]:
    """
    Choose who speaks next using urgency formula with softmax sampling.

    urgency_i = talkativity(core_i) × interest_i × social_permission(scene_i)
                × (1.0 if cooldown == 0 else 0.0)
                + anger_i × 0.3

    Returns agent_id of the chosen speaker, or None if silence.
    """
    urgencies: List[float] = []
    eligible: List[str] = []

    for agent_id in agents:
        state = agent_states.get(agent_id)
        if state is None:
            continue

        if state.talk_cooldown > 0:
            urgencies.append(0.0)
            eligible.append(agent_id)
            continue

        cp = core_params.get(agent_id, {})
        talk = _talkativity(
            cp.get("deception_tendency", 50),
            cp.get("cooperation_bias", 50),
        )
        perm = _social_permission(agent_id, scene, agent_states)
        urgency = (
            talk * state.interest * perm
            + state.anger * 0.3
        )
        urgencies.append(max(0.0, urgency))
        eligible.append(agent_id)

    if not eligible:
        return None

    total = sum(urgencies)
    if total <= 0.0:
        return None

    # Softmax
    exps = [math.exp(u / 0.5) for u in urgencies]
    exp_sum = sum(exps)
    probs = [e / exp_sum for e in exps]

    # Random silence check
    if random.random() < _SILENCE_PROBABILITY:
        return None

    r = random.random()
    cumulative = 0.0
    for agent_id, prob in zip(eligible, probs):
        cumulative += prob
        if r <= cumulative:
            return agent_id
    return eligible[-1]


def _build_step_context(
    speaker_id: str,
    cfg: dict,
    scene: "SceneState",
    previous_message: Optional[DialogMessage],
    step_number: int,
    steps_per_round: int,
) -> tuple:
    """Return (system_prompt, user_prompt) pair for identity-based generation."""
    soul_md = cfg.get("soul_md", "")
    states_md = cfg.get("states_md", "")
    memory_summary = cfg.get("memory_summary", {})
    deception_tendency = cfg.get("deception_tendency", 50)
    total_rounds = cfg.get("total_rounds", 10)
    round_number = cfg.get("round_number", 1)

    rounds_left = total_rounds - round_number
    deception_flag = deception_tendency > 60

    # System prompt — stable identity (SOUL as first-person definition)
    system = _STEP_SYSTEM_TEMPLATE.format(
        agent_id=speaker_id,
        soul_md=soul_md[:600],
        dialog_rules=DIALOG_RULES,
    )
    if deception_flag:
        system += "\nRight now you are hiding your real intentions. Seem cooperative."

    # User prompt — current situational context only
    prev_line = ""
    if previous_message:
        prev_line = f'\nJust now {previous_message.sender_id} said: "{previous_message.text}"'

    # Compact state summary
    import re
    mood_match = re.search(r"mood:\s*(\w+)", states_md)
    mood = mood_match.group(1) if mood_match else "neutral"
    tension_match = re.search(r"tension:\s*([\d.]+)", states_md)
    tension = tension_match.group(1) if tension_match else "?"

    mem_short = ""
    if memory_summary:
        betrayals = memory_summary.get("total_betrayals_received", 0)
        coops = memory_summary.get("total_cooperations_received", 0)
        mem_short = f"You've been betrayed {betrayals}x and helped {coops}x so far."

    user = (
        f"Round {round_number}/{total_rounds}. Step {step_number}/{steps_per_round}. "
        f"{rounds_left} rounds remain.\n"
        f"Your mood: {mood}. Tension: {tension}.\n"
        + (f"{mem_short}\n" if mem_short else "")
        + f"Scene: {scene.topic or 'nothing yet'}. Scene tension: {scene.topic_tension:.2f}."
        + prev_line
        + "\nSpeak now:"
    )

    return system, user


def generate_step_message(
    speaker_id: str,
    cfg: dict,
    scene: "SceneState",
    previous_message: Optional[DialogMessage],
    step_number: int,
    steps_per_round: int,
    model: str = "x-ai/grok-3-mini",
) -> DialogMessage:
    """
    Generate a single spoken line for the given speaker in the current step context.
    Uses identity-based system prompt (SOUL as self) + situational user prompt.
    """
    system, user = _build_step_context(
        speaker_id, cfg, scene, previous_message, step_number, steps_per_round
    )
    model_to_use = cfg.get("model", model)
    text = _call(system, user, model_to_use)
    return DialogMessage(
        sender_id=speaker_id,
        channel="public",
        text=text.strip(),
        is_deceptive=cfg.get("deception_tendency", 50) > 60,
        round_number=cfg.get("round_number", 1),
    )


def generate_round_dialog_stepped(
    round_number: int,
    agent_configs: List[dict],
    steps_per_round: int = _STEPS_PER_ROUND,
    model: str = "x-ai/grok-3-mini",
) -> RoundDialog:
    """
    Step-based dialog generation for one round.

    Replaces generate_round_dialog. Parameters (Variant A):
      steps_per_round=8, cooldown=2, max_messages=5, silence_prob=0.25

    agent_configs: list of dicts with keys:
      agent_id, soul_md, states_md, memory_summary,
      deception_tendency, cooperation_bias, total_rounds,
      visible_history, round_number
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.state_machine import AgentState, SceneState, tick_cooldowns

    dialog = RoundDialog(round_number=round_number)

    # Build agent_id list and state snapshot for this dialog phase
    agent_ids = [cfg["agent_id"] for cfg in agent_configs]
    cfg_by_id = {cfg["agent_id"]: cfg for cfg in agent_configs}

    # Initialize fresh per-round AgentState snapshots for dialog
    agent_states: Dict[str, AgentState] = {}
    for cfg in agent_configs:
        aid = cfg["agent_id"]
        existing_states_md = cfg.get("states_md", "")
        if existing_states_md:
            st = AgentState.from_md(existing_states_md, aid)
        else:
            st = AgentState(agent_id=aid)
        # Reset cooldown at the start of the dialog phase
        import dataclasses
        st = dataclasses.replace(st, talk_cooldown=0)
        agent_states[aid] = st

    # Core params dict for urgency formula
    core_params = {
        cfg["agent_id"]: {
            "cooperation_bias": cfg.get("cooperation_bias", 50),
            "deception_tendency": cfg.get("deception_tendency", 50),
        }
        for cfg in agent_configs
    }

    scene = SceneState(
        topic="",
        topic_tension=0.3,
        step_number=0,
        silence_streak=0,
        last_speaker="",
    )

    previous_message: Optional[DialogMessage] = None
    messages_this_round = 0

    for step in range(steps_per_round):
        scene.step_number = step

        if messages_this_round >= _MAX_MESSAGES_PER_ROUND:
            agent_states = tick_cooldowns(agent_states)
            continue

        speaker_id = select_speaker(agent_ids, scene, agent_states, core_params)

        if speaker_id is None:
            # Silence this step
            scene.silence_streak += 1
            scene.last_speaker = ""
            agent_states = tick_cooldowns(agent_states)
            continue

        # Interrupt check — angry agent can cut through cooldown
        state = agent_states[speaker_id]
        if state.talk_cooldown > 0:
            if state.anger > _INTERRUPT_ANGER_THRESHOLD and random.random() < _INTERRUPT_CHANCE:
                # Interrupt — proceed despite cooldown, but costs tension
                cooldown_after = _COOLDOWN_AFTER_INTERRUPT
                import dataclasses as _dc2
                agent_states[speaker_id] = _dc2.replace(
                    state,
                    tension=min(1.0, state.tension + _INTERRUPT_TENSION_COST),
                )
            else:
                scene.silence_streak += 1
                agent_states = tick_cooldowns(agent_states)
                continue
        else:
            cooldown_after = _COOLDOWN_AFTER_SPEAK

        # Generate the line
        cfg = cfg_by_id[speaker_id]
        cfg_with_round = dict(cfg)
        cfg_with_round["round_number"] = round_number

        msg = generate_step_message(
            speaker_id=speaker_id,
            cfg=cfg_with_round,
            scene=scene,
            previous_message=previous_message,
            step_number=step,
            steps_per_round=steps_per_round,
            model=model,
        )
        dialog.messages.append(msg)
        messages_this_round += 1
        previous_message = msg

        # --- Talk transition: apply per-step state mutations ---
        classify_tone, sample_talk_outcome, apply_talk_outcome, topic_tension_delta, Tone = _get_talk_transition()
        # Classify what listeners actually hear — based on the text content itself, not speaker intent
        # is_deceptive only affects the speaker's framing, not what words come out
        apparent_tone = classify_tone(msg.text, is_deceptive=False)
        # Speaker's actual tone (for self-cost calculation)
        speaker_tone = classify_tone(msg.text, is_deceptive=msg.is_deceptive)

        # Anger cost for speaker if they speak aggressively (consequences for aggression)
        if speaker_tone in (Tone.AGGRESSIVE,):
            import dataclasses as _dc
            sp_state = agent_states[speaker_id]
            agent_states[speaker_id] = _dc.replace(
                sp_state,
                anger=min(1.0, sp_state.anger + _AGGRESSION_ANGER_COST),
                tension=min(1.0, sp_state.tension + _AGGRESSION_ANGER_COST * 0.5),
            )

        for listener_id in agent_ids:
            if listener_id == speaker_id:
                continue
            listener_mood = agent_states[listener_id].mood
            listener_tone = classify_tone(listener_mood, is_deceptive=False)
            outcome = sample_talk_outcome(apparent_tone, listener_tone)
            agent_states[listener_id] = apply_talk_outcome(
                agent_states[listener_id],
                outcome=outcome,
                toward_agent=speaker_id,
            )
            dialog.talk_signals[listener_id] = _outcome_to_signal(outcome)
        tension_shift = topic_tension_delta(
            sample_talk_outcome(apparent_tone, Tone.NEUTRAL)
        )
        scene.topic_tension = min(1.0, max(0.0, scene.topic_tension + tension_shift))

        # Update scene
        scene.last_speaker = speaker_id
        scene.silence_streak = 0
        # Topic tension rises slightly after each message
        scene.topic_tension = min(1.0, scene.topic_tension + 0.04)

        # Set cooldown for speaker
        import dataclasses
        agent_states[speaker_id] = dataclasses.replace(
            agent_states[speaker_id],
            talk_cooldown=cooldown_after,
        )

        # Update attention — others shift attention toward speaker
        for aid in agent_ids:
            if aid != speaker_id:
                scene.attention_graph[aid] = speaker_id

        agent_states = tick_cooldowns(agent_states)

    # DM phase — after the step loop, each agent with a dm_target sends one private message
    for cfg in agent_configs:
        if cfg.get("dm_target"):
            cfg_with_round = dict(cfg)
            cfg_with_round["round_number"] = round_number
            dm = generate_dm(
                sender_id=cfg["agent_id"],
                target_id=cfg["dm_target"],
                soul_md=cfg.get("soul_md", ""),
                states_md=cfg.get("states_md", ""),
                memory_summary=cfg.get("memory_summary", {}),
                deception_tendency=cfg.get("deception_tendency", 50),
                round_number=round_number,
                total_rounds=cfg.get("total_rounds", 10),
                model=model,
            )
            dialog.messages.append(dm)

    return dialog


# ---------------------------------------------------------------------------
# Flat dialog model (simplified: 1 public + 1 DM per agent per round)
# ---------------------------------------------------------------------------

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
        short = aid.split("_")[-1][:8]
        parts.append(f"{short} {_action_label(val)}")
    for aid, val in given.items():
        short = aid.split("_")[-1][:8]
        parts.append(f"{_gave_label(val)} with {short} ({val:.2f})")
    return " ".join(parts)


def _build_flat_public_context(
    cfg: dict,
    round_number: int,
    all_public_so_far: List[DialogMessage],
) -> tuple:
    """Build (system, user) prompts for a flat public message."""
    import re

    soul_md = cfg.get("soul_md", "")
    states_md = cfg.get("states_md", "")
    memory_summary = cfg.get("memory_summary", {})
    deception_tendency = cfg.get("deception_tendency", 50)
    total_rounds = cfg.get("total_rounds", 20)
    agent_id = cfg["agent_id"]
    deception_flag = deception_tendency > 60

    system = _STEP_SYSTEM_TEMPLATE.format(
        agent_id=agent_id,
        soul_md=soul_md[:600],
        dialog_rules=DIALOG_RULES,
    )
    if deception_flag:
        system += "\nYou are hiding your real intentions. Seem calm and cooperative."

    # Compact state
    mood_match = re.search(r"mood:\s*(\w+)", states_md)
    mood = mood_match.group(1) if mood_match else "neutral"

    # Memory short
    betrayals = memory_summary.get("total_betrayals_received", 0)
    coops = memory_summary.get("total_cooperations_received", 0)
    mem_short = f"Betrayed {betrayals}x, helped {coops}x." if (betrayals or coops) else ""

    # Last round personal reflection (if agent reflected after previous round)
    last_reflection = memory_summary.get("last_reflection", "")

    # Last round concrete actions/outcomes (what actually happened)
    last_round_summary = cfg.get("last_round_summary")
    last_round_text = _format_last_round(last_round_summary) if last_round_summary else ""

    # What others have already said this round — framed as competition, not consensus
    others_context = ""
    if all_public_so_far:
        others_context = "Others already spoke:\n"
        for prev in all_public_so_far:
            others_context += f'  {prev.sender_id[-8:]}: "{prev.text[:70]}"\n'
        others_context += (
            "Do NOT echo, agree, or repeat what they said. "
            "React with YOUR own angle — challenge, probe, warn, or contradict if it serves you. "
            "Show your character.\n"
        )

    user = (
        f"Round {round_number}/{total_rounds}. Your mood: {mood}.\n"
        + (f"{mem_short}\n" if mem_short else "")
        + (f"Last round: {last_round_text}\n" if last_round_text else "")
        + (f'Your reflection from last round: "{last_reflection}"\n' if last_reflection else "")
        + (others_context if others_context else "")
        + "Everyone will now make their decision — cooperate or betray — toward each other.\n"
        "This is your ONE public statement before that happens.\n"
        "Use it strategically: signal an alliance, warn a betrayer, bluff about your intentions, "
        "or probe who you can trust. What you say here shapes what others decide.\n"
        "Speak one sentence. First person. Ukrainian."
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


def generate_round_dialog_flat(
    round_number: int,
    agent_configs: List[dict],
    model: str = "x-ai/grok-3-mini",
) -> RoundDialog:
    """
    Flat (simplified) dialog generation for one round.

    Each agent:
      1. Writes ONE public message (sees previous public messages in same round)
      2. Writes ONE DM to their assigned dm_target (sees all public messages)

    Total LLM calls: len(agent_configs) * 2 (worst case, if all have dm_target)
    vs stepped: up to steps_per_round * len(agent_configs) calls.

    agent_configs keys: agent_id, soul_md, states_md, memory_summary,
      deception_tendency, cooperation_bias, total_rounds, visible_history,
      dm_target (optional), model (optional)
    """
    dialog = RoundDialog(round_number=round_number)
    public_messages: List[DialogMessage] = []

    # Phase 1 — public messages (sequential so each agent sees what came before)
    for cfg in agent_configs:
        system, user = _build_flat_public_context(cfg, round_number, public_messages)
        agent_model = cfg.get("model", model)
        text = _call(system, user, agent_model)
        msg = DialogMessage(
            sender_id=cfg["agent_id"],
            channel="public",
            text=text.strip(),
            is_deceptive=cfg.get("deception_tendency", 50) > 60,
            round_number=round_number,
        )
        dialog.messages.append(msg)
        public_messages.append(msg)

    # Phase 2 — DM messages (each agent has full public context)
    for cfg in agent_configs:
        dm_target = cfg.get("dm_target")
        if not dm_target:
            continue
        # Build DM system prompt with public context appended to user prompt
        deception_tendency = cfg.get("deception_tendency", 50)
        deception_flag = deception_tendency > 60
        soul_md = cfg.get("soul_md", "")
        memory_summary = cfg.get("memory_summary", {})

        system = _STEP_SYSTEM_TEMPLATE.format(
            agent_id=cfg["agent_id"],
            soul_md=soul_md[:600],
            dialog_rules=DIALOG_RULES,
        )
        if deception_flag:
            system += "\nYou are writing privately. You may use this to deceive or set a trap."
        else:
            system += "\nYou are writing privately. Be direct — only this person will read it."
        system += "\nDo NOT start your message with 'Приватне повідомлення', agent names, headers, or any prefix. Write ONLY the message content."

        betrayals = memory_summary.get("total_betrayals_received", 0)
        mem_short = f"You've been betrayed {betrayals}x total." if betrayals else ""

        # Include what everyone said publicly so DM can reference it
        public_context = ""
        for pub in public_messages:
            if pub.sender_id != cfg["agent_id"]:
                public_context += f'\n{pub.sender_id} said publicly: "{pub.text}"'

        user = (
            f"Round {round_number}/{cfg.get('total_rounds', 20)}.\n"
            + (f"{mem_short}\n" if mem_short else "")
            + (f"What was said publicly:{public_context}\n" if public_context else "")
            + f"You have a private channel to {dm_target} — they will read this before making their decision.\n"
            "You can: make a deal, threaten quietly, deceive, ask for alliance, or warn.\n"
            "One sentence. Ukrainian."
        )
        agent_model = cfg.get("model", model)
        dm_text = _call(system, user, agent_model)
        dm = DialogMessage(
            sender_id=cfg["agent_id"],
            channel=f"dm_{dm_target}",
            text=dm_text.strip(),
            is_deceptive=deception_flag,
            round_number=round_number,
        )
        dialog.messages.append(dm)

    # Phase 3 — DM responses (each recipient replies to incoming DM)
    for cfg in agent_configs:
        agent_id = cfg["agent_id"]
        received_dms = [m for m in dialog.messages if m.channel == f"dm_{agent_id}"]
        if not received_dms:
            continue
        dm_in = received_dms[-1]

        soul_md = cfg.get("soul_md", "")
        deception_tendency = cfg.get("deception_tendency", 50)
        deception_flag = deception_tendency > 60

        system = _STEP_SYSTEM_TEMPLATE.format(
            agent_id=agent_id,
            soul_md=soul_md[:600],
            dialog_rules=DIALOG_RULES,
        )
        system += "\nYou are writing a private reply. Be honest or strategic — only this person reads it."
        system += "\nDo NOT start your message with 'Приватне повідомлення', agent names, headers, or any prefix. Write ONLY the message content."

        user = (
            f"Round {round_number}.\n"
            f"{dm_in.sender_id} just wrote to you privately: \"{dm_in.text}\"\n"
            "Write one short private reply. Ukrainian."
        )
        agent_model = cfg.get("model", model)
        reply_text = _call(system, user, agent_model)
        reply_msg = DialogMessage(
            sender_id=agent_id,
            channel=f"dm_{dm_in.sender_id}",
            text=reply_text.strip(),
            is_deceptive=deception_flag,
            round_number=round_number,
        )
        dialog.messages.append(reply_msg)

    # Post-process: compute talk_signals from public messages
    _apply_flat_talk_signals(dialog, agent_configs)

    return dialog
