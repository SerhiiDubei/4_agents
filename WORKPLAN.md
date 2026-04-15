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

## [2026-04-15 13:09 UTC] Щогодинна перевірка
- Стан: Всі попередні задачі виконані. КРИТ-8 перевірено — COMM→ACTION порядок вже коректний в поточному коді (COMM line 452, ACTION line 571, last_messages передається). Фактично КРИТ-8 був вже виправлений в попередньому циклі.
- Дія: **ВИС-2 DONE** — Консолідація дублікатів call_openrouter:
  - `pipeline/seed_generator.py::call_openrouter` розширено параметром `response_format: Optional[dict]` для підтримки json_object mode
  - `pipeline/question_engine.py`: видалено локальну копію call_openrouter (~47 рядків), додано `from pipeline.seed_generator import call_openrouter`
  - `pipeline/soul_compiler.py`: видалено локальну копію call_openrouter (~43 рядки) + дублюючий function-local import, додано module-level import з seed_generator
  - Ефект: question_engine і soul_compiler тепер мають безкоштовно 3-retry backoff. Тестові моки `pipeline.seed_generator.call_openrouter` тепер покривають ВСІ LLM-виклики pipeline.
  - Видалено невикористані `import httpx`, `import os` з обох файлів
- Тести: 61/61 GREEN
- Наступний пріоритет: ВИС-6 (meta_params.json підключити до SOUL генерації) або КРИТ-6 (reveal_requests ініціалізація в Island) або М2 TIME WARS FIX items.

## [2026-04-15 16:07 UTC] Щогодинна перевірка
- Стан: M0 та M1 повністю завершені. Всі КРИТ-1..7 і ВИС-1..14 виконані (підтверджено ревізією коду). ВИС-6 фактично вже реалізована — meta_params.json живе в schemas/ і підключена до seed_generator.py + soul_compiler.py. М2 TIME WARS FIX — почато.
- Дія: **СЕР-12 DONE** — CODE фаза тепер personality-driven:
  - `pick_best_code()` в `loop.py` розширено особистісними вагами
  - `steal` та `minus_all` типи коду масштабуються на `deception_tendency` (множник 0.3x..1.7x) — Snake/Gambler б'ють агресивніше
  - `give` та `plus_all_except_one` масштабуються на `cooperation_bias` — Banker/Peacekeeper діляться охочіше, при нижчому surplus порозі
  - `gamble` вже використовував `risk_appetite` — залишено без змін
  - `self` тип не диференційований — виживання не залежить від ролі
  - ARCHITECTURE.html оновлено: loop.py опис включає СЕР-12
- Тести: 61/61 GREEN
- Наступний пріоритет: СЕР-20 (підключити `_skill_applies` умови в skills.py) або СЕР-21 (ON_GAME_END bonus — перевірити порядок визначення переможця) або M3 STORYTELLING items (СЕР-5/6/7/8).

## [2026-04-15 17:09 UTC] Щогодинна перевірка
- Стан: M2 TIME WARS FIX продовжується. ВИС-9 і СЕР-21 фактично вже були виправлені раніше (підтверджено ревізією коду).
- Дія: Три задачі M2 виконано:
  - **СЕР-20 DONE** — `_skill_applies()` тепер перевіряється у ВСІХ trigger handlers skills.py: `apply_before_steal_roll`, `apply_on_steal_fail`, `apply_on_steal_success`, `apply_on_code_use` (раніше — тільки в `apply_on_game_end`). Це correctness + future-proofing для нових умовних скілів.
  - **СЕР-11 DONE** — Виноc game balance параметрів у `game_modes/time_wars/tw_config.json`: base_sec=1000, drain_base=3, drain_double_every=50, ticks_per_action=10, storm_after_ticks=300. serve_time_wars.py тепер читає ці значення через `_load_tw_config()` (graceful fallback на дефолти якщо файл відсутній). trust_boost_dm/public також перенесені в config.
  - **СЕР-10 DONE** — Детальна документація мана механіки додана в `constants.py`: джерела (+5 coop, +8 steal success, -3 steal fail, +1/round), витрати (ціни по класах C/B/A/S), початкова мана, рівновага.
- СЕР-21 VERIFIED: `apply_game_end_bonuses` викликається ДО визначення переможця у всіх трьох шляхах завершення гри (elimination, hard cap, duration cap). Порядок коректний — бонуси впливають на результат при hard cap. Задача закрита.
- Тести: 61/61 GREEN
- Наступний пріоритет: M3 STORYTELLING items — СЕР-5 (genre/mood в промпти), СЕР-6 (Character Arc), СЕР-7 (Dynamic Event Escalation), СЕР-8 (Consequence Carryover). Або залишок M2: перевірити стан СЕР-9 (storytell в Time Wars).

## [2026-04-15 18:11 UTC] Щогодинна перевірка
- Стан: M0/M1/M2 повністю завершені. M3 STORYTELLING — розпочато і завершено за один сеанс.
- Дія: **M3 STORYTELLING — 5 задач DONE:**
  - **СЕР-5 DONE** — `story_params.py::to_style_str()` — новий метод що повертає жанр/настрій/ставки для системного промпту LLM. Підключено в `situation.py` і `round_narrative.py` — тепер LLM знає жанр (thriller/drama/survival) і настрій (paranoid/tense/hopeful) кожної гри.
  - **СЕР-6 DONE** — `storytell/character_arc.py` — новий файл. `CharacterArcTracker` накопичує зради/кооперації по кожному агенту і генерує мітки дуг (зрадник/союзник/жертва/прагматик). Підключено в `game_engine.py` (ініціалізація до циклу, update після кожного раунду) і `round_narrative.py` (arc_tracker → LLM промпт).
  - **СЕР-7 DONE** — `round_events.py` повністю переписано. Три фази ескалації: ранні раунди (0–39%, знайомство), середні (40–74%, напруга), фінальні (75%+, кульмінація). Нові шаблони EVENTS_EARLY/MID/CLIMAX з різними моральними вагами і розподілом.
  - **СЕР-8 DONE** — `consequences.py::build_betrayal_carryover()` — новий helper що збирає зради з усіх попередніх раундів. `generate_consequences()` тепер приймає `betrayal_carryover` і додає контекст повторних зрад в текст наслідків. Підключено в `game_engine.py`.
  - **СЕР-9 DONE** — `serve_time_wars.py`: виправлено root bug — `generate_story_params` → `generate_story` (функція-злодій що тихо падала щоразу). Також додано `CharacterArcTracker` в TW narrative thread — arc тепер будується з усіх попередніх тіків.
  - `storytell/__init__.py` оновлено: `CharacterArcTracker`, `CharacterArc`, `build_betrayal_carryover` додані в exports.
  - `ARCHITECTURE.html` оновлено: M3 статус, всі 7 модулів з мітками.
- Тести: 61/61 GREEN
- Наступний пріоритет: M4 HUMAN PLAYER або F2 (Human player UX) або додаткові тести для storytell модуля (round_events escalation unit test).

## [2026-04-15 19:07 UTC] Щогодинна перевірка
- Стан: M0/M1/M2/M3 повністю завершені. Виявлено: M3 мала вимогу "Тести для storytell модуля" — вона не була виконана (61 тест, ціль M3 = 80+).
- Дія: **M3 TESTS DONE** — створено `tests/test_storytell.py`: 46 unit тестів без LLM-залежностей:
  - `TestCharacterArcLabel` (7 тестів) — перевірка міток дуги: зрадник/прагматик/союзник/жертва
  - `TestCharacterArcTrend` (5 тестів) — тренди: цинічний/відкривається/нейтральний
  - `TestCharacterArcTracker` (7 тестів) — підрахунок зрад/кооп, key_moments, self-interaction
  - `TestRoundEvents` (5 тестів) — ескалація ранні/середні/фінальні раунди, довжина description
  - `TestGetParticipants` (4 тести) — виключення focus_agent, ліміт учасників
  - `TestGenerateConsequences` (5 тестів) — базові наслідки, betrayal carryover
  - `TestBuildBetrayalCarryover` (5 тестів) — агрегація зрад, дедублікація, custom threshold
  - `TestStoryParams` (4 тести) — to_style_str(), to_context_str()
  - `TestRoundEventFormat` (4 тести) — підстановка {name}/{name1}/{name2}
  - Додано `suite_storytell()` в `run_all_tests.py` → 4-й suite в стандартному запуску
  - `ARCHITECTURE.html` оновлено: статус 107 тестів, M3 TESTS badge
- Тести: **107/107 GREEN** (+46 storytell, з 61 до 107)
- Наступний пріоритет: M4 FRONTEND & UX — ВИС-12 (Auth UI) або ВИС-13 (Human player TIME WARS interface)

## [2026-04-15 21:07 UTC] Щогодинна перевірка
- Стан: M0/M1/M2/M3 повністю завершені. 107/107 тестів GREEN. M4 FRONTEND & UX — розпочато.
- Дія: **ВИС-12 DONE** — Auth UI реалізовано у React frontend:
  - `frontend/src/src/hooks/useAuth.ts` — хук з повним auth lifecycle: login/register/logout, JWT зберігання у localStorage, верифікація `/auth/me` при старті (авто-очищення протухлих токенів)
  - `frontend/src/src/components/AuthModal.tsx` — модальне вікно login/register у стилі гри (CRT кути, pixel font, framer-motion анімації). Tabs: УВІЙТИ / РЕЄСТРАЦІЯ. Валідація полів + error display.
  - `frontend/src/src/pages/InitOpenPhase.tsx` — інтегровано: панель `[УВІЙТИ]` / `[username] ВИЙТИ` у верхньому правому куті. Auth modal відкривається по кліку.
  - ARCHITECTURE.html оновлено: M4 статус, новий AuthModal модуль у FRONTEND LAYER
- Тести: 107/107 GREEN (backend тести не торкались, frontend зміни — нові файли без breaking changes)
- Наступний пріоритет: ВИС-13 (Human player interface для TIME WARS — людина грає як один з агентів)

## [2026-04-15 22:08 UTC] Щогодинна перевірка
- Стан: M0/M1/M2/M3/ВИС-12 повністю завершені. 107/107 тестів GREEN на старті.
- Дія: **ВИС-13 DONE** — Human player interface для TIME WARS реалізовано в `serve_time_wars.py`:
  - **Головна сторінка** (`/`): додано кнопку `👤 ГРАТИ ЯК ЛЮДИНА` поруч з `▶ СТАРТ ГРИ`. При натисканні `/api/start-game` викликається з `{human_slot: true}`. Підказки під кожною кнопкою пояснюють режим (спостерігач vs гравець). Обидві кнопки блокуються при запуску щоб уникнути подвійного старту.
  - **Сторінка гри** (`/game`): 60-секундний таймер зворотного відліку у панелі дії гравця (`_startCountdown()`). Таймер червоніє і блимає при ≤10 секундах (`urgent` клас). При таймауті панель автоматично закривається з повідомленням "Час вийшов — автоматичний пас". Таймер зупиняється при виборі дії.
  - **Картки гравців**: власна картка людини виділяється синьою рамкою (клас `is-human`), бейдж `ТИ` поруч з ім'ям.
  - **XSS безпека**: кнопки цілей замінені з `innerHTML` на `document.createElement` + `textContent`.
  - ARCHITECTURE.html оновлено: ВИС-13 DONE badge + новий модуль HumanPlayer у FRONTEND LAYER.
- Тести: 107/107 GREEN
- Наступний пріоритет: M4 — Dashboard з аналітикою ігор або Agent profiles на фронтенді

## [2026-04-15 23:09 UTC] Щогодинна перевірка
- Стан: M0/M1/M2/M3/ВИС-12/ВИС-13 повністю завершені. 107/107 тестів GREEN на старті.
- Дія: **M4 Agent Profiles DONE** — профілі агентів реалізовані у React frontend:
  - `frontend/src/src/components/AgentProfilesView.tsx` — новий компонент: сітка 17 агентів з CORE-барами (cooperation/deception/strategic/risk), фільтр за роллю (all/змія/гравець/банкір/миротворець), detail-панель при кліку (розгортається поверх). ROLE_CORE_OVERLAYS автоматично застосовуються до відображення.
  - `server/main.py` — новий endpoint `/api/roster/profiles`: читає roster.json + CORE.json кожного агента + BIO.md витяг, повертає масив з {id, name, role, roleLabel, roleColor, core, profession, bio, connections}. Role overlays застосовуються server-side.
  - `pages/InitOpenPhase.tsx` — додано phase `agent-profiles` + кнопка `[ АГЕНТИ ]` (фіолетова) у головному меню.
  - ARCHITECTURE.html оновлено: нова картка AgentProfilesView у FRONTEND LAYER, статус-бейдж оновлено.
- Тести: 107/107 GREEN (TypeScript помилки — тільки pre-existing unused vars, не в новому коді)
- Наступний пріоритет: M4 — Dashboard з аналітикою ігор (win rates, betrayal rates, cooperation trends) або Real-time Island UI (SSE-based live visualization)

## [2026-04-16 00:09 UTC] Щогодинна перевірка
- Стан: M0/M1/M2/M3/ВИС-12/ВИС-13/Agent Profiles повністю завершені. 107/107 тестів GREEN.
- Дія: **M4 Analytics Dashboard DONE** — поведінкова аналітика агентів по 151+ іграх:
  - `server/main.py` — новий endpoint `/api/analytics/island`: парсить усі Island JSON логи, агрегує `pair_outcomes` (mutual_coop/exploit_i/exploit_j/mutual_defect) по кожному агенту. Обчислює: win_rate, betrayal_rate, coop_rate, games_played, games_won, betrayals_committed/received, mutual_coops/defects.
  - `frontend/src/src/components/AnalyticsDashboardView.tsx` — новий компонент: загальні метрики (ігор/зрад/кооперацій), progress bars для win/coop/betrayal rate, числові деталі, сортування по 5 колонках (win_rate/betrayal_rate/coop_rate/games_played/betrayals_committed).
  - `pages/InitOpenPhase.tsx` — додано phase `analytics` + кнопка `[ АНАЛІТИКА ]` (помаранчева) у головному меню, URL param `?view=analytics`.
  - `ARCHITECTURE.html` оновлено: нова картка AnalyticsDashboardView у FRONTEND LAYER, статус-бейдж і timestamp оновлені.
- Тести: 107/107 GREEN
- Наступний пріоритет: Real-time Island UI (SSE live React компонент замість island_launcher.html) або M5 Infrastructure (async LLM calls, Alembic, structured logging)
