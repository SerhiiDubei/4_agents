# TIME WARS — Progress Log

## Аналіз стану (2026-03-20)

### Що ПРАЦЮЄ правильно
- `support`/`gift` коди — механіка правильна. +0с в акторa = нормально (він сам не отримує). Ціль отримує 120с. Логується як `target_delta_seconds`.
- `assign_roles()` — ролі призначаються рандомно кожну гру з `roles.json`. `Player.role_id` правильно встановлюється в сесії.
- `ROLE_CORE_OVERLAYS` — правильно застосовуються на базові CORE params.

### Виявлені ПРОБЛЕМИ

#### КРИТ-1: Агенти завжди cooperate, ніколи не steal
**Де:** `pipeline/decision_engine.py` → `_action_scores()`
**Причина:** `strategic_score = -abs(action - 0.66) * sh * 0.4`
Агенти з високим `strategic_horizon` (60-85) отримують великий штраф за будь-яке відхилення від 0.66.
Навіть snake (cooperation_bias 33) не стіляє бо strategic penalty тримає їх на 0.66.
**Рішення:** Зменшити вагу strategic_score АБО додати `risk_appetite` як позитивний фактор для steal у high-risk ролей.

#### КРИТ-2: Character skills не впливають на гру
**Де:** `game_modes/time_wars/skills.py`
**Статус:** Не перевірено — наступний крок

#### КРИТ-3: Core timer mechanics
**Статус:** Треба уточнити що саме відсутнє

### Наступні кроки (пріоритет)
1. [ ] Пофіксити `decision_engine.py` — збалансувати scoring щоб snake/gambler roles реально stealили
2. [ ] Перевірити `skills.py` — чи skills.apply_* функції повертають правильні значення
3. [ ] Запустити тестову гру після фіксів і перевірити логи
4. [ ] Commit + push на гіт

### Локальні зміни (не закомічено)
- Всі зміни в `E:/Work Stuff/4 agents/4_agents/` — тільки локально
- Гілка: `feature/time-wars-roles`
- Стейджу немає, є modified files (agent MEMORY/STATES, game_engine.py, frontend components)
