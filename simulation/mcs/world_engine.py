"""
World Engine — генерує події які надходять до NPC.
Простий MVP: випадкові події з ваговими ймовірностями.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from simulation.mcs.state import NpcState
from simulation.mcs.persona import WorldEvent, EventType

if TYPE_CHECKING:
    from simulation.mcs.tick_processor import TickProcessor


# ---------------------------------------------------------------------------
# Event description templates per EventType
# ---------------------------------------------------------------------------

_DESCRIPTIONS: dict[EventType, list[str]] = {
    EventType.IDLE: [
        "Нічого особливого не відбувається.",
        "Тихий момент. Думки блукають.",
        "Час іде повільно. Навколо спокій.",
        "Пауза між справами.",
        "Мить тиші.",
    ],
    EventType.SOCIAL: [
        "Несподівана зустріч з {other}.",
        "{other} підходить і починає розмову.",
        "Перетинається доля з {other}.",
        "{other} кидає погляд і посміхається.",
        "Короткий обмін словами з {other}.",
    ],
    EventType.OPPORTUNITY: [
        "З'явилась можливість, яку важко ігнорувати.",
        "Несподівана нагода відкрилась на горизонті.",
        "Щось цікаве привертає увагу.",
        "Ситуація складається на користь.",
        "Відкривається вікно можливостей.",
    ],
    EventType.THREAT: [
        "Відчувається небезпека поряд.",
        "Щось загрозливе наближається.",
        "Тривога охоплює без видимої причини.",
        "Обстановка стає напруженою.",
        "Небезпечний сигнал не можна ігнорувати.",
    ],
    EventType.SHOCK: [
        "Несподівана подія вибиває з рівноваги.",
        "Те, чого ніхто не очікував, трапилось.",
        "Шокуюча новина приходить зненацька.",
        "Реальність різко міняється.",
        "Раптовий поворот подій.",
    ],
}

# (event_type, cumulative_probability) — must end at 1.0
_EVENT_DISTRIBUTION: list[tuple[EventType, float]] = [
    (EventType.IDLE,        0.40),
    (EventType.SOCIAL,      0.60),
    (EventType.OPPORTUNITY, 0.80),
    (EventType.THREAT,      0.95),
    (EventType.SHOCK,       1.00),
]


@dataclass
class WorldConfig:
    """Config for the simulation world."""
    agents: List[str]                         # list of agent_id in the world
    event_weights: dict = field(default_factory=dict)  # optional future override
    base_tick_interval: float = 1.0           # seconds between ticks (real-time)


class WorldEngine:
    """Generates events for NPCs. Simple MVP with weighted random events."""

    def __init__(self, config: WorldConfig):
        self.config = config
        self._tick = 0

    # ------------------------------------------------------------------
    # Event generation
    # ------------------------------------------------------------------

    def _pick_event_type(self) -> EventType:
        """Pick an event type using the default weighted distribution."""
        roll = random.random()
        for event_type, cumulative in _EVENT_DISTRIBUTION:
            if roll <= cumulative:
                return event_type
        return EventType.IDLE

    def _pick_other_agent(self, for_agent_id: str) -> Optional[str]:
        """Pick a random other agent from the world (excludes self)."""
        others = [a for a in self.config.agents if a != for_agent_id]
        return random.choice(others) if others else None

    def next_event(self, for_agent_id: str) -> WorldEvent:
        """
        Generate the next event for a specific NPC.

        Distribution:
        - 40% IDLE         (nothing happens)
        - 20% SOCIAL       (meet another agent; source_agent = random other)
        - 20% OPPORTUNITY  (something interesting)
        - 15% THREAT       (something dangerous)
        -  5% SHOCK        (unexpected)

        intensity: random 0.3–0.9
        """
        event_type = self._pick_event_type()
        intensity = round(random.uniform(0.3, 0.9), 2)

        source_agent: Optional[str] = None
        if event_type == EventType.SOCIAL:
            source_agent = self._pick_other_agent(for_agent_id)

        # Build description from templates
        templates = _DESCRIPTIONS.get(event_type, ["Щось трапилось."])
        template = random.choice(templates)

        if "{other}" in template:
            other_label = source_agent or "незнайомець"
            description = template.format(other=other_label)
        else:
            description = template

        return WorldEvent(
            event_type=event_type,
            intensity=intensity,
            source_agent=source_agent,
            description=description,
        )

    # ------------------------------------------------------------------
    # Time management
    # ------------------------------------------------------------------

    def advance(self) -> int:
        """Advance time by 1 tick. Returns current tick number."""
        self._tick += 1
        return self._tick

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------

    def run_simulation_step(
        self,
        states: Dict[str, NpcState],
        processor: "TickProcessor",
        agents_root: Path,
        openrouter_key: str,
    ) -> Dict[str, NpcState]:
        """
        One simulation step for ALL agents.

        1. advance()
        2. For each agent_id:
           - event = self.next_event(agent_id)
           - states[agent_id] = processor.process(...)
        3. Return updated states
        """
        self.advance()

        for agent_id in list(states.keys()):
            event = self.next_event(agent_id)
            states[agent_id] = processor.process(
                states[agent_id], event, agents_root, openrouter_key
            )

        return states
