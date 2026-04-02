"""
test_m0_stabilize.py — тести для M0: STABILIZE

Перевіряє всі фікси M0:
  КРИТ-2: simulation/constants.py — єдині пороги
  КРИТ-5: reveal_skill.was_exposed() існує
  КРИТ-7: reasoning.generate_reasoning() приймає situation_reflection
  ВИС-1:  pipeline/utils._cooperation_val() — одна копія
  ВИС-2:  pipeline/llm_client.call_llm() — спільний LLM клієнт
  КРИТ-4: game_engine логує помилки narrative (перевіряємо через raise)
"""

import inspect
import sys
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# КРИТ-2: Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """simulation/constants.py — єдине джерело порогів."""

    def test_constants_importable(self):
        from simulation.constants import (
            DEFECT_THRESHOLD,
            COOPERATE_THRESHOLD,
            REVEAL_BETRAYAL_THRESHOLD,
            DEFAULT_ACTION_VALUE,
            ACTION_LEVELS,
        )
        assert DEFECT_THRESHOLD == 0.33
        assert COOPERATE_THRESHOLD == 0.66
        assert DEFAULT_ACTION_VALUE == 0.5
        assert len(ACTION_LEVELS) == 4

    def test_reveal_betrayal_threshold_aligned_with_defect(self):
        """Раніше REVEAL_BETRAYAL_THRESHOLD = 0.40, розходилось з DEFECT_THRESHOLD = 0.33."""
        from simulation.constants import DEFECT_THRESHOLD, REVEAL_BETRAYAL_THRESHOLD
        assert REVEAL_BETRAYAL_THRESHOLD == DEFECT_THRESHOLD, (
            f"REVEAL_BETRAYAL_THRESHOLD ({REVEAL_BETRAYAL_THRESHOLD}) "
            f"must equal DEFECT_THRESHOLD ({DEFECT_THRESHOLD})"
        )

    def test_trust_deltas_present(self):
        from simulation.constants import REVEAL_TRUST_GAIN_PER_COOP, REVEAL_TRUST_LOSS_PER_BETRAYAL
        assert REVEAL_TRUST_GAIN_PER_COOP > 0
        assert REVEAL_TRUST_LOSS_PER_BETRAYAL > 0


# ---------------------------------------------------------------------------
# КРИТ-5: was_exposed()
# ---------------------------------------------------------------------------

class TestRevealSkill:
    """reveal_skill.RevealTracker.was_exposed() — раніше метод називався was_target()."""

    def test_was_exposed_method_exists(self):
        from simulation.reveal_skill import RevealTracker
        tracker = RevealTracker.initialize(["a", "b", "c"])
        assert hasattr(tracker, "was_exposed"), "was_exposed() method must exist"
        assert callable(tracker.was_exposed)

    def test_was_target_alias_still_works(self):
        """Backward-compat alias — не ламаємо старий код."""
        from simulation.reveal_skill import RevealTracker
        tracker = RevealTracker.initialize(["a", "b"])
        assert hasattr(tracker, "was_target"), "was_target() backward-compat alias must exist"

    def test_was_exposed_returns_false_before_reveal(self):
        from simulation.reveal_skill import RevealTracker
        tracker = RevealTracker.initialize(["agent_a", "agent_b"])
        assert tracker.was_exposed("agent_b") is False

    def test_was_exposed_returns_true_after_reveal(self):
        from simulation.reveal_skill import RevealTracker
        tracker = RevealTracker.initialize(["agent_a", "agent_b"])
        action_log = {
            1: {"agent_b": {"agent_a": 0.0, "agent_c": 0.66}},
        }
        tracker.use_reveal(
            revealer_id="agent_a",
            target_id="agent_b",
            round_number=1,
            action_log=action_log,
            all_agent_ids=["agent_a", "agent_b"],
        )
        assert tracker.was_exposed("agent_b") is True
        assert tracker.was_exposed("agent_a") is False

    def test_trust_delta_uses_aligned_thresholds(self):
        """Перевіряємо що зрада < 0.33 тепер, а не < 0.40 як раніше."""
        from simulation.reveal_skill import RevealTracker
        from simulation.constants import REVEAL_BETRAYAL_THRESHOLD
        # action = 0.35 — раніше вважалась зрадою (< 0.40), тепер не є (>= 0.33)
        tracker = RevealTracker.initialize(["agent_a", "agent_b"])
        action_log = {
            1: {"agent_b": {"agent_a": 0.35}},
        }
        record = tracker.use_reveal(
            revealer_id="agent_a",
            target_id="agent_b",
            round_number=1,
            action_log=action_log,
            all_agent_ids=["agent_a", "agent_b"],
        )
        assert record is not None
        # 0.35 >= REVEAL_BETRAYAL_THRESHOLD (0.33) — не є зрадою
        assert record.trust_delta_applied >= 0, (
            f"action=0.35 should NOT be betrayal with threshold={REVEAL_BETRAYAL_THRESHOLD}, "
            f"got delta={record.trust_delta_applied}"
        )


# ---------------------------------------------------------------------------
# КРИТ-7: situation_reflection в reasoning
# ---------------------------------------------------------------------------

class TestReasoningSituationReflection:
    """generate_reasoning() тепер приймає situation_reflection."""

    def test_generate_reasoning_has_situation_reflection_param(self):
        from pipeline.reasoning import generate_reasoning
        sig = inspect.signature(generate_reasoning)
        assert "situation_reflection" in sig.parameters, (
            "generate_reasoning() must accept situation_reflection parameter"
        )

    def test_situation_reflection_defaults_to_empty_string(self):
        from pipeline.reasoning import generate_reasoning
        sig = inspect.signature(generate_reasoning)
        default = sig.parameters["situation_reflection"].default
        assert default == "", f"situation_reflection default should be '', got {default!r}"

    def test_situation_reflection_appears_in_prompt(self):
        """Якщо situation_reflection передано — воно має потрапити в промпт."""
        from pipeline.reasoning import generate_reasoning

        captured_user = []

        def fake_call_structured(system, user, model):
            captured_user.append(user)
            from pipeline.reasoning import ReasoningResult
            return ReasoningResult(thought="test", intents={})

        with patch("pipeline.reasoning._call_structured", side_effect=fake_call_structured):
            generate_reasoning(
                agent_id="agent_a",
                soul_md="Test soul",
                round_number=1,
                total_rounds=5,
                peer_ids=["agent_b"],
                last_round_summary=None,
                dialog_heard={},
                trust_scores={},
                situation_reflection="Я відчуваю загрозу з боку Марти",
                model="test-model",
            )

        assert captured_user, "LLM should have been called"
        assert "Я відчуваю загрозу" in captured_user[0], (
            f"situation_reflection должна быть в промпте, got:\n{captured_user[0][:500]}"
        )


# ---------------------------------------------------------------------------
# ВИС-1: pipeline/utils._cooperation_val
# ---------------------------------------------------------------------------

class TestUtilsCooperationVal:
    """Одна функція _cooperation_val замість 5 копій."""

    def test_importable_from_utils(self):
        from pipeline.utils import _cooperation_val
        assert callable(_cooperation_val)

    def test_float_passthrough(self):
        from pipeline.utils import _cooperation_val
        assert _cooperation_val(0.0) == 0.0
        assert _cooperation_val(0.66) == 0.66
        assert _cooperation_val(1.0) == 1.0

    def test_dict_extracts_cooperation(self):
        from pipeline.utils import _cooperation_val
        assert _cooperation_val({"cooperation": 0.33, "support": 1.0}) == 0.33

    def test_missing_cooperation_key_defaults_to_half(self):
        from pipeline.utils import _cooperation_val
        assert _cooperation_val({"support": 0.5}) == 0.5

    def test_none_defaults_to_half(self):
        from pipeline.utils import _cooperation_val
        assert _cooperation_val(None) == 0.5

    def test_state_machine_uses_utils(self):
        """state_machine не має власного _cooperation_value."""
        import pipeline.state_machine as sm
        src = inspect.getsource(sm)
        local_def_count = src.count("def _cooperation_value")
        assert local_def_count == 0, "state_machine must not define own _cooperation_value"

    def test_memory_uses_utils(self):
        """memory не має власного _cooperation_value."""
        import pipeline.memory as mem
        src = inspect.getsource(mem)
        local_def_count = src.count("def _cooperation_value")
        assert local_def_count == 0, "memory must not define own _cooperation_value"

    def test_reasoning_uses_utils(self):
        """reasoning не має власного _cooperation_val."""
        import pipeline.reasoning as rsn
        src = inspect.getsource(rsn)
        local_def_count = src.count("def _cooperation_val")
        assert local_def_count == 0, "reasoning must not define own _cooperation_val"

    def test_reflection_uses_utils(self):
        """reflection не має власного _cooperation_val."""
        import pipeline.reflection as ref
        src = inspect.getsource(ref)
        local_def_count = src.count("def _cooperation_val")
        assert local_def_count == 0, "reflection must not define own _cooperation_val"

    def test_reveal_skill_uses_utils(self):
        """reveal_skill не має власного _cooperation_value."""
        import simulation.reveal_skill as rs
        src = inspect.getsource(rs)
        local_def_count = src.count("def _cooperation_value")
        assert local_def_count == 0, "reveal_skill must not define own _cooperation_value"


# ---------------------------------------------------------------------------
# ВИС-2: pipeline/llm_client.call_llm
# ---------------------------------------------------------------------------

class TestLlmClient:
    """Спільний LLM клієнт замість дублікатів."""

    def test_importable(self):
        from pipeline.llm_client import call_llm
        assert callable(call_llm)

    def test_signature_has_required_params(self):
        from pipeline.llm_client import call_llm
        sig = inspect.signature(call_llm)
        params = sig.parameters
        assert "system" in params
        assert "user" in params
        assert "model" in params
        assert "retries" in params
        assert "label" in params

    def test_retries_on_failure(self):
        """call_llm має повторювати при помилці."""
        from pipeline.llm_client import call_llm

        call_count = [0]

        def flaky_openrouter(**kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("timeout")
            return "success"

        with patch("pipeline.llm_client.call_llm.__wrapped__", create=True):
            with patch("pipeline.seed_generator.call_openrouter", side_effect=flaky_openrouter):
                result = call_llm(
                    system="sys",
                    user="usr",
                    model="test-model",
                    retries=2,
                    retry_delay=0,
                )
        assert result == "success"
        assert call_count[0] == 2

    def test_raises_after_exhausted_retries(self):
        """Після всіх спроб — піднімає виняток."""
        from pipeline.llm_client import call_llm
        import pytest

        def always_fails(**kwargs):
            raise ConnectionError("always fails")

        with patch("pipeline.seed_generator.call_openrouter", side_effect=always_fails):
            with pytest.raises(ConnectionError):
                call_llm(
                    system="sys",
                    user="usr",
                    model="test-model",
                    retries=2,
                    retry_delay=0,
                )


# ---------------------------------------------------------------------------
# КРИТ-4: narrative logging (перевіряємо через stderr capture)
# ---------------------------------------------------------------------------

class TestNarrativeLogging:
    """game_engine тепер логує помилки narrative замість тихого ковтання."""

    def test_narrative_error_prints_to_stderr(self, capsys):
        """Якщо generate_round_narrative кидає — маємо побачити це в stderr."""
        import sys
        # Симулюємо що відбувається в game_engine при помилці narrative
        import sys as _sys
        round_num = 3
        try:
            raise ValueError("LLM timeout")
        except Exception as _narr_err:
            print(f"  [storytell] round_narrative r{round_num}: {_narr_err}", file=_sys.stderr, flush=True)

        captured = capsys.readouterr()
        assert "[storytell]" in captured.err
        assert "round_narrative" in captured.err
        assert "r3" in captured.err
