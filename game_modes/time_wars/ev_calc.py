"""
TIME WARS: розрахунок очікуваної цінності (EV) та рекомендованої ціни кодів.

EV_eq = base_minutes × k(type) × g(type, n)
EV_code = F(choices) × max_choice E[EV_eq]
P = ceil( (EV_code × X / φ(class)) × ρ(risk) × π(position) )
"""

from __future__ import annotations

from game_modes.time_wars.code_manifest import (
    CODE_CLASS_PRICE_MAX,
    CODE_CLASS_PRICE_MIN,
    CODE_CLASS_COEFFICIENT,
    RISK_LEVEL_MULTIPLIER,
    TYPE_COEFFICIENTS,
    TYPE_SELF,
    TYPE_STEAL,
    TYPE_GIVE,
    TYPE_MINUS_ALL,
    TYPE_PLUS_ALL_EXCEPT_ONE,
    TYPE_ZERO_SUM,
    X_MANA_PER_MINUTE,
    POSITION_NORMAL,
)


def group_g(effect_type: str, n: int) -> float:
    """Множник «скільки гравців зачеплено» для групових ефектів."""
    if effect_type in (TYPE_SELF, TYPE_STEAL, TYPE_GIVE, TYPE_ZERO_SUM):
        return 1.0
    if effect_type == TYPE_MINUS_ALL:
        return float(n)
    if effect_type == TYPE_PLUS_ALL_EXCEPT_ONE:
        return float(max(0, n - 1))
    return 1.0


def flexibility_f(num_choices: int) -> float:
    """Премія гнучкості: 2 choice → 1.05, 3+ → 1.10."""
    if num_choices <= 1:
        return 1.0
    if num_choices == 2:
        return 1.05
    return 1.10


def _outcome_ev_eq(
    outcome: dict,
    effect_type: str,
    n: int,
) -> float:
    """
    EV_eq для одного outcome: base_minutes × k(type) × g(type, n).
    Підтримує старий формат (effect_self, effect_other) та pricing_basis (base_minutes, manifest_type).
    """
    k = TYPE_COEFFICIENTS.get(effect_type, 1.0)
    g = group_g(effect_type, n)

    # Новий формат: pricing_basis.base_minutes + manifest_type
    basis = outcome.get("pricing_basis") or {}
    if basis:
        base_min = float(basis.get("base_minutes", 0))
        # manifest_type A–F можна мапити на type; якщо є — використати його k
        return base_min * k * g

    # Старий формат: effect_self, effect_other у хвилинах (або в одиницях, тоді вважаємо хвилинами)
    effect_self = float(outcome.get("effect_self", 0))
    effect_other = float(outcome.get("effect_other", 0))

    if effect_type == TYPE_SELF:
        base_min = effect_self
    elif effect_type == TYPE_STEAL:
        base_min = effect_self  # value = виграш собі
    elif effect_type == TYPE_GIVE:
        base_min = effect_other
    elif effect_type in (TYPE_MINUS_ALL, TYPE_PLUS_ALL_EXCEPT_ONE):
        base_min = max(abs(effect_self), abs(effect_other))
    else:
        base_min = effect_self + abs(effect_other)  # zero_sum: сумарний перерозподіл

    return base_min * k * g


def expected_value_eq(card: dict, n: int) -> float:
    """
    Очікувана цінність коду в еквівалентних хвилинах.
    EV_code = F × max over choices of (sum over outcomes p_i × EV_eq(o_i)).
    """
    choices = card.get("choices") or []
    if not choices:
        return 0.0

    effect_type = card.get("type", TYPE_SELF)

    best_ev = 0.0
    for ch in choices:
        outcomes = ch.get("outcomes") or []
        if not outcomes:
            continue
        total_p = sum(o.get("probability", 0) for o in outcomes)
        if abs(total_p - 1.0) > 0.001:
            continue
        ev_choice = 0.0
        for o in outcomes:
            p = o.get("probability", 0)
            ev_choice += p * _outcome_ev_eq(o, effect_type, n)
        best_ev = max(best_ev, ev_choice)

    F = flexibility_f(len(choices))
    return F * best_ev


def outcome_variance(card: dict, n: int) -> float:
    """Дисперсія EV по outcomes (для chaos-перевірки). Зважена по ймовірностях одного choice з max EV."""
    choices = card.get("choices") or []
    effect_type = card.get("type", TYPE_SELF)
    best_var = 0.0
    for ch in choices:
        outcomes = ch.get("outcomes") or []
        if not outcomes:
            continue
        probs = [o.get("probability", 0) for o in outcomes]
        if abs(sum(probs) - 1.0) > 0.001:
            continue
        evs = [_outcome_ev_eq(o, effect_type, n) for o in outcomes]
        mean_ev = sum(p * e for p, e in zip(probs, evs))
        var = sum(p * (e - mean_ev) ** 2 for p, e in zip(probs, evs))
        best_var = max(best_var, var)
    return best_var


def suggested_price(
    card: dict,
    n: int,
    position_multiplier: float = POSITION_NORMAL,
    x: float | None = None,
) -> int:
    """
    Рекомендована ціна: P = ceil( (EV_code × X / φ(class)) × ρ(risk) × π(position) ).
    Діапазон класу застосовується як обмеження.
    """
    from game_modes.time_wars.code_manifest import code_cost

    ev = expected_value_eq(card, n)
    class_key = card.get("class", "b")
    risk_level = card.get("risk_level", 0)
    rho = RISK_LEVEL_MULTIPLIER.get(risk_level, 1.0)
    # base_ev у формулі code_cost — тут ми передаємо EV_code; формула там (base_ev * k * x / phi).
    # Але code_cost очікує base_ev і type окремо; у нас EV вже враховує type через expected_value_eq.
    # Тому для suggested_price: P = (EV * X / phi) * rho * pos. EV вже «повний» (з k і g).
    x = x if x is not None else X_MANA_PER_MINUTE
    phi = CODE_CLASS_COEFFICIENT.get(class_key, 1.0)
    raw = (ev * x / phi) * rho * position_multiplier
    cost = max(1, round(raw))
    lo = CODE_CLASS_PRICE_MIN.get(class_key, 0)
    hi = CODE_CLASS_PRICE_MAX.get(class_key)
    if hi is not None and cost > hi:
        cost = hi
    if cost < lo:
        cost = lo
    return cost


def validate_code(
    card: dict,
    n: int,
    chaos_variance_min: float = 0.5,
    class_min_efficiency: dict[str, float] | None = None,
) -> dict:
    """
    Валідація коду: схема, діапазон класу, ефективність EV/cost, дисперсія для chaos.
    Повертає { "ok": bool, "errors": list, "ev": float, "suggested_price": int, "efficiency": float }.
    """
    errors: list[str] = []
    ev = expected_value_eq(card, n)
    pos_mod = card.get("position_modifier", POSITION_NORMAL)
    if isinstance(pos_mod, dict):
        pos_mod = pos_mod.get("multiplier_if_last", 1.0)
    p_suggest = suggested_price(card, n, position_multiplier=pos_mod)
    cost = card.get("cost_mana", card.get("base_cost_mana", 0))

    # Діапазон класу
    class_key = card.get("class")
    if class_key in CODE_CLASS_PRICE_MIN:
        lo, hi = CODE_CLASS_PRICE_MIN[class_key], CODE_CLASS_PRICE_MAX.get(class_key)
        if cost < lo:
            errors.append(f"cost_mana {cost} < class min {lo}")
        if hi is not None and cost > hi:
            errors.append(f"cost_mana {cost} > class max {hi}")

    # Ефективність (EV/cost): мінімум по класу
    efficiency = ev / cost if cost > 0 else 0.0
    thresholds = class_min_efficiency or {
        "c": 0.02,
        "b": 0.04,
        "a": 0.06,
        "S": 0.08,
    }
    if class_key and efficiency < thresholds.get(class_key, 0):
        errors.append(f"efficiency EV/cost {efficiency:.4f} below class threshold")

    # Chaos: дисперсія
    if card.get("risk_level") == 2:
        var = outcome_variance(card, n)
        if var < chaos_variance_min:
            errors.append(f"chaos code variance {var:.2f} < min {chaos_variance_min}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "ev": ev,
        "suggested_price": p_suggest,
        "efficiency": efficiency,
    }
