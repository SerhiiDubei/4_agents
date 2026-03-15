"""
round_events.py — маппінг раунду → подія.

Кожен раунд — унікальна ситуація. Наприклад:
- "Ти береш {name} з собою на човен — і тільки її в цей раунд"
- "Ти ділишся останньою водою з {name1} і {name2}"

involved_count: скільки учасників у рішенні (1 = тільки один, N = кілька).
"""

from __future__ import annotations

import random
from typing import List, Optional

from storytell.story_params import RoundEvent, StoryParams

# Шаблони подій: involved_count 1
EVENTS_1 = [
    "Ти береш {name} з собою на човен — і тільки її в цей раунд.",
    "Ти довіряєш {name} ключ від сховища — більше нікому.",
    "Ти вибираєш {name} для спільної варти — тільки ви двоє.",
    "Ти ділишся з {name} останньою порцією — ніхто інший не бачить.",
    "Ти йдеш з {name} на розвідку — сам на сам.",
    "Ти відкриваєш {name} таємницю, яку нікому не казав.",
]

# Шаблони подій: involved_count 2
EVENTS_2 = [
    "Ти ділишся ресурсом з {name1} і {name2} — обом порівну.",
    "Ти обираєш {name1} і {name2} для спільної справи.",
    "Ти маєш вибрати: підтримати {name1} чи {name2} — не обох.",
]

# Шаблони подій: involved_count 3+ (всі)
EVENTS_ALL = [
    "Усі четверо — ти вирішуєш, кому довіритись більше.",
    "Загальний розподіл — кожен отримує частину за твоїм рішенням.",
]


def get_round_event(
    round_number: int,
    total_rounds: int,
    story_params: StoryParams,
    agent_ids: List[str],
    agent_names: dict = None,
    rng: Optional[random.Random] = None,
) -> RoundEvent:
    """
    Повертає RoundEvent для даного раунду.

    - round_number, total_rounds: контекст гри
    - story_params: загальний сторітейл (поки не використовується для вибору, але для консистентності)
    - agent_ids: список усіх агентів
    - agent_names: {agent_id: display_name}
    - rng: опційно для детермінованості

    involved_count вибирається з ймовірністю:
    - 1: часто (найбільш "читабельні" ситуації)
    - 2: рідше
    - all: рідко
    """
    rng = rng or random.Random(story_params.seed + round_number)
    names = agent_names or {}

    # Розподіл: 60% — 1 учасник, 25% — 2, 15% — всі
    roll = rng.random()
    if roll < 0.6:
        template = rng.choice(EVENTS_1)
        involved_count = 1
    elif roll < 0.85:
        template = rng.choice(EVENTS_2)
        involved_count = 2
    else:
        template = rng.choice(EVENTS_ALL)
        involved_count = len(agent_ids)

    return RoundEvent(
        round_number=round_number,
        template=template,
        involved_count=involved_count,
        description=template[:60] + "..." if len(template) > 60 else template,
    )


def get_participants_for_event(
    event: RoundEvent,
    agent_ids: List[str],
    focus_agent_id: str,
    seed: int = 0,
    rng: Optional[random.Random] = None,
) -> List[str]:
    """
    Повертає список agent_id учасників події (виключаючи focus_agent).

    focus_agent_id: хто приймає рішення (його не включаємо в participants).
    """
    others = [a for a in agent_ids if a != focus_agent_id]
    rng = rng or random.Random(seed + event.round_number)
    n = min(event.involved_count, len(others))
    return list(rng.sample(others, n))
