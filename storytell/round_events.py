"""
round_events.py — маппінг раунду → подія.

Кожен раунд — унікальна ситуація. Наприклад:
- "Ти береш {name} з собою на човен — і тільки її в цей раунд"
- "Ти ділишся останньою водою з {name1} і {name2}"

involved_count: скільки учасників у рішенні (1 = тільки один, N = кілька).
СЕР-7: Dynamic Event Escalation — події ескалують відповідно до прогресу раунду.
"""

from __future__ import annotations

import random
from typing import List, Optional

from storytell.story_params import RoundEvent, StoryParams

# === РАННІ РАУНДИ (0–39% прогресу) — знайомство, перші рішення ===

EVENTS_EARLY_1 = [
    "Ти береш {name} з собою на чергування — перше знайомство в дії.",
    "Ти ділишся з {name} частиною свого пайку — невеличкий жест довіри.",
    "Ти вибираєш {name} для спільної роботи — хочеш зрозуміти, чи можна на нього покластись.",
    "Ти розповідаєш {name} про свої плани — перевірка, чи він зберігає таємниці.",
    "Ти пропонуєш {name} змінитись вахтою — подивишся, чи він надійний.",
]

EVENTS_EARLY_2 = [
    "Ти ділишся ресурсом з {name1} і {name2} — перевіряєш, хто з них чесний.",
    "Ти обираєш {name1} і {name2} для спільної задачі — перше відчуття команди.",
    "Ти розповідаєш щось важливе {name1} і {name2} — дивишся, як вони реагують.",
]

# === СЕРЕДНІ РАУНДИ (40–74% прогресу) — наростаюча напруга, складні вибори ===

EVENTS_MID_1 = [
    "Ти береш {name} з собою на човен — і тільки його в цей раунд.",
    "Ти довіряєш {name} ключ від сховища — більше нікому.",
    "Ти ділишся з {name} останньою порцією — ніхто інший не бачить.",
    "Ти йдеш з {name} на розвідку — сам на сам, без свідків.",
    "Ти відкриваєш {name} таємницю, яку нікому не казав — і ставиш на нього.",
    "Ти покладаєш на {name} відповідальність за ресурс — він може ним скористатись.",
]

EVENTS_MID_2 = [
    "Ти маєш вибрати: підтримати {name1} чи {name2} — не обох.",
    "Ресурсів вистачить лише двом: ти обираєш {name1} і {name2}.",
    "Ти берешь {name1} і {name2} на небезпечну ділянку — якщо щось піде не так, вони зазнають.",
    "Ти довіряєш секретну інформацію {name1} і {name2} — один з них може зрадити.",
]

EVENTS_MID_ALL = [
    "Загальний перерозподіл — кожен отримує частину за твоїм рішенням.",
    "Усі зібрались разом — ти вирішуєш, кому довіритись більше.",
]

# === ФІНАЛЬНІ РАУНДИ (75%+ прогресу) — кульмінація, виживання ===

EVENTS_CLIMAX_1 = [
    "Є лише одне місце на порятунок — ти береш {name} і нікого більше.",
    "Ти кладеш {name} на терези рятівного рішення — і всі це бачать.",
    "Останній ресурс дістається {name} — твій вибір визначить його долю.",
    "Ти прикриваєш {name} власним тілом в критичний момент — або ні.",
    "Ти відкриваєш {name} місце схрону — останнє, що у тебе залишилось.",
]

EVENTS_CLIMAX_2 = [
    "Два місця порятунку, три людини: ти обираєш {name1} і {name2} — третій залишається.",
    "Остання перевірка: ти ставиш на {name1} і {name2} — і всі ставки зроблені.",
    "Хто виживе — {name1} чи {name2}? Ти вирішуєш просто зараз.",
]

EVENTS_CLIMAX_ALL = [
    "Фінальний момент — кожен отримує рівно стільки, скільки заслужив. Або ні.",
    "Остання ніч на острові — рішення прийнято назавжди.",
    "Вирок вже виноситься — кожен дізнається, ким він насправді був.",
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

    СЕР-7: events ескалують за прогресом:
    - 0–39%: ранні (знайомство, перші довіри)
    - 40–74%: середні (напруга, складні вибори)
    - 75%+: фінальні (кульмінація, виживання)

    involved_count розподіл:
    - Ранні: 65% × 1, 25% × 2, 10% × всі
    - Середні: 55% × 1, 30% × 2, 15% × всі
    - Фінальні: 45% × 1, 35% × 2, 20% × всі (більше колективних рішень наприкінці)
    """
    rng = rng or random.Random(story_params.seed + round_number)

    # Визначаємо фазу гри (0.0 → 1.0)
    progress = round_number / max(1, total_rounds)

    roll = rng.random()

    if progress < 0.40:
        # Ранні раунди: знайомство, перші довіри
        if roll < 0.65:
            template = rng.choice(EVENTS_EARLY_1)
            involved_count = 1
        elif roll < 0.90:
            template = rng.choice(EVENTS_EARLY_2)
            involved_count = 2
        else:
            template = rng.choice(EVENTS_MID_ALL)
            involved_count = len(agent_ids)

    elif progress < 0.75:
        # Середні раунди: наростаюча напруга
        if roll < 0.55:
            template = rng.choice(EVENTS_MID_1)
            involved_count = 1
        elif roll < 0.85:
            template = rng.choice(EVENTS_MID_2)
            involved_count = 2
        else:
            template = rng.choice(EVENTS_MID_ALL)
            involved_count = len(agent_ids)

    else:
        # Фінальні раунди: кульмінація
        if roll < 0.45:
            template = rng.choice(EVENTS_CLIMAX_1)
            involved_count = 1
        elif roll < 0.80:
            template = rng.choice(EVENTS_CLIMAX_2)
            involved_count = 2
        else:
            template = rng.choice(EVENTS_CLIMAX_ALL)
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
