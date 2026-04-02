"""
test_decision_engine.py — validates role differentiation and context sensitivity.

Tests that:
1. Roles produce meaningfully different action distributions
2. Context (trust, betrayals, reasoning) shifts behavior
3. Temperature controls prediction spread
"""

import pytest
from pipeline.decision_engine import (
    CoreParams, AgentContext, action_distribution, choose_action,
)

# Role profiles (after ROLE_CORE_OVERLAYS applied)
SNAKE = CoreParams(cooperation_bias=25, deception_tendency=80, strategic_horizon=70, risk_appetite=65)
GAMBLER = CoreParams(cooperation_bias=20, deception_tendency=85, strategic_horizon=60, risk_appetite=80)
BANKER = CoreParams(cooperation_bias=70, deception_tendency=40, strategic_horizon=80, risk_appetite=40)
PEACEKEEPER = CoreParams(cooperation_bias=75, deception_tendency=25, strategic_horizon=70, risk_appetite=40)

CLEAN_CTX = AgentContext(
    round_number=1, total_rounds=10,
    trust_scores={"o1": 0.5}, observed_actions={"o1": 0.5},
)


class TestRoleDifferentiation:
    """Roles must produce meaningfully different behavior."""

    def test_snake_defects_more_than_peacekeeper(self):
        d_snake = action_distribution(SNAKE, CLEAN_CTX)
        d_pk = action_distribution(PEACEKEEPER, CLEAN_CTX)
        assert d_snake["full_defect"] > d_pk["full_defect"] * 1.5, \
            f"Snake defect {d_snake['full_defect']:.1%} should be >1.5x peacekeeper {d_pk['full_defect']:.1%}"

    def test_peacekeeper_cooperates_more_than_snake(self):
        d_snake = action_distribution(SNAKE, CLEAN_CTX)
        d_pk = action_distribution(PEACEKEEPER, CLEAN_CTX)
        assert d_pk["full_cooperate"] > d_snake["full_cooperate"] * 1.5, \
            f"Peacekeeper coop {d_pk['full_cooperate']:.1%} should be >1.5x snake {d_snake['full_cooperate']:.1%}"

    def test_snake_defect_dominates(self):
        """Snake's most probable action should be defection."""
        d = action_distribution(SNAKE, CLEAN_CTX)
        assert d["full_defect"] == max(d.values()), \
            f"Snake should defect most often, got {d}"

    def test_peacekeeper_coop_dominates(self):
        """Peacekeeper's most probable action should be full cooperation."""
        d = action_distribution(PEACEKEEPER, CLEAN_CTX)
        assert d["full_cooperate"] == max(d.values()), \
            f"Peacekeeper should cooperate most often, got {d}"

    def test_banker_prefers_cooperation(self):
        """Banker should prefer cooperation over defection."""
        d = action_distribution(BANKER, CLEAN_CTX)
        coop_total = d["conditional_cooperate"] + d["full_cooperate"]
        defect_total = d["full_defect"] + d["soft_defect"]
        assert coop_total > defect_total, \
            f"Banker coop {coop_total:.1%} should exceed defect {defect_total:.1%}"

    def test_extreme_roles_not_uniform(self):
        """Snake and peacekeeper (extreme roles) should have spread > 0.10."""
        for name, core in [("snake", SNAKE), ("peacekeeper", PEACEKEEPER)]:
            d = action_distribution(core, CLEAN_CTX)
            vals = list(d.values())
            spread = max(vals) - min(vals)
            assert spread > 0.10, \
                f"{name} distribution spread {spread:.3f} is too uniform: {d}"


class TestContextSensitivity:
    """Context should shift behavior meaningfully."""

    def test_high_trust_increases_cooperation(self):
        low_trust = AgentContext(round_number=5, total_rounds=10,
                                trust_scores={"o1": 0.1}, observed_actions={"o1": 0.5})
        high_trust = AgentContext(round_number=5, total_rounds=10,
                                 trust_scores={"o1": 0.9}, observed_actions={"o1": 0.5})
        d_low = action_distribution(BANKER, low_trust)
        d_high = action_distribution(BANKER, high_trust)
        assert d_high["full_cooperate"] > d_low["full_cooperate"], \
            f"High trust coop {d_high['full_cooperate']:.1%} should > low trust {d_low['full_cooperate']:.1%}"

    def test_betrayals_increase_defection(self):
        no_betrayal = AgentContext(round_number=5, total_rounds=10,
                                  trust_scores={"o1": 0.5}, observed_actions={"o1": 0.5},
                                  betrayals_received=0)
        many_betrayals = AgentContext(round_number=5, total_rounds=10,
                                     trust_scores={"o1": 0.5}, observed_actions={"o1": 0.5},
                                     betrayals_received=5)
        d_clean = action_distribution(PEACEKEEPER, no_betrayal)
        d_hurt = action_distribution(PEACEKEEPER, many_betrayals)
        assert d_hurt["full_defect"] > d_clean["full_defect"], \
            f"Betrayed peacekeeper defect {d_hurt['full_defect']:.1%} should > clean {d_clean['full_defect']:.1%}"

    def test_reasoning_hint_defect_shifts_snake(self):
        no_hint = AgentContext(round_number=5, total_rounds=10,
                               trust_scores={"o1": 0.4}, observed_actions={"o1": 0.5})
        defect_hint = AgentContext(round_number=5, total_rounds=10,
                                  trust_scores={"o1": 0.4}, observed_actions={"o1": 0.5},
                                  reasoning_hint="зраджу вкраду не довіряю")
        d_no = action_distribution(SNAKE, no_hint)
        d_def = action_distribution(SNAKE, defect_hint)
        assert d_def["full_defect"] > d_no["full_defect"], \
            f"Defect hint should increase defection: {d_def['full_defect']:.1%} vs {d_no['full_defect']:.1%}"

    def test_reasoning_hint_coop_shifts_peacekeeper(self):
        no_hint = AgentContext(round_number=5, total_rounds=10,
                               trust_scores={"o1": 0.5}, observed_actions={"o1": 0.5})
        coop_hint = AgentContext(round_number=5, total_rounds=10,
                                trust_scores={"o1": 0.5}, observed_actions={"o1": 0.5},
                                reasoning_hint="співпрацюю довіряю разом підтримаю")
        d_no = action_distribution(PEACEKEEPER, no_hint)
        d_coop = action_distribution(PEACEKEEPER, coop_hint)
        assert d_coop["full_cooperate"] > d_no["full_cooperate"], \
            f"Coop hint should increase cooperation: {d_coop['full_cooperate']:.1%} vs {d_no['full_cooperate']:.1%}"

    def test_observed_defection_triggers_retaliation(self):
        peaceful = AgentContext(round_number=5, total_rounds=10,
                                trust_scores={"o1": 0.5}, observed_actions={"o1": 0.66})
        hostile = AgentContext(round_number=5, total_rounds=10,
                               trust_scores={"o1": 0.5}, observed_actions={"o1": 0.0})
        d_peace = action_distribution(BANKER, peaceful)
        d_hostile = action_distribution(BANKER, hostile)
        assert d_hostile["full_defect"] > d_peace["full_defect"], \
            "Observed defection should increase defection"


class TestTemperature:
    """Risk appetite controls prediction spread."""

    def test_low_risk_sharper_distribution(self):
        """Low risk appetite = more predictable (sharper peak)."""
        low_risk = CoreParams(cooperation_bias=50, deception_tendency=50,
                              strategic_horizon=50, risk_appetite=10)
        high_risk = CoreParams(cooperation_bias=50, deception_tendency=50,
                               strategic_horizon=50, risk_appetite=90)
        d_low = action_distribution(low_risk, CLEAN_CTX)
        d_high = action_distribution(high_risk, CLEAN_CTX)
        spread_low = max(d_low.values()) - min(d_low.values())
        spread_high = max(d_high.values()) - min(d_high.values())
        assert spread_low > spread_high, \
            f"Low risk spread {spread_low:.3f} should > high risk spread {spread_high:.3f}"


class TestSampling:
    """Sampling should respect probability distribution."""

    def test_100_samples_cover_all_actions(self):
        """Over 100 samples, all 4 actions should appear at least once."""
        actions_seen = set()
        for i in range(100):
            r = choose_action(GAMBLER, CLEAN_CTX, seed=i)
            actions_seen.add(r.action)
        assert len(actions_seen) == 4, \
            f"Gambler should use all 4 actions over 100 samples, got {actions_seen}"

    def test_snake_defects_most_in_samples(self):
        """Snake should defect most often over 200 samples."""
        counts = {0.0: 0, 0.33: 0, 0.66: 0, 1.0: 0}
        for i in range(200):
            r = choose_action(SNAKE, CLEAN_CTX, seed=i)
            counts[r.action] += 1
        assert counts[0.0] > counts[1.0], \
            f"Snake should defect more than cooperate: defect={counts[0.0]} coop={counts[1.0]}"
