# REFACTOR AUDIT — Чеклист перед рефакторингом

> **Створено:** март 2025. Не забути при рефакторингу — цей етап попрацював на славу.

---

## 1. ІДЕЇ, ЩО ПОТРІБНО ЗБЕРЕГТИ

### 1.1 API `/api/games-summary` (server/main.py)

| Що | Де | Чому |
|---|---|---|
| **Нормалізація середнього балу** | Рядки 1698–1721 | Ігри мають різні шкали (17 vs 28 vs 70 бал/раунд). Формула: `game_avg = mean(бал/раунд)`, `scale = 100/game_avg`, `agent_norm = (бал/раунд)*scale`. Усереднити за кількістю ігор. **100 = середній по грі.** |
| **Всі агенти з roster** | Рядки 1639–1642 | Таблиця показує всіх з roster (навіть 0 ігор). `agent_names_order` з roster, не з games. |
| **agentTotals, agentRoundsPlayed, agentGamesPlayed, agentAvgPerRound** | return dict | Фронтенд очікує ці поля. agentAvgPerRound — нормалізований. |

### 1.2 GamesResultsView.tsx

| Що | Де | Чому |
|---|---|---|
| **agentAvgPerRound з API** | averageScore() | Пріоритет API. Fallback (agentTotals/agentRoundsPlayed) тільки для legacy. |
| **min-w-max + tabular-nums + whitespace-nowrap** | table, td з числами | Без цього колонки зливаються, числа накладаються. |
| **font-pixel для чисел** | всі числові td | Моноширинний шрифт для вирівнювання. |
| **GamesSummaryResponse.agentAvgPerRound** | interface | API віддає нормалізований середній (100=середній). |

### 1.3 LeaderboardView.tsx

| Що | Де | Чому |
|---|---|---|
| **Сортування за agentAvgPerRound** | names.sort() | Чесно для різної кількості ігор. Нормалізований показник. |
| **tabular-nums на всіх числах** | td | Вирівнювання колонок. |

### 1.4 deploy.py + start_servers.py

| Що | Де | Чому |
|---|---|---|
| **deploy.py — єдиний скрипт** | docstring | Не розбивати на окремі. Один entry point. |
| **start_servers.py** | Main 8000 + TW 5174 | deploy.py викликає цей скрипт. |
| **_free_port для 8000, 5174** | deploy.py, start_servers.py | Windows: netstat + taskkill. Інакше порти залишаються зайняті. |

---

## 2. СИЛЬНІ МІСЦЯ

- **Чітка формула нормалізації** — задокументована, перевірена на реальних даних (17 vs 28 vs 70).
- **IDEA-коментарі в коді** — легко шукати при рефакторингу: `grep -r "IDEA"`.
- **Deploy automation** — один скрипт, різні режими (--build, --restart).
- **Єдина source of truth** — API рахує agentAvgPerRound, фронтенд не дублює логіку.
- **Правило .cursor/rules** — deploy-workflow.mdc тримає контекст для AI.

---

## 3. СЛАБКІ МІСЦЯ / РИЗИКИ

| Проблема | Де | Рекомендація |
|----------|-----|--------------|
| **Різні GamesSummaryResponse** | GamesResultsView vs LeaderboardView | Уніфікувати interface (runs, agentNames тощо). |
| **LeaderboardView.names** | Побудова з winsByAgent + agentTotals | Можна брати `agentNames` з API для консистентності з roster. |
| **deploy._free_port** | Тільки Windows | Додати Linux/macOS (fuser) або документувати. |
| **totalRounds у GamesResultsView** | Рахується з games | Тільки для підпису "XXX раундів". Не впливає на середній. |
| **Великі game_*.json** | Логи | При багатьох іграх games-summary може повільно завантажувати. Розглянути пагінацію/кеш. |

---

## 4. ЧЕКЛИСТ ДЛЯ РЕФАКТОРИНГУ

Перед великим рефакторингом:

- [ ] Пройтися по `grep -r "IDEA"` — усі згадані місця враховані.
- [ ] Не міняти формулу agent_avg_per_round без перевірки на різних шкалах ігор.
- [ ] Зберегти `min-w-max`, `tabular-nums`, `whitespace-nowrap` для таблиць з числами.
- [ ] deploy.py залишити єдиним entry point для deploy.
- [ ] Після змін — `python deploy.py` і перевірка 8000, 5174.

---

## 5. ФАЙЛИ ДЛЯ ПЕРЕВІРКИ

```
server/main.py          — games-summary, agent_avg_per_round
frontend/.../GamesResultsView.tsx
frontend/.../LeaderboardView.tsx
deploy.py
start_servers.py
.cursor/rules/deploy-workflow.mdc
```

---

*Цей етап ніколи не буде забутий.*
