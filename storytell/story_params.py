"""
story_params.py — параметри драматичної архітектури.

Всі поля, що формують контекст історії.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StoryParams:
    """
    Загальний сторітейл — генерується з random seed.

    Відповідає на: який рік, місце, дійові особи, проблема, завязка.
    """

    seed: int
    year: str  # напр. "1943", "сучасність"
    place: str  # напр. "острів у Тихому океані", "бункер під Києвом"
    characters: List[str]  # ролі/типи: "капітан", "медик", "штурман"
    problem: str  # центральна проблема: "ресурси закінчуються", "хтось зрадник"
    setup: str  # завязка: "корабель потонув, ви на плоту"
    genre: str = "drama"  # drama, thriller, survival
    mood: str = "tense"  # tense, desperate, hopeful, paranoid
    stakes: str = ""  # що на кону: "виживання", "втеча"

    def to_context_str(self) -> str:
        """Компактний текст для промптів."""
        parts = [
            f"Рік: {self.year}. Місце: {self.place}.",
            f"Завязка: {self.setup}.",
            f"Проблема: {self.problem}.",
            f"Ролі: {', '.join(self.characters)}.",
        ]
        if self.stakes:
            parts.append(f"На кону: {self.stakes}.")
        return " ".join(parts)


@dataclass
class RoundEvent:
    """
    Подія раунду — що саме відбувається в цьому раунді.

    Маппить абстрактне "зрада/підтримка" на конкретну ситуацію.
    """

    round_number: int
    template: str  # напр. "Ти береш {name} з собою на човен — і тільки її в цей раунд."
    involved_count: int  # 1..N — скільки учасників у цьому рішенні
    description: str = ""  # короткий опис для логу
    # Якщо involved_count=1: один конкретний учасник
    # Якщо involved_count>1: кілька учасників

    def format(self, agent_names: dict = None,
               focus_agent: str = None,
               participants: List[str] = None) -> str:
        """
        Підставляє імена в template.

        agent_names: {agent_id: display_name}
        focus_agent: хто приймає рішення (опційно)
        participants: список agent_id учасників події (для involved_count>1)
        """
        names = agent_names or {}
        text = self.template

        def _dn(aid: str) -> str:
            return names.get(aid) or aid.split("_")[-1][:8]

        if participants:
            if len(participants) == 1:
                text = text.replace("{name}", _dn(participants[0]))
            else:
                # Для кількох: {name1}, {name2} або {names}
                names_str = ", ".join(_dn(p) for p in participants)
                text = text.replace("{names}", names_str)
                for i, p in enumerate(participants):
                    text = text.replace(f"{{name{i+1}}}", _dn(p))

        return text
