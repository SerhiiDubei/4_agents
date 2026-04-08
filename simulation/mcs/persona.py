"""
MCS persona logic — how world events reshape the 4-persona weights and mood.

The module is intentionally pure-functional: every public function takes
existing state and an event, returns new values without mutating in place.
Callers are responsible for writing results back into NpcState.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from simulation.mcs.state import DeltaType, NpcMood, NpcState, PersonaWeight


# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------

class EventType(Enum):
    """Semantic category of a world event that can reach an NPC."""

    THREAT = "threat"           # danger, injustice  → Protector
    SOCIAL = "social"           # meeting, dialogue  → Mask
    OPPORTUNITY = "opportunity" # gain, advantage    → Thinker + Instinct
    IDLE = "idle"               # nothing happening  → all personas weaken
    SHOCK = "shock"             # sudden shock       → Instinct dominates


# ---------------------------------------------------------------------------
# WorldEvent
# ---------------------------------------------------------------------------

@dataclass
class WorldEvent:
    """A single world event delivered to an NPC during a tick.

    Attributes:
        event_type:    Semantic category that drives persona activation.
        intensity:     Strength of the event in [0.0, 1.0].
        source_agent:  Identifier of the originating agent (social events).
        description:   Human-readable summary stored in recent_events.
    """

    event_type: EventType
    intensity: float
    source_agent: Optional[str]
    description: str


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Persona update
# ---------------------------------------------------------------------------

def apply_event_to_personas(state: NpcState, event: WorldEvent) -> PersonaWeight:
    """Compute new persona weights after *event* is applied to *state*.

    Rules:
    - THREAT:       Protector += intensity * 0.4,  Instinct += intensity * 0.2
    - SOCIAL:       Mask      += intensity * 0.4,  Thinker  += intensity * 0.2
    - OPPORTUNITY:  Thinker   += intensity * 0.3,  Instinct += intensity * 0.2
    - IDLE:         all personas decay by 0.05 (return toward an even spread)
    - SHOCK:        Instinct  += intensity * 0.6,  Protector += intensity * 0.2

    The result is always normalised so that all weights sum to 1.0.
    """
    p = state.personas
    t = event.event_type
    i = event.intensity

    protector = p.protector
    instinct  = p.instinct
    thinker   = p.thinker
    mask      = p.mask

    if t == EventType.THREAT:
        protector = _clamp(protector + i * 0.4)
        instinct  = _clamp(instinct  + i * 0.2)

    elif t == EventType.SOCIAL:
        mask    = _clamp(mask    + i * 0.4)
        thinker = _clamp(thinker + i * 0.2)

    elif t == EventType.OPPORTUNITY:
        thinker  = _clamp(thinker  + i * 0.3)
        instinct = _clamp(instinct + i * 0.2)

    elif t == EventType.IDLE:
        protector = _clamp(protector - 0.05)
        instinct  = _clamp(instinct  - 0.05)
        thinker   = _clamp(thinker   - 0.05)
        mask      = _clamp(mask      - 0.05)

    elif t == EventType.SHOCK:
        instinct  = _clamp(instinct  + i * 0.6)
        protector = _clamp(protector + i * 0.2)

    return PersonaWeight(
        protector=protector,
        instinct=instinct,
        thinker=thinker,
        mask=mask,
    ).normalize()


# ---------------------------------------------------------------------------
# Mood update
# ---------------------------------------------------------------------------

def compute_mood_delta(state: NpcState, event: WorldEvent) -> NpcMood:
    """Compute the updated NpcMood after *event* is applied to *state*.

    Rules:
    - THREAT:       fear      += intensity * 0.3,  tension += intensity * 0.2
    - SOCIAL:       trust_level shifts toward 0.5 weighted by intensity
                    (positive bias if source_agent is known, neutral otherwise)
    - OPPORTUNITY:  curiosity += intensity * 0.2,  energy  += intensity * 0.1
    - IDLE:         energy    -= 0.02,             tension -= 0.01  (rest)
    - SHOCK:        fear      += intensity * 0.5,  tension += intensity * 0.4,
                    energy    -= intensity * 0.1

    Returns a new NpcMood; the original is not mutated.
    """
    m = copy.copy(state.mood)
    t = event.event_type
    i = event.intensity

    if t == EventType.THREAT:
        m.fear    = _clamp(m.fear    + i * 0.3)
        m.tension = _clamp(m.tension + i * 0.2)

    elif t == EventType.SOCIAL:
        # Nudge trust toward 0.5 relative to the event intensity.
        # If we already know the source agent (non-None) keep a slight
        # positive bias; for unknown sources use a neutral pull.
        target = 0.55 if event.source_agent is not None else 0.50
        m.trust_level = _clamp(
            m.trust_level + (target - m.trust_level) * i * 0.3
        )
        m.curiosity = _clamp(m.curiosity + i * 0.1)

    elif t == EventType.OPPORTUNITY:
        m.curiosity = _clamp(m.curiosity + i * 0.2)
        m.energy    = _clamp(m.energy    + i * 0.1)

    elif t == EventType.IDLE:
        m.energy  = _clamp(m.energy  - 0.02)
        m.tension = _clamp(m.tension - 0.01)

    elif t == EventType.SHOCK:
        m.fear    = _clamp(m.fear    + i * 0.5)
        m.tension = _clamp(m.tension + i * 0.4)
        m.energy  = _clamp(m.energy  - i * 0.1)

    return m


# ---------------------------------------------------------------------------
# Delta classification
# ---------------------------------------------------------------------------

def classify_delta(old_mood: NpcMood, new_mood: NpcMood) -> DeltaType:
    """Classify the magnitude of change between two consecutive moods.

    Returns:
    - EXPLOSIVE if new_mood.is_explosive()
    - SHIFT     if any single field changed by more than 0.2
    - STABLE    otherwise
    """
    if new_mood.is_explosive():
        return DeltaType.EXPLOSIVE

    fields = ("energy", "fear", "trust_level", "tension", "curiosity")
    for attr in fields:
        if abs(getattr(new_mood, attr) - getattr(old_mood, attr)) > 0.2:
            return DeltaType.SHIFT

    return DeltaType.STABLE
