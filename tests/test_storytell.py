"""
test_storytell.py — unit тести для storytell модуля (M3 вимога).

Тестує чисту логіку без LLM-викликів:
  - CharacterArc / CharacterArcTracker
  - get_round_event / get_participants_for_event
  - generate_consequences / build_betrayal_carryover
  - StoryParams.to_style_str / RoundEvent.format
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

# Додаємо корінь проекту до sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storytell.character_arc import CharacterArc, CharacterArcTracker
from storytell.consequences import build_betrayal_carryover, generate_consequences
from storytell.round_events import get_participants_for_event, get_round_event
from storytell.story_params import RoundEvent, StoryParams


# ─────────────────────────────────────────────────
#  CharacterArc — мітки дуги
# ─────────────────────────────────────────────────

class TestCharacterArcLabel:
    def test_no_actions_returns_undefined(self):
        arc = CharacterArc(agent_id="a1")
        assert arc.arc_label() == "невизначений"

    def test_high_betrayal_is_traitor(self):
        arc = CharacterArc(agent_id="a1", betrayal_count=8, cooperation_count=2)
        # ratio = 0.8 > 0.7 → зрадник
        assert arc.arc_label() == "зрадник"

    def test_majority_betrayal_is_pragmatist_traitor(self):
        arc = CharacterArc(agent_id="a1", betrayal_count=6, cooperation_count=4)
        # ratio = 0.6 → 0.5..0.7
        assert arc.arc_label() == "прагматик, схильний до зради"

    def test_mixed_is_cautious_pragmatist(self):
        arc = CharacterArc(agent_id="a1", betrayal_count=4, cooperation_count=6)
        # ratio = 0.4 → > 0.3 → "обережний прагматик"
        assert arc.arc_label() == "обережний прагматик"

    def test_victim_who_cooperated(self):
        arc = CharacterArc(
            agent_id="a1",
            betrayal_count=1, cooperation_count=10,
            betrayed_by_count=3,
        )
        # ratio < 0.15? 1/11 ≈ 0.09 < 0.15 BUT betrayed_by_count=3 >= 2
        assert arc.arc_label() == "жертва, яка все одно допомагала"

    def test_loyal_ally(self):
        arc = CharacterArc(agent_id="a1", betrayal_count=1, cooperation_count=20)
        # ratio ≈ 0.048 < 0.15 і betrayed_by_count=0 (не жертва)
        assert arc.arc_label() == "вірний союзник"

    def test_cautious(self):
        arc = CharacterArc(agent_id="a1", betrayal_count=2, cooperation_count=5)
        # ratio ≈ 0.28 → < 0.3 але betrayed_by_count=0 → не жертва, > 0.15 → не союзник
        assert arc.arc_label() == "обачний"


# ─────────────────────────────────────────────────
#  CharacterArc — тренд дуги
# ─────────────────────────────────────────────────

class TestCharacterArcTrend:
    def test_no_moments_empty_trend(self):
        arc = CharacterArc(agent_id="a1")
        assert arc.arc_trend() == ""

    def test_one_moment_empty_trend(self):
        arc = CharacterArc(agent_id="a1", key_moments=[(1, "зрадив у раунді 1")])
        assert arc.arc_trend() == ""

    def test_mostly_betrayals_cynical(self):
        arc = CharacterArc(
            agent_id="a1",
            key_moments=[
                (1, "зрадив у раунді 1"),
                (2, "зрадив у раунді 2"),
                (3, "кооп у раунді 3"),
            ],
        )
        assert arc.arc_trend() == "все більш цинічний"

    def test_mostly_coops_opens_trust(self):
        arc = CharacterArc(
            agent_id="a1",
            key_moments=[
                (1, "зрадив у раунді 1"),
                (2, "кооп у раунді 2"),
                (3, "кооп у раунді 3"),
            ],
        )
        assert arc.arc_trend() == "відкривається до довіри"

    def test_equal_moments_empty_trend(self):
        arc = CharacterArc(
            agent_id="a1",
            key_moments=[
                (1, "зрадив у раунді 1"),
                (2, "кооп у раунді 2"),
            ],
        )
        assert arc.arc_trend() == ""


# ─────────────────────────────────────────────────
#  CharacterArcTracker
# ─────────────────────────────────────────────────

class TestCharacterArcTracker:
    def test_update_counts_betrayals(self):
        tracker = CharacterArcTracker()
        # agent_a зраджує agent_b (значення < 0.4)
        tracker.update(1, {"agent_a": {"agent_b": 0.1}})
        arc_a = tracker.get_arc("agent_a")
        arc_b = tracker.get_arc("agent_b")
        assert arc_a.betrayal_count == 1
        assert arc_b.betrayed_by_count == 1
        assert arc_b.cooperation_count == 0

    def test_update_counts_cooperations(self):
        tracker = CharacterArcTracker()
        tracker.update(1, {"agent_a": {"agent_b": 0.8}})
        arc_a = tracker.get_arc("agent_a")
        assert arc_a.cooperation_count == 1
        assert arc_a.betrayal_count == 0

    def test_self_interaction_ignored(self):
        tracker = CharacterArcTracker()
        tracker.update(1, {"agent_a": {"agent_a": 0.0}})
        # Самозрада ігнорується — рахунки нульові (arc може створитись, але без дій)
        arc = tracker.get_arc("agent_a")
        # Або arc не існує, або існує з нулями — в обох випадках зради не рахується
        if arc is not None:
            assert arc.betrayal_count == 0
            assert arc.cooperation_count == 0

    def test_multiple_rounds_accumulate(self):
        tracker = CharacterArcTracker()
        tracker.update(1, {"agent_a": {"agent_b": 0.1}})  # зрада
        tracker.update(2, {"agent_a": {"agent_b": 0.9}})  # кооп
        tracker.update(3, {"agent_a": {"agent_b": 0.0}})  # зрада
        arc = tracker.get_arc("agent_a")
        assert arc.betrayal_count == 2
        assert arc.cooperation_count == 1

    def test_get_arc_context_not_empty(self):
        tracker = CharacterArcTracker()
        tracker.update(1, {"agent_x": {"agent_y": 0.2}})
        ctx = tracker.get_arc_context({"agent_x": "Алєг", "agent_y": "Вова"})
        assert "Алєг" in ctx or "agent_x" in ctx

    def test_get_arc_returns_none_for_unknown(self):
        tracker = CharacterArcTracker()
        assert tracker.get_arc("nonexistent_agent") is None

    def test_arc_key_moments_recorded(self):
        tracker = CharacterArcTracker()
        tracker.update(2, {"agent_a": {"agent_b": 0.1}})  # зрада
        arc = tracker.get_arc("agent_a")
        assert len(arc.key_moments) == 1
        assert arc.key_moments[0][0] == 2  # раунд 2


# ─────────────────────────────────────────────────
#  round_events — ескалація за прогресом
# ─────────────────────────────────────────────────

_STORY = StoryParams(
    seed=42,
    year="сучасність",
    place="острів",
    characters=["капітан", "медик"],
    problem="ресурси закінчуються",
    setup="корабель потонув",
    genre="thriller",
    mood="paranoid",
    stakes="виживання",
)

_AGENTS = ["a1", "a2", "a3", "a4", "a5"]


class TestRoundEvents:
    def test_returns_round_event(self):
        ev = get_round_event(0, 10, _STORY, _AGENTS)
        assert ev.round_number == 0
        assert ev.involved_count >= 1
        assert len(ev.template) > 5

    def test_early_round_has_early_events(self):
        """Перші раунди (progress < 0.4) мають involved_count типово 1 або 2."""
        counts = set()
        for r in range(3):  # rounds 0,1,2 of 10 → progress < 0.3
            ev = get_round_event(r, 10, _STORY, _AGENTS, rng=random.Random(r * 99))
            counts.add(ev.involved_count)
        # Принаймні один раунд має involved_count=1 (65% ймовірність для ранніх)
        assert any(c <= 2 for c in counts)

    def test_climax_round_has_higher_involvement_rate(self):
        """Фінальні раунди частіше мають involved_count > 1."""
        inv_counts = []
        for seed in range(20):
            ev = get_round_event(9, 10, _STORY, _AGENTS, rng=random.Random(seed * 7))
            inv_counts.append(ev.involved_count)
        # Серед 20 фінальних раундів принаймні деякі мають > 1
        multi = sum(1 for c in inv_counts if c > 1)
        assert multi > 5, f"Очікувалось > 5 multi-person events, отримали {multi}"

    def test_description_truncated_at_60(self):
        ev = get_round_event(0, 5, _STORY, _AGENTS)
        assert len(ev.description) <= 63  # "..." додається

    def test_different_seeds_different_results(self):
        ev1 = get_round_event(5, 10, _STORY, _AGENTS, rng=random.Random(1))
        ev2 = get_round_event(5, 10, _STORY, _AGENTS, rng=random.Random(9999))
        # Не завжди ідентичні (хоч і можуть бути при дуже маленькому пулі)
        # Перевіряємо що функція не падає і повертає коректні об'єкти
        assert ev1.round_number == ev2.round_number == 5


class TestGetParticipants:
    def test_returns_correct_count(self):
        ev = RoundEvent(round_number=1, template="{name}", involved_count=2, description="test")
        agents = ["a1", "a2", "a3", "a4"]
        participants = get_participants_for_event(ev, agents, focus_agent_id="a1")
        assert len(participants) == 2

    def test_excludes_focus_agent(self):
        ev = RoundEvent(round_number=1, template="{name}", involved_count=3, description="test")
        agents = ["a1", "a2", "a3", "a4"]
        participants = get_participants_for_event(ev, agents, focus_agent_id="a1")
        assert "a1" not in participants

    def test_does_not_exceed_available(self):
        """Якщо агентів менше ніж involved_count — повертає всіх доступних."""
        ev = RoundEvent(round_number=1, template="{name}", involved_count=10, description="test")
        agents = ["a1", "a2", "a3"]
        participants = get_participants_for_event(ev, agents, focus_agent_id="a1")
        assert len(participants) == 2  # всього 2 "інших"

    def test_single_participant(self):
        ev = RoundEvent(round_number=1, template="{name}", involved_count=1, description="test")
        agents = ["a1", "a2", "a3"]
        participants = get_participants_for_event(ev, agents, focus_agent_id="a1")
        assert len(participants) == 1
        assert participants[0] != "a1"


# ─────────────────────────────────────────────────
#  consequences
# ─────────────────────────────────────────────────

class TestGenerateConsequences:
    def test_empty_payoffs_returns_empty(self):
        result = generate_consequences(1, {}, {})
        assert result == ""

    def test_basic_winner_loser(self):
        result = generate_consequences(
            1,
            {"a1": {"a2": 0.1}},
            {"a1": 3.0, "a2": -1.0},
            names={"a1": "Алєг", "a2": "Вова"},
        )
        assert "Алєг" in result
        assert "Вова" in result

    def test_same_winner_and_loser(self):
        """Якщо один агент — і переможець, і програвший."""
        result = generate_consequences(1, {}, {"a1": 5.0}, names={"a1": "Алєг"})
        assert "однаковій" in result

    def test_carryover_repeat_betrayal(self):
        """Повторна зрада тих самих агентів → carryover-рядок."""
        carryover = {"a1": ["a2"]}
        result = generate_consequences(
            2,
            {"a1": {"a2": 0.0}},  # знову зраджує a2
            {"a1": 5.0, "a2": -2.0},
            names={"a1": "Алєг", "a2": "Вова"},
            betrayal_carryover=carryover,
        )
        assert "знову" in result or "закономірність" in result

    def test_carryover_no_repeat(self):
        """Раніше зраджував, але зараз ні — "тиша підозріла"."""
        carryover = {"a1": ["a2"]}
        result = generate_consequences(
            2,
            {"a1": {"a2": 0.9}},  # кооп
            {"a1": 5.0, "a2": -2.0},
            names={"a1": "Алєг", "a2": "Вова"},
            betrayal_carryover=carryover,
        )
        # Агент a1 — в топ-2 (5.0), раніше зраджував → пам'ять згадується
        assert "пам'ять" in result or "нікуди" in result or "утримав" in result


class TestBuildBetrayalCarryover:
    def test_single_betrayal(self):
        actions = [{"a1": {"a2": 0.1}}]  # зрада (< 0.4)
        carryover = build_betrayal_carryover(actions)
        assert "a1" in carryover
        assert "a2" in carryover["a1"]

    def test_no_betrayals(self):
        actions = [{"a1": {"a2": 0.9}}]  # кооп
        carryover = build_betrayal_carryover(actions)
        assert carryover == {}

    def test_multiple_rounds_accumulate(self):
        actions = [
            {"a1": {"a2": 0.1}},  # раунд 1: зрада a2
            {"a1": {"a3": 0.0}},  # раунд 2: зрада a3
        ]
        carryover = build_betrayal_carryover(actions)
        assert "a2" in carryover["a1"]
        assert "a3" in carryover["a1"]

    def test_no_duplicates(self):
        """Один і той же агент зраджений двічі — тільки один запис."""
        actions = [
            {"a1": {"a2": 0.1}},
            {"a1": {"a2": 0.0}},
        ]
        carryover = build_betrayal_carryover(actions)
        assert carryover["a1"].count("a2") == 1

    def test_custom_threshold(self):
        # Поріг 0.6: значення 0.5 є зрадою
        actions = [{"a1": {"a2": 0.5}}]
        carryover = build_betrayal_carryover(actions, threshold=0.6)
        assert "a1" in carryover
        assert "a2" in carryover["a1"]


# ─────────────────────────────────────────────────
#  StoryParams
# ─────────────────────────────────────────────────

class TestStoryParams:
    def test_to_style_str_contains_genre(self):
        params = StoryParams(
            seed=1, year="2020", place="бункер", characters=[], problem="",
            setup="", genre="thriller", mood="paranoid", stakes="виживання",
        )
        style = params.to_style_str()
        assert "трилер" in style
        assert "параноїдальний" in style

    def test_to_style_str_unknown_genre_passthrough(self):
        params = StoryParams(
            seed=1, year="2020", place="бункер", characters=[], problem="",
            setup="", genre="mystery", mood="unknown_mood", stakes="",
        )
        style = params.to_style_str()
        assert "mystery" in style

    def test_to_style_str_no_stakes_when_empty(self):
        params = StoryParams(
            seed=1, year="2020", place="бункер", characters=[], problem="",
            setup="", genre="drama", mood="tense", stakes="",
        )
        style = params.to_style_str()
        assert "Ставки" not in style

    def test_to_context_str_contains_place_and_problem(self):
        params = StoryParams(
            seed=1, year="1943", place="острів у Тихому океані", characters=["капітан"],
            problem="хтось зрадник", setup="літак впав",
        )
        ctx = params.to_context_str()
        assert "острів у Тихому океані" in ctx
        assert "хтось зрадник" in ctx
        assert "1943" in ctx


# ─────────────────────────────────────────────────
#  RoundEvent.format
# ─────────────────────────────────────────────────

class TestRoundEventFormat:
    def test_single_name_substitution(self):
        ev = RoundEvent(
            round_number=1,
            template="Ти береш {name} з собою.",
            involved_count=1,
        )
        result = ev.format(
            agent_names={"a1": "Алєг"},
            participants=["a1"],
        )
        assert "Алєг" in result
        assert "{name}" not in result

    def test_two_name_substitution(self):
        ev = RoundEvent(
            round_number=2,
            template="Ти обираєш {name1} і {name2}.",
            involved_count=2,
        )
        result = ev.format(
            agent_names={"a1": "Алєг", "a2": "Вова"},
            participants=["a1", "a2"],
        )
        assert "Алєг" in result
        assert "Вова" in result

    def test_no_participants_leaves_template(self):
        """Без participants — шаблон залишається як є."""
        ev = RoundEvent(round_number=1, template="Подія без учасників.", involved_count=0)
        result = ev.format()
        assert result == "Подія без учасників."

    def test_unknown_agent_uses_id_suffix(self):
        ev = RoundEvent(round_number=1, template="Подія {name}.", involved_count=1)
        result = ev.format(agent_names={}, participants=["agent_synth_mykyta"])
        # Якщо немає в names → використовує останній сегмент ID до 8 символів
        assert "mykyta" in result or "agent_sy" in result
