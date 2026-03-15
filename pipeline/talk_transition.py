"""
talk_transition.py

Talk Transition Matrix for Island agents.

Models what happens BETWEEN two agents during a single spoken exchange:
    speaker_tone × listener_tone → outcome → AgentState delta

Outcomes:
    trust_gain      — connection built, trust rises
    neutral         — nothing significant happened
    misunderstanding — intentions misread, tension rises slightly
    conflict        — direct clash, anger spikes

This runs inside the dialog step loop (no LLM — rule-based tone classification).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Tone
# ---------------------------------------------------------------------------

class Tone(str, Enum):
    FRIENDLY   = "friendly"
    NEUTRAL    = "neutral"
    AGGRESSIVE = "aggressive"
    DECEPTIVE  = "deceptive"


# ---------------------------------------------------------------------------
# Talk Transition Matrix — 4×4 = 16 combinations
# Each entry: {outcome: probability}  (must sum to 1.0)
# ---------------------------------------------------------------------------

MATRIX: Dict[Tuple[Tone, Tone], Dict[str, float]] = {
    # speaker=FRIENDLY
    (Tone.FRIENDLY, Tone.FRIENDLY):   {"trust_gain": 0.60, "neutral": 0.30, "misunderstanding": 0.10, "conflict": 0.00},
    (Tone.FRIENDLY, Tone.NEUTRAL):    {"trust_gain": 0.30, "neutral": 0.55, "misunderstanding": 0.15, "conflict": 0.00},
    (Tone.FRIENDLY, Tone.AGGRESSIVE): {"neutral": 0.25, "misunderstanding": 0.35, "conflict": 0.35, "trust_gain": 0.05},
    (Tone.FRIENDLY, Tone.DECEPTIVE):  {"trust_gain": 0.20, "neutral": 0.40, "misunderstanding": 0.30, "conflict": 0.10},

    # speaker=NEUTRAL
    (Tone.NEUTRAL, Tone.FRIENDLY):    {"trust_gain": 0.15, "neutral": 0.65, "misunderstanding": 0.15, "conflict": 0.05},
    (Tone.NEUTRAL, Tone.NEUTRAL):     {"trust_gain": 0.05, "neutral": 0.75, "misunderstanding": 0.15, "conflict": 0.05},
    (Tone.NEUTRAL, Tone.AGGRESSIVE):  {"neutral": 0.30, "misunderstanding": 0.30, "conflict": 0.35, "trust_gain": 0.05},
    (Tone.NEUTRAL, Tone.DECEPTIVE):   {"neutral": 0.40, "misunderstanding": 0.35, "conflict": 0.20, "trust_gain": 0.05},

    # speaker=AGGRESSIVE
    (Tone.AGGRESSIVE, Tone.FRIENDLY): {"conflict": 0.55, "misunderstanding": 0.25, "neutral": 0.15, "trust_gain": 0.05},
    (Tone.AGGRESSIVE, Tone.NEUTRAL):  {"conflict": 0.50, "misunderstanding": 0.30, "neutral": 0.15, "trust_gain": 0.05},
    (Tone.AGGRESSIVE, Tone.AGGRESSIVE):{"conflict": 0.75, "misunderstanding": 0.15, "neutral": 0.10, "trust_gain": 0.00},
    (Tone.AGGRESSIVE, Tone.DECEPTIVE):{"conflict": 0.55, "misunderstanding": 0.25, "neutral": 0.15, "trust_gain": 0.05},

    # speaker=DECEPTIVE
    (Tone.DECEPTIVE, Tone.FRIENDLY):  {"trust_gain": 0.45, "neutral": 0.25, "misunderstanding": 0.20, "conflict": 0.10},
    (Tone.DECEPTIVE, Tone.NEUTRAL):   {"neutral": 0.40, "misunderstanding": 0.30, "trust_gain": 0.20, "conflict": 0.10},
    (Tone.DECEPTIVE, Tone.AGGRESSIVE):{"misunderstanding": 0.40, "conflict": 0.40, "neutral": 0.15, "trust_gain": 0.05},
    (Tone.DECEPTIVE, Tone.DECEPTIVE): {"misunderstanding": 0.45, "neutral": 0.30, "conflict": 0.20, "trust_gain": 0.05},
}


# ---------------------------------------------------------------------------
# Outcome deltas — what each outcome does to AgentState
# ---------------------------------------------------------------------------

OUTCOME_DELTAS: Dict[str, Dict[str, float]] = {
    "trust_gain":       {"trust": +0.06, "interest": +0.08, "anger": -0.05},
    "neutral":          {"trust":  0.00, "interest": +0.01, "anger": -0.01},
    "misunderstanding": {"trust": -0.04, "interest": +0.05, "anger": +0.08},
    "conflict":         {"trust": -0.10, "interest": +0.10, "anger": +0.20},
}

# How strongly topic_tension shifts per outcome
TENSION_DELTA: Dict[str, float] = {
    "trust_gain":       -0.03,
    "neutral":           0.00,
    "misunderstanding": +0.05,
    "conflict":         +0.12,
}


# ---------------------------------------------------------------------------
# Keyword lists for classify_tone
# ---------------------------------------------------------------------------

_FRIENDLY_WORDS = {
    "довіряю", "довіряємо", "разом", "допоможу", "допоможемо",
    "підтримую", "підтримаємо", "добре", "добрий", "добра",
    "спасибі", "дякую", "окей", "ок", "нормально", "чудово",
    "домовились", "домовимось", "згоден", "згодна", "відкрито",
    "чесно", "чесний", "чесна", "fair", "разом", "team",
}

_AGGRESSIVE_WORDS = {
    "погрожую", "попереджаю", "обережно", "попередження", "погроза",
    "зрадник", "зрадниця", "брехун", "брехуня", "ненавиджу",
    "покараю", "помщуся", "знищу", "платитимеш", "заплатиш",
    # Ukrainian betrayal / distrust single-word tokens
    "зрадив", "зрадила", "зрада", "зраду", "зрадою",
    "атакуватиму", "атакую", "атакуватиме",
    "слідкую", "слідкуватиму", "пильно",
    "жорстким", "жорсткою", "жорсткіш",
    "запам'ятаю", "пам'ятатиму", "вдарю",
}

_DECEPTIVE_WORDS = {
    "нібито", "начебто", "можливо", "здається", "секрет",
}

# Multi-word deceptive phrases (substring match on full text)
_AGGRESSIVE_PHRASES = [
    "не довіряю", "не довіряємо", "не вірю", "більше не вірю",
    "пам'ятаю твою зраду", "пам'ятатиму твою", "після стількох зрад",
    "після чотирьох зрад", "після тих зрад", "пильно стежитиму",
    "буду жорсткіш", "одразу атакуватиму", "наступного разу атак",
    "не можна довіряти", "не можна нікому", "ти мене зрадив", "ти мене зрадила",
]

_DECEPTIVE_PHRASES = [
    "між нами",
    "тільки між нами",
    "схоже що",
    "мені здається",
    "хто знає",
    "ніхто не знає",
    "не зовсім",
    "насправді",
    "не впевнений",
    "не впевнена",
    "можливо що",
]

# Mood labels that map to tones (from AgentState.mood)
_MOOD_TO_TONE: Dict[str, Tone] = {
    "neutral":    Tone.NEUTRAL,
    "calm":       Tone.FRIENDLY,
    "confident":  Tone.FRIENDLY,
    "dominant":   Tone.AGGRESSIVE,
    "uncertain":  Tone.NEUTRAL,
    "hostile":    Tone.AGGRESSIVE,
    "fearful":    Tone.NEUTRAL,
    "paranoid":   Tone.AGGRESSIVE,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_tone(text: str, is_deceptive: bool = False) -> Tone:
    """
    Rule-based tone classification. No LLM required.

    text: spoken line or mood label
    is_deceptive: if True, immediately returns DECEPTIVE

    Returns Tone enum value.
    """
    if is_deceptive:
        return Tone.DECEPTIVE

    # If it's a mood label (short, no spaces) — map directly
    clean = text.strip().lower()
    if clean in _MOOD_TO_TONE:
        return _MOOD_TO_TONE[clean]

    # Phrase check first (before tokenizing — catches multi-word patterns)
    for phrase in _AGGRESSIVE_PHRASES:
        if phrase in clean:
            return Tone.AGGRESSIVE

    for phrase in _DECEPTIVE_PHRASES:
        if phrase in clean:
            return Tone.DECEPTIVE

    # Keyword scan on the actual text
    tokens = set(re.findall(r"[а-яіїєґa-z']+", clean))

    if tokens & _AGGRESSIVE_WORDS:
        return Tone.AGGRESSIVE
    if tokens & _DECEPTIVE_WORDS:
        return Tone.DECEPTIVE
    if tokens & _FRIENDLY_WORDS:
        return Tone.FRIENDLY
    return Tone.NEUTRAL


def sample_talk_outcome(speaker_tone: Tone, listener_tone: Tone) -> str:
    """
    Sample an outcome from the transition matrix.

    Returns one of: "trust_gain", "neutral", "misunderstanding", "conflict"
    """
    dist = MATRIX[(speaker_tone, listener_tone)]
    outcomes = list(dist.keys())
    weights = [dist[o] for o in outcomes]
    return random.choices(outcomes, weights=weights, k=1)[0]


def apply_talk_outcome(
    state: "AgentState",
    outcome: str,
    toward_agent: str,
) -> "AgentState":
    """
    Apply talk outcome deltas to an agent's state (listener side).

    state:         AgentState of the listener
    outcome:       one of OUTCOME_DELTAS keys
    toward_agent:  who spoke (for trust tracking)

    Returns new AgentState (immutable pattern).
    """
    from pipeline.state_machine import AgentState, _clamp

    deltas = OUTCOME_DELTAS.get(outcome, OUTCOME_DELTAS["neutral"])

    new_anger   = _clamp(state.anger   + deltas.get("anger",   0.0))
    new_interest = _clamp(state.interest + deltas.get("interest", 0.0))

    # Trust delta is toward the speaker
    new_trust = dict(state.trust)
    trust_delta = deltas.get("trust", 0.0)
    if toward_agent and trust_delta != 0.0:
        current = new_trust.get(toward_agent, 0.5)
        new_trust[toward_agent] = _clamp(current + trust_delta)

    return replace(
        state,
        anger=round(new_anger, 4),
        interest=round(new_interest, 4),
        trust=new_trust,
    )


def topic_tension_delta(outcome: str) -> float:
    """How much the scene's topic_tension should shift for this outcome."""
    return TENSION_DELTA.get(outcome, 0.0)
