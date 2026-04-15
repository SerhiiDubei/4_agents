# WORKPLAN — 4 AGENTS
> Складено: 2026-03-19 | На основі аудиту логів та коду

---

## ДІАГНОЗ (що реально зламано)

| Проблема | Факт з логів | Де обрив |
|----------|-------------|----------|
| STEAL майже не відбувається | 0 стілів в 4 з 5 останніх ігор | cooperation_bias=70 → level>0.33 завжди → steal не тригеряється |
| COMM — декорація | 672 повідомлення, але 0/310 intent їх згадують | loop.py не передає last_messages в decision |
| Всі агенти однакові | Кожен зробив рівно 24 кооперації | CORE.json читається але не диференціює поведінку |
| Skills не тригеряться | Gambler/Snake ніколи не крадуть | Залежать від steal якого немає |
| Support = zombie | Код є, ніхто не викликає | choose_action(dim_id="support") — ніде не викликається |

---

## ПЛАН РОБІТ

### 🔴 TIER 1 — Кор механіка (гра має бути різною для кожного агента)

#### T1.1 — Виправити рішення про крадіжку
**Проблема:** Агент вирішує красти тільки якщо cooperation_level ≤ 0.33. Але з cooperation_bias=70 це ніколи не буває.
**Рішення:** Steal-рішення повинне залежати від `deception_tendency` + `risk_appetite` напряму, не тільки через cooperation_level.
**Файли:** `game_modes/time_wars/agent_context.py` → `_get_cooperation_levels_per_target()`, `compute_action_utility()`
**Результат:** Gambler (high deception) крадуть. Banker/Peacekeeper — ні.

#### T1.2 — Підключити COMM до рішень
**Проблема:** `last_messages` параметр є у функції, але loop.py передає `[]` або `None`.
**Рішення:** В `loop.py` зібрати повідомлення поточного раунду з `session.event_log` і передати в decision.
**Файли:** `game_modes/time_wars/loop.py` → `run_action_phase()` → передати `last_messages`
**Результат:** Якщо агент отримав DM з пропозицією → це впливає на рішення.

#### T1.3 — Диференціювати ролі через CORE.json
**Проблема:** Всі агенти мають схожий cooperation_bias (~70). Ролі не відображають різні CORE параметри.
**Рішення:** При призначенні ролі — застосовувати модифікатори до CORE параметрів (Gambler +deception, Banker +cooperation, Snake +risk).
**Файли:** `game_modes/time_wars/loop.py` → `assign_roles()`, `game_modes/time_wars/roles.json`
**Результат:** Агенти з різними ролями реально поводяться по-різному.

---

### 🟠 TIER 2 — Активувати zombie code

#### T2.1 — Скіли тригеряться (автоматично після T1.1)
Після того як steal працює → Gambler/Snake скіли починають тригеритися.
Перевірити: `ON_STEAL_FAIL`, `ON_STEAL_SUCCESS`, `ON_GAME_END` бонуси.

#### T2.2 — Support механіка: рішення
**Варіант A:** Реалізувати як окрему дію в COMM фазі (агент може "support" іншого → +trust)
**Варіант B:** Видалити код і не плутати систему
**Потребує:** твоє рішення яку механіку ти хотів мати

#### T2.3 — Game End бонуси відображаються
`apply_on_game_end()` викликається (line 485 loop.py) але результат не показується в фінальному екрані.
**Файли:** `game_modes/time_wars/loop.py` → фінальний summary, frontend результати

---

### 🟡 TIER 3 — Технічний борг (SEC + ROB)

#### SEC-1 — JWT валідація
Токени не перевіряються належним чином на expiry.
**Файл:** `db/auth.py`

#### SEC-2 — Rate limiting на LLM endpoints
Немає захисту від спаму до `/generate-question`, `/compile-soul`.
**Файл:** `server/main.py`

#### SEC-3 — Session TTL
Сесії не закінчуються. Старі сесії накопичуються.
**Файл:** `db/auth.py`, `server/main.py`

#### ROB-1 — LLM retry з backoff
При помилці LLM — немає retry. Гра ламається.
**Файл:** `pipeline/memory.py`, LLM call sites

#### ROB-2 — Dialog timeout
Якщо LLM не відповів — агент висить назавжди.
**Файл:** `game_modes/time_wars/loop.py`

#### ROB-3 — Атомарний запис MEMORY.json
Запис файлу може перерватись → корупція даних.
**Файл:** `pipeline/memory.py`

---

### 🔵 TIER 4 — Нові фічі (після стабілізації)

#### F1 — Візуалізація в frontend
- Показувати скіли агента в UI під час гри
- Показувати COMM повідомлення в реальному часі
- Показувати cooperation_levels per target (вже є в player_intent)

#### F2 — Human player
Можливість приєднатись до гри як один з гравців.

#### F3 — 4-гравцева архітектура
Дизайн механік для 4 агентів (зараз 13).

---

## ПОРЯДОК ВИКОНАННЯ

```
T1.1 → T1.2 → T1.3   ← без цього все інше не має сенсу
     ↓
T2.1 (автоматично)
T2.2 (після твого рішення по support)
T2.3
     ↓
SEC-1 → SEC-2 → SEC-3 → ROB-1 → ROB-2 → ROB-3
     ↓
F1 → F2 → F3
```

---

## КРИТЕРІЙ УСПІХУ

Після T1.x — в логах гри маємо бачити:
- [ ] Gambler краде в ≥ 30% раундів
- [ ] Snake краде в ≥ 20% раундів
- [ ] Banker ніколи не краде
- [ ] player_intent містить референс на COMM повідомлення
- [ ] Різні агенти мають різну кількість cooperations (не рівно 24 у всіх)

---

## ПИТАННЯ ДО ТЕБЕ

1. **Support механіка** — що вона мала робити? Лишити чи видалити?
2. **4-player vs поточний масштаб** — ти хочеш зменшити до 4 гравців або зберегти 13?
3. **Human player** — це пріоритет зараз чи після стабілізації?

## [2026-04-13 15:08 UTC] Щогодинна перевірка
- Стан: Всі T1.x задачі виконані (зафіксовано в "ВЖЕ ВИПРАВЛЕНО"). T2.1 активний автоматично (steal скіли триґеряться через ON_STEAL_SUCCESS/ON_STEAL_FAIL у loop.py). T2.2 потребує рішення від користувача. T2.3 був баг.
- Дія: Виправлено T2.3 — `log_to_html.py` фінальна таблиця тепер показує Роль, Стілів, Кооп, Бонус із `player_stats` у game_over event. Оновлено ARCHITECTURE.html статус.
- Тести: 61/61 GREEN
- Наступний пріоритет: T2.2 (Support механіка) — потребує рішення від користувача: Варіант A (COMM фаза +trust) або Варіант B (видалити). Після — T2.3 вже закрито, йти на SEC-1 (JWT валідація).

## [2026-04-13 16:06 UTC] Щогодинна перевірка
- Стан: Всі T1.x/T2.x задачі виконані. SEC-1/2/3 і ROB-3 вже були реалізовані (JWT, rate limit, session TTL, atomic write).
- Дія: Виправлено ROB-1 — `reasoning.py::_call_structured` мігровано з голого `call_openrouter` на `call_llm` (3 retries, 2s delay, label="reasoning"). Тепер агент не зависає при LLM помилці.
- Тести: 61/61 GREEN
- Наступний пріоритет: T2.2 (Support механіка — чекає рішення від користувача). Потім ROB-2 (Dialog timeout) та F1 (Візуалізація скілів у frontend).

## [2026-04-13] F1 TIER 4 — Frontend фічі завершено
- **F1.1 DONE** — `serve_time_wars.py`: live UI тепер показує скіли агента (`skill-tag` бейджі під роллю) з `role_assignment` event (поле `skills`).
- **F1.2 DONE** — `run_simulation_live.py` + `island_launcher.html`: comm_messages (діалог) включені в WE_EVENT payload та рендеряться в "Діалог" блоці Island WE-tab у реальному часі.
- **F1.3 DONE** — `island_launcher.html`: `intents` (cooperation_level per target) тепер рендеряться в "Наміри" блоці в кожного агента з прогрес-баром та кольором (зелений=кооп, червоний=зрада, жовтий=нейтраль).
- **log_to_html.py DONE** — `round_narrative` event тепер рендерується в HTML звіті TW (фіолетовий italic текст).
- Залишається відкритим: T2.2 (Support механіка — потребує рішення), F2 (Human player), F3 (4-player).

## [2026-04-13] T2.2 ISLAND — Support механіка (Variant A) реалізована
- **decision_engine.py**: `CoreParams.from_dict()` тепер автодеривує `support_bias` з personality якщо не задано: `max(10, min(90, coop*0.65 - dec*0.35 + 35))` → Алєг=26.7, Миролюб=86.8
- **game_engine.py**: після payoff phase — якщо `support ≥ 0.66` → trust effect: supporter→supported +0.05*val, supported→supporter +0.03*val. Логуються в `_support_events` → `RoundResult.support_events`
- **run_simulation_live.py**: `support_events` збагачені іменами і включені в WE_EVENT payload
- **island_launcher.html**: новий "💚 Підтримка" блок в WE-tab — показує хто кого підтримав, рівень та trust_delta
- Залишається: F2 (Human player), F3 (4-player)

## [2026-04-14 08:14 UTC] Щогодинна перевірка
- Стан: Всі T1-T2-SEC-ROB-F1-T5 задачі виконані. Тести 61/61 GREEN.
- Дія: Реалізовано 2 items з PRODUCT_ROADMAP:
  - **ВИС-11** — `RoundResult.to_dict()` тепер включає `state_snapshots` (стан агентів після раунду). Корисно для аналітики та дебагу.
  - **ВИС-14** — Кешування файлів: `_bio_cache`, `_soul_cache`, `_roster_profiles` будуються 1 раз перед ігровим циклом (game_engine.py). Усунено ~130+ зайвих disk reads для 5-раундової гри з 13 агентами. Всі 4 per-round читання BIO.md/roster.json замінені на cache lookups.
- Тести: 61/61 GREEN
- Наступний пріоритет: ВИС-5 (question_contexts в decision pipeline) або ВИС-8 (dead code cleanup в dialog_engine). Після — КРИТ-8 (COMM→ACTION ordering в Time Wars — висока складність).

## [2026-04-15 11:45 UTC] Щогодинна перевірка
- Стан: Всі T1-T5 / SEC / ROB / F1 / ВИС-11 / ВИС-14 задачі виконані. Тести 61/61 GREEN на старті.
- Дія: **ВИС-8 DONE** — Прибрано мертвий код з `simulation/dialog_engine.py`:
  - Видалено `_DIALOG_SYSTEM`, `_DM_SYSTEM` (константи промптів лише для legacy функцій)
  - Видалено `_build_context()` (helper лише для legacy)
  - Видалено `generate_public_message()` (legacy, нічим не викликалась)
  - Видалено `generate_round_dialog()` (legacy one-message-per-agent, нічим не викликалась)
  - Файл: 1176 → 1053 рядків (-123 рядки мертвого коду)
  - Stepped dialog (`generate_round_dialog_stepped`, `select_speaker`) залишено — вони покриті smoke тестами (smoke_a/smoke_c)
  - Помітка: `# EXPERIMENTAL` додана до stepped блоку
  - Також виявлено: ВИС-5 (question_contexts) вже виконано раніше — файл `schemas/question_contexts.json` вже підключений до `pipeline/question_engine.py`
- Тести: 61/61 GREEN (після cleanup)
- Наступний пріоритет: КРИТ-8 (COMM→ACTION ordering в Time Wars — висока складність) або ВИС-4 (soul_template.json оновити до 8 розділів) або ВИС-7 (заповнити profile в roster.json для 14 агентів)

## [2026-04-15 12:10 UTC] Щогодинна перевірка
- Стан: Всі попередні задачі виконані. ВИС-4 і ВИС-7 вже були закриті раніше (soul_template.json вже має 8 секцій, всі 17 агентів мають profiles в roster.json).
- Дія: **КРИТ-3 DONE** — Призначення ролей всім 17 агентам + централізація ROLE_CORE_OVERLAYS:
  - Всі 17 агентів отримали поле `role` в CORE.json: snake×3 (Алєг,Марта,Чорна Кішка), gambler×4 (Хесус,Тайлер,Артурчик,Дімончик), banker×4 (Вова,Павло,Катерина,Сергій), peacekeeper×6 (Вождь,Роман,Ліля,Микита,Наталка,Новий)
  - ROLE_CORE_OVERLAYS перенесено з `game_modes/time_wars/agent_context.py` в `simulation/constants.py` (єдине джерело правди)
  - `pipeline/decision_engine.py::CoreParams.from_dict()` тепер автоматично застосовує role overlay при завантаженні CORE — Island Mode тепер теж диференціює агентів за роллю
  - `game_modes/time_wars/agent_context.py` тепер імпортує з `simulation/constants.py` замість власного визначення
  - Ефект: Алєг (snake): coop 40→15, dec 98→100, risk 70→85; Вова (banker): coop 70→90, dec 10→0
- Тести: 61/61 GREEN
- Наступний пріоритет: КРИТ-8 (COMM→ACTION ordering в Time Wars — висока складність). М1 CONNECT milestone майже завершений.
