"""
tests/test_social_fabric.py

Наглядні тести для social_fabric.py.
Запуск: python -m tests.test_social_fabric
        (з директорії 4_agents)

Кожен тест друкує BEFORE/AFTER таблицю щоб було зрозуміло що відбулось.
"""

import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.social_fabric import (
    SocialAction, SocialState, SocialFabric, AgentTurnContext,
    BUDGET_BASE, CAP_MULTIPLIER, DEFAULT_ALPHA,
)


# ---------------------------------------------------------------------------
# Helpers for pretty output
# ---------------------------------------------------------------------------

def sep(title: str = ""):
    line = "─" * 60
    if title:
        pad = (58 - len(title)) // 2
        print(f"\n┌{line}┐")
        print(f"│{' ' * pad}{title}{' ' * (58 - pad - len(title))}│")
        print(f"└{line}┘")
    else:
        print(f"\n{line}")


def show_budget(state: SocialState, label: str = ""):
    s = state.budget_summary()
    tag = f" [{label}]" if label else ""
    print(f"  {s['agent']}{tag}:")
    print(f"    base={s['base']}  alpha={s['alpha']}  bonus={s['bonus']}")
    print(f"    received_last={s['received_last']}")
    print(f"    pool={s['pool']}  cap={s['cap']}")


def show_trust(trust_map: dict, label: str = ""):
    if label:
        print(f"\n  Trust {label}:")
    for agent, peers in sorted(trust_map.items()):
        peer_str = "  ".join(f"{p}={v:.3f}" for p, v in sorted(peers.items()))
        print(f"    {agent}: {peer_str}")


# ---------------------------------------------------------------------------
# TEST 1 — SocialAction validation
# ---------------------------------------------------------------------------

def test_social_action_basic():
    sep("TEST 1: SocialAction — базова валідація")

    # Valid actions
    a1 = SocialAction(target="agent_b", type="share_food", value=0.8, visibility="private")
    a2 = SocialAction(target="agent_c", type="warn",       value=0.3, visibility="public")
    a3 = SocialAction(target="agent_d", type="alliance",   value=0.5)

    print("\n  ✅ Створено 3 дії:")
    for a in [a1, a2, a3]:
        print(f"     {a.to_dict()}")

    # Invalid type
    try:
        bad = SocialAction(target="agent_b", type="fly_away", value=0.5)
        print("  ❌ Мало впасти помилку але не впало")
    except ValueError as e:
        print(f"\n  ✅ Невідомий тип відкинуто: {e}")

    # Invalid visibility
    try:
        bad2 = SocialAction(target="agent_b", type="share_food", value=0.5, visibility="secret")
        print("  ❌ Мало впасти помилку але не впало")
    except ValueError as e:
        print(f"  ✅ Невідома visibility відкинута: {e}")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 2 — Budget recalculation
# ---------------------------------------------------------------------------

def test_budget_recalculation():
    sep("TEST 2: Budget — накопичення від взаємності")

    print("\n  Сценарій: Аня дає Борису 0.8, ніхто не дає Ані нічого (раунд 1)")
    print("            В раунді 2: Борис дає Ані 0.6, Гліб дає Ані 0.4")

    anya = SocialState(agent_id="Аня", alpha=0.5)
    print(f"\n  BEFORE (раунд 1 → 2):")
    show_budget(anya, "початок")

    # Раунд 1: Аня нічого не отримала
    anya.received_last_round = {}
    anya.recalculate_budget()
    print(f"\n  Раунд 1 — отримано: нічого")
    show_budget(anya, "після раунду 1")

    # Раунд 2: отримала від Бориса 0.6 і Гліба 0.4
    anya.received_last_round = {"Борис": 0.6, "Гліб": 0.4}
    anya.recalculate_budget()
    print(f"\n  Раунд 2 — отримано: Борис=0.6, Гліб=0.4 (сума=1.0)")
    show_budget(anya, "після раунду 2")
    expected = round(BUDGET_BASE + 0.5 * 1.0, 4)
    assert anya.budget_pool == expected, f"Expected {expected}, got {anya.budget_pool}"
    print(f"\n  pool={anya.budget_pool} == base({BUDGET_BASE}) + alpha(0.5) * received(1.0) = {expected} ✅")

    # CAP test: якщо всі дають забагато
    anya.received_last_round = {"Борис": 2.0, "Гліб": 2.0, "Діна": 2.0}
    anya.recalculate_budget()
    cap_val = round(BUDGET_BASE * CAP_MULTIPLIER, 4)
    print(f"\n  Якщо отримано 6.0 (забагато) → cap спрацьовує:")
    show_budget(anya, "cap test")
    assert anya.budget_pool == cap_val, f"Expected cap {cap_val}, got {anya.budget_pool}"
    print(f"  pool={anya.budget_pool} == cap({cap_val}) ✅")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 3 — Budget normalization
# ---------------------------------------------------------------------------

def test_budget_normalization():
    sep("TEST 3: Normalization — не можна витратити більше ніж є")

    print("\n  Сценарій: budget=1.0, агент хоче дати 0.8+0.7+0.6=2.1 (забагато)")

    state = SocialState(agent_id="Борис", budget_pool=1.0)
    actions = [
        SocialAction("Аня",  "share_food", 0.8, "public"),
        SocialAction("Гліб", "alliance",   0.7, "private"),
        SocialAction("Діна", "warn",        0.6, "public"),
    ]

    total_before = sum(a.value for a in actions)
    normalized = state.normalize_actions(actions)
    total_after = sum(a.value for a in normalized)

    print(f"\n  BEFORE нормалізації (total={total_before:.2f} > pool={state.budget_pool}):")
    for a in actions:
        print(f"    {a.target}: value={a.value}")

    print(f"\n  AFTER нормалізації (total={total_after:.4f} ≤ pool={state.budget_pool}):")
    for orig, norm in zip(actions, normalized):
        scale = norm.value / orig.value
        print(f"    {norm.target}: {orig.value} → {norm.value}  (×{scale:.3f})")

    assert abs(total_after - state.budget_pool) < 0.001, f"Total {total_after} should ≈ {state.budget_pool}"
    assert all(n.type == o.type for n, o in zip(normalized, actions)), "Types changed!"
    assert all(n.visibility == o.visibility for n, o in zip(normalized, actions)), "Visibility changed!"
    print(f"\n  Сума={total_after:.4f} ≈ budget={state.budget_pool} ✅  типи і visibility збережено ✅")

    # Under-budget: no change
    small_actions = [SocialAction("Аня", "share_food", 0.3)]
    unchanged = state.normalize_actions(small_actions)
    assert unchanged[0].value == 0.3
    print(f"  Under-budget (0.3 < 1.0): без змін ✅")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 4 — SocialFabric full round
# ---------------------------------------------------------------------------

def test_social_fabric_full_round():
    sep("TEST 4: SocialFabric — повний раунд з trust update")

    print("""
  Персонажі:
    Аня    — cooperation_bias=70, alpha=0.5
    Алєг   — cooperation_bias=40, alpha=0.8  (дуже reciprocal)
    Роман  — cooperation_bias=62, alpha=0.3  (мало reciprocal)

  Раунд 1 дії:
    Аня   → Алєг: share_food(0.7, private)
    Аня   → Роман: warn(0.3, public)
    Алєг  → Аня:  betray(0.0, private)    [нічого не дав фактично, value=0]
    Роман → Аня:  alliance(0.6, public)
    Роман → Алєг: ignore(0.0, public)
    """)

    # Setup SocialState для кожного
    anya  = SocialState.from_core("Аня",   {"reciprocity_sensitivity": 0.5})
    alieg = SocialState.from_core("Алєг",  {"reciprocity_sensitivity": 0.8})
    roman = SocialState.from_core("Роман", {"reciprocity_sensitivity": 0.3})

    fabric = SocialFabric()
    fabric.add(anya)
    fabric.add(alieg)
    fabric.add(roman)

    # Початковий trust (нейтральний)
    trust_map = {
        "Аня":   {"Алєг": 0.5, "Роман": 0.5},
        "Алєг":  {"Аня":  0.5, "Роман": 0.5},
        "Роман": {"Аня":  0.5, "Алєг":  0.5},
    }

    print("  Trust BEFORE:")
    show_trust(trust_map)

    # Дії раунду
    round_actions = {
        "Аня": [
            SocialAction("Алєг",  "share_food", 0.7, "private"),
            SocialAction("Роман", "warn",        0.3, "public"),
        ],
        "Алєг": [
            # betray = value 0 (нічого реально не дав)
            SocialAction("Аня", "betray", 0.0, "private"),
        ],
        "Роман": [
            SocialAction("Аня",  "alliance", 0.6, "public"),
            SocialAction("Алєг", "ignore",   0.0, "public"),
        ],
    }

    # Apply round
    trust_map = fabric.apply_round(round_actions, trust_map)

    print("\n  Trust AFTER раунду 1:")
    show_trust(trust_map)

    print("\n  Budget AFTER раунду 1 (для раунду 2):")
    for state in [anya, alieg, roman]:
        show_budget(state)
        print()

    # Assertions
    # Аня отримала від Романа 0.6 → її budget = 1.0 + 0.5*0.6 = 1.3
    assert abs(anya.budget_pool - 1.3) < 0.01, f"Аня budget: expected 1.3, got {anya.budget_pool}"
    print("  Аня budget = 1.3 (отримала 0.6 від Романа × alpha=0.5) ✅")

    # Алєг отримав від Ані 0.7 → його budget = 1.0 + 0.8*0.7 = 1.56 → cap=1.5
    assert abs(alieg.budget_pool - 1.5) < 0.01, f"Алєг budget: expected 1.5 (capped), got {alieg.budget_pool}"
    print("  Алєг budget = 1.5 (cap! raw=1.56, отримав 0.7 × alpha=0.8) ✅")

    # Роман витратив alliance(0.6)+ignore(0.0)=0.6 → leftover=0.4 → pool=1.4 (carryover!)
    assert abs(roman.budget_pool - 1.4) < 0.01, f"Роман budget: expected 1.4, got {roman.budget_pool}"
    print("  Роман budget = 1.4 (витратив 0.6 → leftover=0.4 → carryover) ✅")

    # Trust: Аня довіряє Роману більше (він дав alliance 0.6)
    trust_anya_roman = trust_map["Аня"]["Роман"]
    assert trust_anya_roman > 0.5, f"Аня має більше довіряти Роману, got {trust_anya_roman}"
    print(f"  trust[Аня→Роман] = {trust_anya_roman:.3f} > 0.5 ✅ (Роман дав alliance)")

    # Trust: Алєг довіряє Ані більше (Аня дала share_food)
    trust_alieg_anya = trust_map["Алєг"]["Аня"]
    assert trust_alieg_anya > 0.5, f"Алєг має більше довіряти Ані, got {trust_alieg_anya}"
    print(f"  trust[Алєг→Аня] = {trust_alieg_anya:.3f} > 0.5 ✅ (Аня дала share_food)")

    # Trust: Аня до Алєга дрейфує вниз (він нічого не дав, betray value=0)
    trust_anya_alieg = trust_map["Аня"]["Алєг"]
    assert trust_anya_alieg < 0.5, f"Аня має менше довіряти Алєгу, got {trust_anya_alieg}"
    print(f"  trust[Аня→Алєг] = {trust_anya_alieg:.3f} < 0.5 ✅ (Алєг нічого не дав — drift вниз)")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 5 — Drain prevention (один агент не стає нескінченно потужним)
# ---------------------------------------------------------------------------

def test_drain_prevention():
    sep("TEST 5: Drain prevention — cap захищає від зірки")

    print("""
  Сценарій: всі 3 агенти дають Зірці максимум
    Аня   → Зірка: 1.0
    Борис → Зірка: 1.0
    Гліб  → Зірка: 1.0
    Зірка → нікому нічого
    """)

    star = SocialState(agent_id="Зірка", alpha=0.5, budget_base=1.0)

    star.received_last_round = {"Аня": 1.0, "Борис": 1.0, "Гліб": 1.0}
    raw_would_be = 1.0 + 0.5 * 3.0
    star.recalculate_budget()

    cap = round(1.0 * CAP_MULTIPLIER, 4)
    print(f"  Без cap: budget = {raw_would_be}")
    print(f"  З cap ({CAP_MULTIPLIER}x): budget = {star.budget_pool}")
    assert star.budget_pool == cap, f"Expected {cap}, got {star.budget_pool}"
    print(f"\n  ✅ Зірка не може накопичити більше {cap} (= base × {CAP_MULTIPLIER})")

    # Водночас дарувальники витратили весь бюджет (1.0) і нічого не отримали
    donors = [SocialState(agent_id=n, alpha=0.5) for n in ["Аня", "Борис", "Гліб"]]
    for d in donors:
        d.budget_spent_last = 1.0   # витратили весь бюджет на Зірку
        d.received_last_round = {}
        d.recalculate_budget()
        # leftover = 1.0 - 1.0 = 0 → pool = 0 + 1.0 + 0 = 1.0
        print(f"  {d.agent_id} budget = {d.budget_pool} (витратили все → leftover=0 → pool=1.0)")
        assert d.budget_pool == 1.0, f"Expected 1.0, got {d.budget_pool}"

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 6 — Budget carryover (unspent accumulates)
# ---------------------------------------------------------------------------

def test_budget_carryover():
    sep("TEST 6: Carryover — незвитрачений budget накопичується")

    print("""
  Сценарій: Борис — стратег, зберігає бюджет 2 раунди, потім б'є
    Раунд 1: pool=1.0, витратив 0.3  → leftover=0.7
    Раунд 2: pool=0.7+1.0=1.7 → але cap=1.5 → pool=1.5 (capped)
             витратив 0.0 (нічого)   → leftover=1.5
    Раунд 3: pool=1.5+1.0=2.5 → cap=1.5 → pool=1.5 (capped)
             Але якщо також отримав 0.5 в раунді 2:
             pool=1.5+1.0+0.5*0.5=2.75 → cap=1.5
    """)

    boris = SocialState(agent_id="Борис", alpha=0.5)
    print(f"  СТАРТ: pool={boris.budget_pool}")

    # Раунд 1: витратив 0.3
    boris.budget_spent_last = 0.3
    boris.received_last_round = {}
    boris.recalculate_budget()
    print(f"\n  Після раунду 1 (spent=0.3, received=0):")
    show_budget(boris)
    # leftover=0.7, base=1.0, bonus=0 → raw=1.7 → cap=1.5
    assert boris.budget_pool == 1.5, f"Expected 1.5 (capped), got {boris.budget_pool}"
    print(f"  pool={boris.budget_pool} (1.0 base + 0.7 carryover = 1.7 → capped at 1.5) ✅")

    # Раунд 2: нічого не витратив, отримав 0.0
    boris.budget_spent_last = 0.0
    boris.received_last_round = {}
    boris.recalculate_budget()
    print(f"\n  Після раунду 2 (spent=0, received=0) — зберігає весь cap:")
    show_budget(boris)
    assert boris.budget_pool == 1.5, f"Expected 1.5 (cap), got {boris.budget_pool}"
    print(f"  pool={boris.budget_pool} ✅ (cap не росте вище 1.5 навіть з carryover)")

    # Раунд 2 альтернатива: витратив тільки 0.2 але отримав 0.8
    boris2 = SocialState(agent_id="Борис2", alpha=0.5, budget_pool=1.0)
    boris2.budget_spent_last = 0.2
    boris2.received_last_round = {"Аня": 0.8}
    boris2.recalculate_budget()
    print(f"\n  Варіант: spent=0.2, received=0.8:")
    show_budget(boris2)
    # leftover=0.8, base=1.0, bonus=0.4 → raw=2.2 → cap=1.5
    assert boris2.budget_pool == 1.5, f"Expected 1.5 (capped), got {boris2.budget_pool}"
    print(f"  pool={boris2.budget_pool} ✅ (0.8 leftover + 1.0 base + 0.4 bonus = 2.2 → cap 1.5)")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 7 — Mandatory action enforcement
# ---------------------------------------------------------------------------

def test_mandatory_action():
    sep("TEST 7: Mandatory action — агент не може мовчати")

    fabric = SocialFabric()
    for name in ["Аня", "Борис", "Гліб"]:
        fabric.add(SocialState(agent_id=name, alpha=0.5))

    peers = ["Борис", "Гліб"]

    # Порожній список → enforce вставляє дефолт
    empty = []
    enforced = fabric.enforce_minimum_action("Аня", empty, peers)
    print(f"\n  actions=[] → enforce → {[a.to_dict() for a in enforced]}")
    assert len(enforced) == 1, f"Expected 1 action, got {len(enforced)}"
    assert enforced[0].type == "ignore", f"Expected 'ignore', got {enforced[0].type}"
    assert enforced[0].value == 0.0, "ignore should cost 0 budget"
    print(f"  ✅ Вставлено: ignore→{enforced[0].target} (value=0, не витрачає budget)")

    # Непорожній список → не чіпаємо
    real_actions = [SocialAction("Борис", "share_food", 0.7)]
    unchanged = fabric.enforce_minimum_action("Аня", real_actions, peers)
    assert unchanged == real_actions
    print(f"  ✅ Непорожній список: не змінюється")

    # AgentTurnContext — must_act() завжди True
    ctx = AgentTurnContext(
        agent_id="Аня",
        round_number=3,
        total_rounds=10,
        peer_ids=peers,
        budget_pool=1.2,
        budget_carryover=0.2,
        trust_scores={"Борис": 0.6, "Гліб": 0.4},
        received_last_round={"Борис": 0.5},
        actions_given_last=[],
        public_messages={"Борис": "Привіт всім"},
        private_messages={},
        round_event="Знайдено їжу на північ від табору",
    )
    assert ctx.must_act() is True
    print(f"\n  AgentTurnContext.must_act() = {ctx.must_act()} ✅")
    print(f"  budget_summary: {ctx.budget_summary_str()}")

    llm_ctx = ctx.to_llm_context()
    assert "must_declare" in llm_ctx
    assert str(ctx.budget_pool) in llm_ctx["must_declare"]
    print(f"\n  LLM context 'must_declare' поле:")
    print(f"    {llm_ctx['must_declare']}")
    print(f"  ✅ Агент отримує чітку інструкцію що оголошення обов'язкове")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# TEST 8 — Target validation (hallucination filter)
# ---------------------------------------------------------------------------

def test_target_validation():
    sep("TEST 8: Target validation — фільтр галюцинацій")

    fabric = SocialFabric()
    peers = ["Аня", "Борис", "Гліб"]
    for name in peers:
        fabric.add(SocialState(agent_id=name, alpha=0.5))

    valid_peers = ["Борис", "Гліб"]

    # Simulate what game_engine does: filter actions against peer_set
    raw_dicts = [
        {"target": "Борис",        "type": "share_food",  "value": 0.5, "visibility": "public"},
        {"target": "agent_synth_a","type": "warn",        "value": 0.3, "visibility": "public"},  # hallucinated
        {"target": "Гліб",         "type": "alliance",    "value": 0.3, "visibility": "private"},
        {"target": "не_існує",     "type": "betray",      "value": 0.2, "visibility": "public"},  # hallucinated
    ]

    peer_set = set(valid_peers)
    valid_actions = []
    dropped = []
    for sa in raw_dicts:
        t = sa.get("target", "")
        if t not in peer_set:
            dropped.append(t)
            continue
        valid_actions.append(SocialAction(
            target=t,
            type=sa.get("type", "ignore"),
            value=float(sa.get("value", 0.0)),
            visibility=sa.get("visibility", "public"),
        ))

    print(f"\n  Вхідні дії (4 шт): {[d['target'] for d in raw_dicts]}")
    print(f"  Дійсні peers: {valid_peers}")
    print(f"  Відфільтровано (галюцинації): {dropped}")
    print(f"  Залишилось: {[a.to_dict() for a in valid_actions]}")

    assert len(dropped) == 2, f"Expected 2 dropped, got {len(dropped)}"
    assert "agent_synth_a" in dropped
    assert "не_існує" in dropped
    assert len(valid_actions) == 2, f"Expected 2 valid actions, got {len(valid_actions)}"
    assert valid_actions[0].target == "Борис"
    assert valid_actions[1].target == "Гліб"
    print(f"\n  ✅ 2 галюцинації відкинуто, 2 дійсні дії збережено")

    # After filtering, enforce_minimum should NOT trigger (we have 2 valid actions)
    enforced = fabric.enforce_minimum_action("Аня", valid_actions, valid_peers)
    assert len(enforced) == 2, "enforce_minimum should not inject when valid actions exist"
    print(f"  ✅ enforce_minimum не втручається (є дійсні дії)")

    # Edge case: ALL actions are hallucinated → enforce_minimum fires
    peer_set2 = set(valid_peers)
    only_bad = [d for d in raw_dicts if d["target"] not in peer_set2]
    valid_from_bad = []
    for sa in only_bad:
        t = sa.get("target", "")
        if t in peer_set2:
            valid_from_bad.append(SocialAction(t, sa.get("type", "ignore"), float(sa.get("value", 0.0))))
    # All dropped → empty → enforce fires
    enforced2 = fabric.enforce_minimum_action("Аня", valid_from_bad, valid_peers)
    assert len(enforced2) == 1
    assert enforced2[0].type == "ignore"
    print(f"  ✅ Якщо всі галюцинації — enforce_minimum вставляє ignore→{enforced2[0].target}")

    # Trust map: hallucinated targets should NOT appear
    trust_map = {p: {} for p in peers}
    sa_map = {"Аня": valid_actions}  # only 2 valid actions
    updated = fabric.apply_round(sa_map, trust_map)
    all_trust_targets = set()
    for peer_trust in updated.values():
        all_trust_targets.update(peer_trust.keys())
    assert "agent_synth_a" not in all_trust_targets
    assert "не_існує" not in all_trust_targets
    print(f"  ✅ Галюцинації не забруднюють trust_map")

    print("\n  PASS ✓")


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_social_action_basic,
        test_budget_recalculation,
        test_budget_normalization,
        test_social_fabric_full_round,
        test_drain_prevention,
        test_budget_carryover,
        test_mandatory_action,
        test_target_validation,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n  ❌ FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    sep()
    total = passed + failed
    print(f"\n  Результат: {passed}/{total} тестів пройшло", end="")
    if failed == 0:
        print("  🎉 Всі OK\n")
    else:
        print(f"  ⚠️  {failed} провалено\n")
        sys.exit(1)
