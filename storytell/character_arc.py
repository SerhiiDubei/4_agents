"""
character_arc.py — відстеження дуг персонажів між раундами.

СЕР-6: Character Arc відсутній → персонажі не розвиваються між раундами.
Рішення: CharacterArcTracker накопичує зради/кооперації по кожному агенту
і генерує текстовий опис поточної дуги для промптів LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CharacterArc:
    """
    Дуга одного персонажа: підраховує моральні рішення між раундами.
    """
    agent_id: str
    betrayal_count: int = 0         # скільки разів зрадив інших
    cooperation_count: int = 0      # скільки разів підтримав інших
    betrayed_by_count: int = 0      # скільки разів зраджений
    # Ключові моменти: (раунд, текст-мітка)
    key_moments: List[tuple] = field(default_factory=list)

    def arc_label(self) -> str:
        """Поточна дуга персонажа — коротка українська мітка."""
        total = self.betrayal_count + self.cooperation_count
        if total == 0:
            return "невизначений"
        ratio = self.betrayal_count / total
        if ratio > 0.7:
            return "зрадник"
        elif ratio > 0.5:
            return "прагматик, схильний до зради"
        elif ratio > 0.3:
            return "обережний прагматик"
        elif self.betrayed_by_count >= 2 and ratio < 0.3:
            return "жертва, яка все одно допомагала"
        elif ratio < 0.15:
            return "вірний союзник"
        else:
            return "обачний"

    def arc_trend(self) -> str:
        """Тренд — чи стає персонаж більш циничним чи відкритим."""
        # Дивимось на останні key_moments
        if len(self.key_moments) < 2:
            return ""
        recent = self.key_moments[-3:]
        betrayals = sum(1 for _, label in recent if "зрад" in label)
        coops = sum(1 for _, label in recent if "кооп" in label)
        if betrayals > coops:
            return "все більш цинічний"
        elif coops > betrayals:
            return "відкривається до довіри"
        return ""

    def to_prompt_str(self) -> str:
        """Компактний рядок для промптів LLM."""
        label = self.arc_label()
        parts = [f"Дуга: {label}"]
        if self.betrayal_count or self.cooperation_count:
            parts.append(f"(зрад: {self.betrayal_count}, кооп: {self.cooperation_count})")
        trend = self.arc_trend()
        if trend:
            parts.append(f"— {trend}")
        return " ".join(parts)


class CharacterArcTracker:
    """
    Відстежує дуги всіх персонажів протягом гри.
    Оновлюється після кожного раунду.
    """

    def __init__(self) -> None:
        self._arcs: Dict[str, CharacterArc] = {}

    def _get(self, agent_id: str) -> CharacterArc:
        if agent_id not in self._arcs:
            self._arcs[agent_id] = CharacterArc(agent_id=agent_id)
        return self._arcs[agent_id]

    def update(
        self,
        round_num: int,
        round_actions: Dict[str, Dict[str, float]],
    ) -> None:
        """
        Оновлює дуги після раунду.

        round_actions: {agent_id: {target_id: cooperation_value (0.0..1.0)}}
        Значення < 0.4 = зрада, >= 0.4 = кооперація.
        """
        for agent_id, targets in round_actions.items():
            arc = self._get(agent_id)
            for target_id, val in targets.items():
                if agent_id == target_id:
                    continue
                t_arc = self._get(target_id)
                # Нормалізуємо: може бути dict з полем cooperation
                coop_val = float(val) if isinstance(val, (int, float)) else float(val.get("cooperation", 0.5))
                if coop_val < 0.4:
                    arc.betrayal_count += 1
                    t_arc.betrayed_by_count += 1
                    arc.key_moments.append((round_num, f"зрадив у раунді {round_num}"))
                else:
                    arc.cooperation_count += 1
                    arc.key_moments.append((round_num, f"кооп у раунді {round_num}"))

    def get_arc_context(
        self,
        agent_names: Optional[Dict[str, str]] = None,
        max_agents: int = 8,
    ) -> str:
        """
        Повертає форматований рядок дуг для LLM промпту.

        Включає лише агентів з хоча б 1 рішенням (решта — невизначені).
        """
        names = agent_names or {}
        lines: List[str] = []
        for aid, arc in list(self._arcs.items())[:max_agents]:
            name = names.get(aid) or aid.split("_")[-1][:8]
            lines.append(f"  {name}: {arc.to_prompt_str()}")
        return "\n".join(lines) if lines else ""

    def get_arc(self, agent_id: str) -> Optional[CharacterArc]:
        """Повертає дугу конкретного агента або None."""
        return self._arcs.get(agent_id)
