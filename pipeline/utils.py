"""
utils.py — спільні утиліти pipeline.

Раніше _cooperation_val() / _cooperation_value() були скопійовані у 5 файлах:
  state_machine.py, memory.py, reasoning.py, reflection.py, reveal_skill.py

Тепер один варіант тут, всі імпортують звідси.
"""

from typing import Any


def _cooperation_val(val: Any) -> float:
    """Extract cooperation action from legacy float or per-dim dict.

    Handles both:
      - legacy format: float (0.0–1.0)
      - multi-dim format: {"cooperation": float, "support": float}
    """
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5
