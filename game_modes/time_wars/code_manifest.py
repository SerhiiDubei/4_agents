"""
TIME WARS: Маніфест Кодів v1.0 — константи та формула вартості.

Базова одиниця: 1 хв = X мани.
Вартість коду = (Base_EV × k × Risk_Multiplier × Position_Modifier) × X.
Класи кодів: c, b, a, S — вищий клас = дорожчий діапазон і вищий коеф value.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Базова одиниця
# ---------------------------------------------------------------------------
X_MANA_PER_MINUTE = 20  # 1 хв = 20 мани (якір)

# ---------------------------------------------------------------------------
# 2. Типи хвилин (коефіцієнти value)
# ---------------------------------------------------------------------------
TYPE_SELF = "self"
TYPE_STEAL = "steal"
TYPE_GIVE = "give"
TYPE_MINUS_ALL = "minus_all"
TYPE_PLUS_ALL_EXCEPT_ONE = "plus_all_except_one"
TYPE_ZERO_SUM = "zero_sum"

TYPE_COEFFICIENTS: dict[str, float] = {
    TYPE_SELF: 1.0,
    TYPE_STEAL: 1.3,
    TYPE_GIVE: 0.5,
    TYPE_MINUS_ALL: 0.3,
    TYPE_PLUS_ALL_EXCEPT_ONE: 0.8,
    TYPE_ZERO_SUM: 1.1,
}

# ---------------------------------------------------------------------------
# 3. Risk price multiplier ρ(risk) — prospect theory: stable costs more, chaos less
# ---------------------------------------------------------------------------
RISK_STABLE = 1.15   # premium for predictability
RISK_RISK = 1.0
RISK_CHAOS = 0.85    # discount for variance

RISK_LEVEL_MULTIPLIER: dict[int, float] = {
    0: RISK_STABLE,
    1: RISK_RISK,
    2: RISK_CHAOS,
}

# ---------------------------------------------------------------------------
# 4. Position modifier
# ---------------------------------------------------------------------------
POSITION_NORMAL = 1.0
POSITION_COMEBACK = 0.7

# ---------------------------------------------------------------------------
# 5. Класи кодів (c, b, a, S)
# ---------------------------------------------------------------------------
CODE_CLASS_C = "c"
CODE_CLASS_B = "b"
CODE_CLASS_A = "a"
CODE_CLASS_S = "S"

# φ(class): efficiency — higher class = more EV per mana (used as divisor in price)
CODE_CLASS_COEFFICIENT: dict[str, float] = {
    CODE_CLASS_C: 0.5,
    CODE_CLASS_B: 0.75,
    CODE_CLASS_A: 1.0,
    CODE_CLASS_S: 1.25,
}
CLASS_EFFICIENCY_PHI = CODE_CLASS_COEFFICIENT  # alias for P = (EV*X/φ)*ρ*π

CODE_CLASS_PRICE_MIN: dict[str, int] = {
    CODE_CLASS_C: 6,
    CODE_CLASS_B: 20,
    CODE_CLASS_A: 40,
    CODE_CLASS_S: 60,
}

CODE_CLASS_PRICE_MAX: dict[str, int | None] = {
    CODE_CLASS_C: 16,
    CODE_CLASS_B: 30,
    CODE_CLASS_A: 60,
    CODE_CLASS_S: None,  # no upper bound
}

# ---------------------------------------------------------------------------
# 6. Сегменти ескалації
# ---------------------------------------------------------------------------
SEGMENT_BUDGET = (6, 16)
SEGMENT_STANDARD = (20, 30)
SEGMENT_PREMIUM = (40, 60)


def code_cost(
    base_ev: float,
    type_key: str,
    risk_multiplier: float | None = None,
    position_modifier: float = POSITION_NORMAL,
    x: float | None = None,
    class_key: str | None = None,
) -> int:
    """
    Вартість коду (мана): P = ceil( (EV×X / φ(class)) × ρ(risk) × π(position) ).
    Вищий клас (φ) → краща ефективність (менше мани за екв. хв); діапазон класу обрізає P.
    """
    x = x if x is not None else X_MANA_PER_MINUTE
    k = TYPE_COEFFICIENTS.get(type_key, 1.0)
    rho = risk_multiplier if risk_multiplier is not None else RISK_STABLE
    phi = CODE_CLASS_COEFFICIENT.get(class_key, 1.0) if class_key else 1.0
    raw = (base_ev * k * x / phi) * rho * position_modifier
    cost = max(1, round(raw))
    if class_key and class_key in CODE_CLASS_PRICE_MIN:
        lo = CODE_CLASS_PRICE_MIN[class_key]
        hi = CODE_CLASS_PRICE_MAX.get(class_key)
        if hi is not None and cost > hi:
            cost = hi
        if cost < lo:
            cost = lo
    return cost


def base_ev_from_cost(
    cost_mana: float,
    type_key: str,
    risk_multiplier: float = RISK_STABLE,
    position_modifier: float = POSITION_NORMAL,
    x: float | None = None,
    class_key: str | None = None,
) -> float:
    """Зворотній розрахунок: Base_EV з ціни. P = (EV×k×X/φ)×ρ×π => EV = P×φ/(k×X×ρ×π)."""
    x = x if x is not None else X_MANA_PER_MINUTE
    k = TYPE_COEFFICIENTS.get(type_key, 1.0)
    phi = CODE_CLASS_COEFFICIENT.get(class_key, 1.0) if class_key else 1.0
    denom = k * (x / phi) * risk_multiplier * position_modifier
    if denom <= 0:
        return 0.0
    return cost_mana / denom


def segment_for_cost(cost_mana: float) -> str:
    """Повертає назву сегменту за ціною (Budget / Standard / Premium / Comeback)."""
    if cost_mana <= SEGMENT_BUDGET[1]:
        return "Budget"
    if cost_mana <= SEGMENT_STANDARD[1]:
        return "Standard"
    if cost_mana <= SEGMENT_PREMIUM[1]:
        return "Premium"
    return "Comeback"


def risk_multiplier_from_level(risk_level: int) -> float:
    """Повертає Risk_Multiplier за risk_level (0, 1, 2)."""
    return RISK_LEVEL_MULTIPLIER.get(risk_level, RISK_STABLE)


def validate_card(card: dict) -> list[str]:
    """
    Валідація картки коду. Повертає список помилок (порожній якщо валідно).
    Перевірка: обов'язкові поля, class in (c,b,a,S), type у TYPE_COEFFICIENTS,
    risk_level in (0,1,2), сума probability у outcomes по кожному choice ≈ 1.0,
    cost_mana узгоджений з формулою (з допуском).
    """
    err: list[str] = []
    required = ("id", "class", "type", "base_ev", "cost_mana")
    for key in required:
        if key not in card:
            err.append(f"missing required field: {key}")
    if err:
        return err

    if card["class"] not in (CODE_CLASS_C, CODE_CLASS_B, CODE_CLASS_A, CODE_CLASS_S):
        err.append(f"invalid class: {card['class']}")
    if card["type"] not in TYPE_COEFFICIENTS:
        err.append(f"invalid type: {card['type']}")

    risk_level = card.get("risk_level", 0)
    if risk_level not in (0, 1, 2):
        err.append(f"invalid risk_level: {risk_level}")

    choices = card.get("choices", [])
    if not choices:
        err.append("choices must be non-empty (at least one option)")
    for i, ch in enumerate(choices):
        outcomes = ch.get("outcomes", [])
        if not outcomes:
            err.append(f"choice[{i}] has no outcomes")
            continue
        total_p = sum(o.get("probability", 0) for o in outcomes)
        if abs(total_p - 1.0) > 0.001:
            err.append(f"choice[{i}] outcomes probabilities sum to {total_p}, expected 1.0")

    # cost_mana vs formula (optional strict check)
    risk_mult = risk_multiplier_from_level(risk_level)
    pos_mod = card.get("position_modifier", POSITION_NORMAL)
    expected_cost = code_cost(
        card["base_ev"],
        card["type"],
        risk_multiplier=risk_mult,
        position_modifier=pos_mod,
        class_key=card["class"],
    )
    if abs(card["cost_mana"] - expected_cost) > 2:  # allow small rounding
        err.append(f"cost_mana {card['cost_mana']} does not match formula (expected ~{expected_cost})")

    return err
