"""
MCS state dataclasses — internal NPC state representation.

Each NPC carries a PersonaWeight (4 voices), NpcMood (emotional layer),
and a top-level NpcState that glues everything together and drives
the cheap-tick / LLM-tick decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# PersonaWeight
# ---------------------------------------------------------------------------

@dataclass
class PersonaWeight:
    """Relative activation weight of each of the 4 personas at a given tick.

    All values should be in [0.0, 1.0] and normally sum to 1.0 after
    normalisation.  Use :meth:`normalize` to enforce that invariant.
    """

    protector: float  # responds to threats / injustice
    instinct: float   # emotions, physical stimuli
    thinker: float    # rational analysis, consequences
    mask: float       # social expectations, performance

    def dominant(self) -> str:
        """Return the name of the persona with the highest current weight."""
        weights = {
            "protector": self.protector,
            "instinct": self.instinct,
            "thinker": self.thinker,
            "mask": self.mask,
        }
        return max(weights, key=lambda k: weights[k])

    def normalize(self) -> "PersonaWeight":
        """Return a new PersonaWeight whose values sum to 1.0.

        If the total is zero (degenerate case) every persona gets 0.25.
        """
        total = self.protector + self.instinct + self.thinker + self.mask
        if total == 0.0:
            return PersonaWeight(0.25, 0.25, 0.25, 0.25)
        factor = 1.0 / total
        return PersonaWeight(
            protector=self.protector * factor,
            instinct=self.instinct * factor,
            thinker=self.thinker * factor,
            mask=self.mask * factor,
        )


# ---------------------------------------------------------------------------
# NpcMood
# ---------------------------------------------------------------------------

@dataclass
class NpcMood:
    """Emotional state of an NPC at a single point in time.

    All fields are in [0.0, 1.0].  Values are clamped on assignment via
    the helper :func:`_clamp` used in mutation helpers.
    """

    energy: float       # vitality; decays over time
    fear: float         # threat-induced anxiety
    trust_level: float  # average trust toward all known agents
    tension: float      # accumulated stress; hard to discharge quickly
    curiosity: float    # drive to explore / interact

    def is_explosive(self) -> bool:
        """Return True when the NPC is in a critical emotional state.

        Criteria (any one triggers EXPLOSIVE):
        - fear > 0.8
        - tension > 0.85
        - fear > 0.6 AND tension > 0.6
        """
        if self.fear > 0.8:
            return True
        if self.tension > 0.85:
            return True
        if self.fear > 0.6 and self.tension > 0.6:
            return True
        return False


# ---------------------------------------------------------------------------
# DeltaType
# ---------------------------------------------------------------------------

class DeltaType(Enum):
    """Severity classification of a mood change between two ticks."""

    STABLE = "stable"       # negligible change — no LLM needed
    SHIFT = "shift"         # noticeable change — worth noting
    EXPLOSIVE = "explosive" # critical — LLM must intervene immediately


# ---------------------------------------------------------------------------
# NpcState
# ---------------------------------------------------------------------------

@dataclass
class NpcState:
    """Complete internal state of a single NPC in the MCS engine.

    Carries identity, tick counters, persona weights, mood, a short
    event buffer, and an optional pending action the NPC wants to execute.
    """

    agent_id: str
    agent_name: str
    tick_count: int           # total ticks lived since creation
    last_llm_tick: int        # tick index of the last LLM invocation
    personas: PersonaWeight
    mood: NpcMood
    recent_events: List[str]  # rolling buffer of the last 5 experienced events
    pending_action: Optional[str]  # action the NPC wants to take next tick

    def ticks_since_llm(self) -> int:
        """Return how many ticks have elapsed since the last LLM call."""
        return self.tick_count - self.last_llm_tick

    def needs_llm(self, llm_interval: int = 10) -> bool:
        """Return True when the NPC requires an LLM tick.

        Triggers:
        - mood is in EXPLOSIVE state
        - ticks since last LLM call >= llm_interval
        - there is a pending action waiting to be resolved
        """
        if self.mood.is_explosive():
            return True
        if self.ticks_since_llm() >= llm_interval:
            return True
        if self.pending_action is not None:
            return True
        return False

    @classmethod
    def from_soul_and_core(
        cls,
        agent_id: str,
        soul_text: str,  # noqa: ARG003  (reserved for future NLP parsing)
        core: dict,
    ) -> "NpcState":
        """Build an initial NpcState from a SOUL.md text and a CORE.json dict.

        CORE.json fields used:
        - cooperation_bias   (0–100) → raises mask + thinker
        - deception_tendency (0–100) → raises mask + lowers instinct
        - risk_appetite      (0–100) → raises protector + instinct

        All three are normalised to [0.0, 1.0] before being applied.
        """
        coop = core.get("cooperation_bias", 50) / 100.0
        decep = core.get("deception_tendency", 50) / 100.0
        risk = core.get("risk_appetite", 50) / 100.0

        personas = PersonaWeight(
            protector=0.25 + risk * 0.3,
            instinct=0.25 + risk * 0.2 - decep * 0.1,
            thinker=0.25 + coop * 0.2,
            mask=0.25 + coop * 0.1 + decep * 0.2,
        ).normalize()

        mood = NpcMood(
            energy=0.8,
            fear=0.1,
            trust_level=coop * 0.6,
            tension=0.1,
            curiosity=0.5,
        )

        return cls(
            agent_id=agent_id,
            agent_name=core.get("name", agent_id),
            tick_count=0,
            last_llm_tick=0,
            personas=personas,
            mood=mood,
            recent_events=[],
            pending_action=None,
        )
