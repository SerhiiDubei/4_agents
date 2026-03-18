# TIME WARS — Аналіз 6×1000 симуляцій та стан системи

*Дата: 2026-03-18 | 6 пачок по 1000 ігор | Повний аудит + balance patch*

---

## 1. ЕВОЛЮЦІЯ БАЛАНСУ — 6 ПАЧОК

| Пачка | Агент | Зміни | Snake | Banker | Нічиїх |
|---|---|---|---|---|---|
| v1 | рандом | базова | 21.3% | 6.3% | 5.3% |
| v2 | heuristic | mock survival | 20.0% | 10.4% | 5.6% |
| v3 | heuristic | tie fix | 20.2% | 11.4% | **0%** |
| v4 | role-bias | role weights | 19.7% | 17.3% | 0% |
| v5 | role-bias | multiplier bug fix | 16.7% | **30.8%** | 0% |
| **v6** | role-bias | **1.5x mult + retuned** | **18.2%** | **18.2%** | **0%** |

> Очікуваний % = 16.7%. Ціль: всі ролі ±3% від очікуваного.

---

## 2. ФІНАЛЬНИЙ БАЛАНС — v6

### Відсоток перемог
| Роль | % перемог | # перемог | Avg місце | Очікується |
|---|---|---|---|---|
| Змій (role_snake) | **18.2%** | 364 | 3.38 | 16.7% |
| Банкір (role_banker) | **18.2%** | 182 | 3.32 | 16.7% |
| Авантюрист (role_gambler) | 15.8% | 158 | 3.62 | 16.7% |
| Миротворець (role_peacekeeper) | 14.8% | 296 | 3.60 | 16.7% |

### Хто вилітає першим (v6)
| Роль | % перших виліт |
|---|---|
| Миротворець | 18.2% |
| Авантюрист | 17.8% |
| Змій | 15.3% |
| Банкір | 15.0% |

> **Результат**: Усі ролі між 15–18.2% — відмінна рівновага!

### Розподіл дій — v6 (%)
| Роль | cooperate | steal | use_code | pass |
|---|---|---|---|---|
| Змій | 26.3% | **41.1%** | 20.0% | 12.7% |
| Банкір | **52.5%** | 0% | **23.5%** | 24.1% |
| Авантюрист | 38.5% | 28.1% | 20.4% | 13.0% |
| Миротворець | **50.2%** | 14.7% | 22.4% | 12.7% |

### Тривалість ігор (v6)
```
Раундів:  17–20 (середнє 18.0, σ=0.6)
Тіків:    середнє 185.8
Нічиїх:   0%
```

---

## 3. МАТЕМАТИЧНИЙ АНАЛІЗ РОЛЕЙ (фінальні значення)

### Steal EV (v6 параметри)
| Роль | Roll | P(success) | P(partial) | P(fail) | Penalty fail | EV |
|---|---|---|---|---|---|---|
| Base | d20 | 30% | 35% | 35% | -15с | **+15.25с** |
| Змій | d20+1 | 35% | 35% | 30% | -5с | **+21.25с** (+39%) |
| Авантюрист | d20 | 30% | 35% | 35% | -25с | **+13.25с** (варіанс↑) |

### Banker code EV (1.5x multiplier — тепер реально працює)
| Код | Звичайний | Banker (1.5x) | Вартість | Efficiency |
|---|---|---|---|---|
| mini_boost | 60с | **90с** | 14 mana | 6.4с/mana |
| vampire (self) | 90с | **135с** | 40 mana | 3.4с/mana |

---

## 4. ПОВНИЙ СПИСОК ВИПРАВЛЕНЬ

### Баги виправлені

| # | Баг | Місце | Статус |
|---|---|---|---|
| 1 | `elimination` vs `eliminated` event type + `target_id` vs `agent_id` | serve_time_wars.py JS | ✅ |
| 2 | Tie: 5.3% ігор без переможця | serve_time_wars.py | ✅ |
| 3 | `situation_below_count` threshold 60с → 333с | serve_time_wars.py | ✅ |
| 4 | Mock-агент вмирав з повним інвентарем | agent_context.py | ✅ |
| 5 | cooperate broken ternary — actor `timeSec` не оновлювався | serve_time_wars.py JS | ✅ |
| 6 | code_use — `timeSec` і `mana` не оновлювались у UI | serve_time_wars.py JS | ✅ |
| 7 | **КРИТИЧНИЙ: `code_time_multiplier` Banker не застосовувалось** | loop.py | ✅ |

### Баги в дизайні виправлені

| # | Зміна | Де | Ефект |
|---|---|---|---|
| A | Snake roll bonus +2 → +1 | roles.json | Snake 21.3% → 18.2% |
| B | Banker code_time_multiplier 1.5x (реально спрацьовує) | loop.py + roles.json | Banker 6.3% → 18.2% |
| C | Role-specific action weights у mock-агента | agent_context.py | Realistic tactics |
| D | Survival heuristic для mock-агента | agent_context.py | Agents use codes before dying |

---

## 5. ДЕТАЛЬНІ ЗМІНИ ПО ФАЙЛАХ

### `game_modes/time_wars/roles.json`
```json
// Snake: steal_roll_bonus 2 → 1  (nerf)
// Banker: code_time_multiplier 1.5x (залишили, але тепер реально спрацьовує)
```

### `game_modes/time_wars/loop.py` — apply_code_use
```python
# Card format: ТЕПЕР застосовуємо role multiplier до effect_self_sec > 0
if effect_self_sec > 0:
    mult_result = skills.apply_on_code_use(pa.role_id, {...})
    mult = mult_result.get("code_time_multiplier", 1.0)
    if mult != 1.0:
        effect_self_sec = int(effect_self_sec * mult)
# mini_boost: Banker тепер отримує 90с замість 60с
```

### `game_modes/time_wars/agent_context.py` — get_agent_action_mock
```python
# Role-specific weights: [pass, coop, steal, code]
role_peacekeeper:  1, 4, 1, 3  # coop-focused, rare steal
role_snake:        1, 2, 3, 2  # steal-leaning
role_gambler:      1, 3, 2, 2  # moderate steal
role_banker:       1, 2, 0, 4  # code-focused, no steal
# + survival heuristic: use_code/steal priority when time_sec < base/4
```

### `serve_time_wars.py` — frontend JS
```javascript
// cooperate: actor timeSec += delta (fixed broken ternary)
// code_use: actor timeSec += selfDelta, target timeSec += targetDelta
// elimination: 'eliminated' → 'elimination', agent_id → target_id
// tie: winner = max(players, key=mana) when all eliminated same tick
```

---

## 6. ЩО ЗАЛИШИЛОСЬ

### OPEN (не критично)
1. **Snake EV +39%** — математично Snake ще трохи краще за базу через fail penalty -5 vs -15. Це прийнятно (design intent: Snake tolerated for risk-takers).
2. **Peacekeeper 14.8%** — трохи нижче 16.7%. Причина: coop-bias означає менше агресивних moves. `ON_GAME_END` bonus (+10/coop if no steal) потенційно strong але тільки для переможця.
3. **Vampire code** — 40 mana cost, rarely bought. Мала penetration: потребує high-mana момент.
4. **Snake roll>20 cosmetic** — roll=21 у логах коли d20=20+1. Не критично.

### WISHLIST
- Chart.js в HTML-звіті (time по раундах)
- Replay mode
- LLM-тестування з реальними API keys

---

## 7. КІЛЬКІСНЕ РЕЗЮМЕ

```
Загалом ігор:  6000 (6 × 1000)
Поточна версія: v6

БАЛАНС (v6):
  Snake:       18.2% win  ← було 21.3% (v1)
  Banker:      18.2% win  ← було  6.3% (v1)
  Gambler:     15.8% win  ← було 14.9% (v1)
  Peacekeeper: 14.8% win  ← було 15.4% (v1)

SPREAD (max-min): 3.4% (було: 15%)
Нічиїх:       0%   ← було 5.3% (v1)
Раундів:      17-20 (18.0 середнє)

ВИПРАВЛЕНО КРИТИЧНИХ БАГІВ: 7
ВИПРАВЛЕНО БАЛАНСОВИХ ПРОБЛЕМ: 4
```

---

*JSON дані: `sim_results_v6.json` | Всі попередні: v1–v5*
