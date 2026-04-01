# PRODUCT ROADMAP: 4 Agents Social Simulation Platform

> **Дата**: 2026-04-01
> **Версія**: 1.0
> **Статус**: Аудит завершено, план дій сформовано

---

## VISION

**4 Agents** — платформа мульти-агентної соціальної симуляції, де AI-агенти з унікальними особистостями взаємодіють через ігрові механіки (Prisoner's Dilemma, Time Wars), приймають рішення на основі характеру, спілкуються природною мовою, формують довіру та пам'ять між іграми.

**Кінцева мета**: Створити екосистему, де 17+ агентів із SOUL/BIO/CORE/MEMORY демонструють правдоподібну соціальну динаміку — зраду, альянси, маніпуляцію, кооперацію — з кінематографічним наративом кожного раунду.

**Два ігрові режими**:
- **Island** (покроковий) — класична Prisoner's Dilemma з наративом, діалогом, рефлексією
- **Time Wars** (реал-тайм) — battle royale з тайм-ресурсом, ролями, кодами, магазином

---

## EXECUTIVE SUMMARY

Платформа має **солідну базу** (17 агентів, повні SOUL/BIO/CORE/MEMORY, працюючий game loop, decision engine, dialog engine), але страждає від:

1. **Розірваних зв'язків** — діалог генерується, але ігнорується при прийнятті рішень
2. **Неконсистентних порогів** — одна й та ж дія класифікується по-різному в різних підсистемах
3. **Мертвого коду** — ~30% функціоналу написано, але не підключено
4. **Відсутньої інфраструктури** — Redis/Celery = 0 рядків, всі LLM-виклики синхронні
5. **Дублювання** — 5 копій `_cooperation_val()`, 3-4 копії `call_openrouter()`

**Кількість проблем**: 8 критичних, 14 високих, 22 середніх, 12 низьких

---

## КРИТИЧНІ ПРОБЛЕМИ (БЛОКЕРИ)

### КРИТ-1: Діалог ігнорується при прийнятті рішень
- **Де**: `game_engine.py:536-587`
- **Суть**: `dialog_heard` будується (рядки 536-544), але НЕ передається в `generate_reasoning()`. Агенти приймають рішення без урахування того, що було сказано в діалозі.
- **Вплив**: Діалог чисто декоративний. Агент може сказати "я тебе підтримаю" і зрадити — не тому що маніпулює, а тому що його рішення не бачить його ж слова.
- **Фікс**: Передати `dialog_heard` в `generate_reasoning()` як параметр
- **Складність**: Низька (1 параметр)
- **Пріоритет**: P0

### КРИТ-2: Пороги класифікації дій розходяться між підсистемами
- **Де**: `payoff_matrix.py` (0.33/0.66), `dialog_engine.py` (0.15/0.45/0.75), `reveal_skill.py` (0.4/0.66)
- **Суть**: Одна дія (наприклад, 0.5) класифікується як "mixed" в payoff, "soft-cooperated" в діалозі, "cooperated" в reveal
- **Вплив**: Агенти отримують суперечливі сигнали про поведінку інших
- **Фікс**: Створити `simulation/constants.py` з єдиними порогами
- **Складність**: Середня (рефакторинг 4 файлів)
- **Пріоритет**: P0

### КРИТ-3: Ролі НЕ призначені агентам
- **Де**: `agents/*/CORE.json` — немає поля `role`
- **Суть**: `roles.json` визначає 4 ролі (snake, gambler, banker, peacekeeper) з 8 навичками, але жодному агенту роль не призначена
- **Вплив**: Блокує TIME WARS механіку ролей. `ROLE_CORE_OVERLAYS` не застосовуються в Island
- **Фікс**: Додати `role` в CORE.json або автоматичне призначення в `create_session()`
- **Складність**: Низька
- **Пріоритет**: P0

### КРИТ-4: Round Narrative мовчазно фейлить
- **Де**: `game_engine.py:716-745`
- **Суть**: `generate_round_narrative()` обгорнуте в `try/except: pass`. Якщо LLM фейлить — наратив = "", жодного логування
- **Вплив**: Логи показують шаблонні тексти замість кінематографічних описів. Storytelling — мертвий
- **Фікс**: Додати логування помилок, fallback текст
- **Складність**: Низька
- **Пріоритет**: P0

### КРИТ-5: Reveal Skill — метод не існує
- **Де**: `reveal_skill.py:249` — викликає `tracker.was_exposed()`, але метод називається `was_target()` (рядок 147)
- **Суть**: CLI тест падає; reveal фіча не тестується
- **Фікс**: Перейменувати `was_target()` на `was_exposed()`
- **Складність**: Мінімальна
- **Пріоритет**: P0

### КРИТ-6: Reveal Requests ніколи не ініціалізуються
- **Де**: `game_engine.py:235,749`
- **Суть**: Параметр `reveal_requests` існує, але завжди порожній. Reveal skill недоступний в грі
- **Вплив**: Механіка "одноразового розкриття" (1 токен на гру) — dead code
- **Фікс**: Ініціалізувати reveal_requests або додати механізм тригерення
- **Складність**: Середня
- **Пріоритет**: P0

### КРИТ-7: Situation Reflections не впливають на рішення
- **Де**: `game_engine.py:407-427`
- **Суть**: `situation_reflections` генеруються LLM, але не передаються в decision engine
- **Вплив**: Агент "думає" про ситуацію, але ці думки не впливають на його дію
- **Фікс**: Передати reflections в reasoning/decision pipeline
- **Складність**: Низька
- **Пріоритет**: P0

### КРИТ-8: COMM → ACTION в Time Wars відстає
- **Де**: `serve_time_wars.py:348-509`
- **Суть**: Дія вже обрана утилітарно ДО того, як COMM фаза завершиться. COMM timeout (90 сек) → гра без діалогу
- **Вплив**: TIME WARS комунікація не впливає на рішення
- **Фікс**: Переструктурувати послідовність: COMM → рішення → ACTION
- **Складність**: Висока
- **Пріоритет**: P0

---

## ВИСОКІ ПРОБЛЕМИ

### ВИС-1: 5 копій `_cooperation_val()` в pipeline/
- **Де**: `state_machine.py`, `memory.py`, `reasoning.py`, `reflection.py`, `talk_transition.py`
- **Суть**: Одна й та ж функція скопійована 5 разів
- **Фікс**: Винести в `pipeline/utils.py`
- **Пріоритет**: P1

### ВИС-2: 3-4 копії `call_openrouter()` в pipeline/
- **Де**: Кожен модуль pipeline має свою версію
- **Суть**: Різні версії з різними параметрами timeout, retry, temperature
- **Фікс**: Один `pipeline/llm_client.py`
- **Пріоритет**: P1

### ВИС-3: Support dimension — dead code
- **Де**: `payoff_matrix.py:113-129`, `interaction_dimensions.py`
- **Суть**: Support dimension визначена (weight=0.5, payoff_type="support"), але game_engine ніколи не передає multi-dim actions
- **Фікс**: Або підключити, або видалити
- **Пріоритет**: P1

### ВИС-4: soul_template.json застарілий
- **Де**: `agents/soul_template.json` — 6 розділів, реальні SOUL.md мають 8
- **Суть**: Шаблон не відповідає фактичній структурі (відсутні Voice, Body Language)
- **Фікс**: Оновити шаблон до 8 розділів
- **Пріоритет**: P1

### ВИС-5: question_contexts.json не використовується
- **Де**: `agents/question_contexts.json` — 7 контекстів x 4 варіанти
- **Суть**: Добре розроблені контексти (resource, trust, conflict, etc.) не підключені до decision_engine
- **Фікс**: Інтегрувати або позначити як planned
- **Пріоритет**: P1

### ВИС-6: meta_params.json не використовується
- **Де**: `agents/meta_params.json` — 6 словників варіаторів (drive, temperament, blind_spot, etc.)
- **Суть**: Красива система метапараметрів не пов'язана з SOUL.md
- **Фікс**: Або підключити при генерації SOUL, або видалити
- **Пріоритет**: P1

### ВИС-7: profile в roster.json порожній для 14 із 17 агентів
- **Де**: `agents/roster.json`
- **Суть**: Тільки 3 нові агенти мають заповнений profile (connections, profession, bio)
- **Фікс**: Заповнити з BIO.md або автогенерувати
- **Пріоритет**: P1

### ВИС-8: Dead code в dialog_engine.py
- **Де**: `dialog_engine.py:250,544`
- **Суть**: 2 невикористані генератори діалогу (stepped, legacy). Тільки flat mode працює
- **Фікс**: Видалити або позначити як experimental
- **Пріоритет**: P1

### ВИС-9: codes.json може не існувати
- **Де**: `game_modes/time_wars/shop.py`
- **Суть**: `load_codes()` повертає `[]` якщо файл не знайдений. SHOP фаза пропускається мовчки
- **Фікс**: Додати дефолтні коди або помилку на старті
- **Пріоритет**: P1

### ВИС-10: Redis та Celery = 0 рядків коду
- **Де**: Весь проект
- **Суть**: Архітектурна документація згадує Redis/Celery, але реалізація відсутня. Всі LLM-виклики синхронні
- **Вплив**: ~13 LLM-викликів на раунд Island × 45 сек timeout = потенційно 10+ хв на раунд
- **Фікс**: Або впровадити async queue, або видалити з документації
- **Пріоритет**: P1

### ВИС-11: state_snapshots не серіалізуються
- **Де**: `game_engine.py:796-819`
- **Суть**: state_snapshots збираються, але НЕ включаються в `GameResult.to_dict()`
- **Вплив**: Дані стану агентів втрачаються в логах
- **Фікс**: Додати до серіалізації
- **Пріоритет**: P1

### ВИС-12: Auth UI відсутній
- **Де**: Frontend
- **Суть**: Auth endpoints існують в backend, але UI для логіну/реєстрації немає. USER_ID завжди "local"
- **Фікс**: Або додати auth UI, або видалити auth endpoints
- **Пріоритет**: P1

### ВИС-13: Human player інтерфейс для TIME WARS
- **Де**: `serve_time_wars.py`
- **Суть**: Логіка для людського гравця існує (60 сек timeout), але frontend UI не реалізований
- **Фікс**: Або додати UI, або прибрати `hasHuman` параметр
- **Пріоритет**: P1

### ВИС-14: Повторне читання файлів на кожен раунд
- **Де**: `game_engine.py:347,718`
- **Суть**: `roster.json` та `BIO.md` читаються з диску на КОЖЕН раунд замість кешування
- **Фікс**: Кешувати на початку гри
- **Пріоритет**: P1

---

## СЕРЕДНІ ПРОБЛЕМИ

| # | Проблема | Де | Вплив |
|---|---------|-----|-------|
| СЕР-1 | Async event loop дублюється 3+ разів | game_engine.py | Code smell |
| СЕР-2 | sys.path.insert 5+ разів | game_engine.py | Крихкий import |
| СЕР-3 | DM ротація передбачувана (i+round%n) | game_engine.py:212 | Тривіальна стратегія |
| СЕР-4 | No bounds check на action values | payoff_matrix.py | Потенційний crash |
| СЕР-5 | Genre/mood/stakes не передаються в промпти | storytell | Наративи не відповідають mood |
| СЕР-6 | Character Arc відсутній | storytell | Персонажі не розвиваються |
| СЕР-7 | Dynamic Event Escalation відсутній | storytell/round_events.py | Events статичні |
| СЕР-8 | Consequence Carryover відсутній | storytell | Зрада не впливає на events |
| СЕР-9 | Storytell не інтегрований з TIME WARS | game_modes/time_wars | Немає наративу в TW |
| СЕР-10 | Мана механіка непрозора | TIME WARS | Як купувати коди? |
| СЕР-11 | Параметри TIME WARS hardcoded | serve_time_wars.py | Немає конфігурації |
| СЕР-12 | CODE фаза не використовує decision_engine | loop.py | Утилітарна замість personality |
| СЕР-13 | Deception threshold (60) тільки в dialog | dialog_engine.py | Inconsistent |
| СЕР-14 | Temperature 0.88 hardcoded | dialog_engine.py | Неможливо тюнити |
| СЕР-15 | DM reply не отримує memory context | dialog_engine.py | Менш інформовані відповіді |
| СЕР-16 | Dimension weights не нормалізовані | interaction_dimensions.py | Sum=1.5 замість 1.0 |
| СЕР-17 | core_deception поле ніде не використовується | interaction_dimensions.py | Dead field |
| СЕР-18 | Dead code в reflection.py | pipeline | ~100 рядків unused |
| СЕР-19 | Inconsistent JSON parsing в pipeline | pipeline | Різні парсери |
| СЕР-20 | Skill conditions (_skill_applies) не використовуються | skills.py | Тільки ON_GAME_END |
| СЕР-21 | ON_GAME_END бонус після визначення переможця | loop.py | Бонус інформаційний |
| СЕР-22 | Rounding inconsistency (2, 3, 4 decimals) | Кілька файлів | Cosmetic |

---

## НИЗЬКІ ПРОБЛЕМИ

| # | Проблема | Де |
|---|---------|-----|
| НИЗ-1 | Display names vs agent IDs inconsistent | game_engine.py |
| НИЗ-2 | Visibility modes partially implemented | reveal_skill.py |
| НИЗ-3 | DEFAULT_ACTION_VALUE дублюється (0.5) | 3 файли |
| НИЗ-4 | Situation text truncation (400 chars) | dialog_engine.py |
| НИЗ-5 | Action label gaps (0.34-0.65 = "mixed") | payoff_matrix.py |
| НИЗ-6 | No per-agent model override in flat dialog | dialog_engine.py |
| НИЗ-7 | DM: тільки останній DM обробляється | dialog_engine.py |
| НИЗ-8 | Trust snapshot restoration uncertain | game_engine.py |
| НИЗ-9 | Talkativity formula hardcoded | dialog_engine.py |
| НИЗ-10 | Multi-message DMs ігноруються | dialog_engine.py |
| НИЗ-11 | talk_signals може бути порожнім | dialog_engine.py |
| НИЗ-12 | Game seed formula hardcoded | game_engine.py |

---

## MILESTONES

### M0: STABILIZE (1-2 дні)
**Мета**: Зробити Island Mode стабільним та функціональним

- [ ] КРИТ-1: Передати dialog_heard в reasoning
- [ ] КРИТ-2: Централізувати пороги дій в `simulation/constants.py`
- [ ] КРИТ-4: Логувати помилки в `generate_round_narrative()`
- [ ] КРИТ-5: Фікс `was_target()` → `was_exposed()`
- [ ] КРИТ-7: Передати situation_reflections в decision pipeline
- [ ] ВИС-1: Один `_cooperation_val()` в `pipeline/utils.py`
- [ ] ВИС-2: Один `call_openrouter()` в `pipeline/llm_client.py`

**Критерій готовності**: Island гра де діалог впливає на рішення, наративи генеруються, reveal працює

### M1: CONNECT (3-5 днів)
**Мета**: Підключити всі розроблені системи

- [ ] КРИТ-3: Призначити ролі агентам
- [ ] КРИТ-6: Ініціалізувати reveal_requests
- [ ] ВИС-3: Підключити support dimension або видалити
- [ ] ВИС-4: Оновити soul_template.json до 8 розділів
- [ ] ВИС-5: Інтегрувати question_contexts в decision pipeline
- [ ] ВИС-6: Підключити meta_params до SOUL генерації
- [ ] ВИС-7: Заповнити profile в roster.json
- [ ] ВИС-8: Видалити dead code з dialog_engine
- [ ] ВИС-11: Серіалізувати state_snapshots
- [ ] ВИС-14: Кешувати roster.json та BIO.md

**Критерій готовності**: Всі розроблені системи працюють разом, немає dead code

### M2: TIME WARS FIX (3-5 днів)
**Мета**: Зробити Time Wars повноцінним

- [ ] КРИТ-8: Переструктурувати COMM → ACTION послідовність
- [ ] ВИС-9: Забезпечити codes.json
- [ ] СЕР-10: Документувати мана механіку
- [ ] СЕР-11: Конфігурація параметрів TIME WARS (config.json)
- [ ] СЕР-12: CODE фаза через decision_engine
- [ ] СЕР-20: Підключити skill conditions
- [ ] СЕР-21: ON_GAME_END бонус до визначення переможця

**Критерій готовності**: TIME WARS з працюючими COMM, SHOP, CODE, ACTION фазами

### M3: STORYTELLING (3-5 днів)
**Мета**: Кінематографічний наратив кожного раунду

- [ ] СЕР-5: Genre/mood/stakes в промпти
- [ ] СЕР-6: Character Arc між раундами
- [ ] СЕР-7: Dynamic Event Escalation (напруга зростає)
- [ ] СЕР-8: Consequence Carryover (зрада → наступні events)
- [ ] СЕР-9: Storytell для TIME WARS
- [ ] Тести для storytell модуля

**Критерій готовності**: HTML лог гри читається як кінематографічна історія

### M4: FRONTEND & UX (5-7 днів)
**Мета**: Повноцінний UI

- [ ] ВИС-12: Auth UI (login/register)
- [ ] ВИС-13: Human player interface для TIME WARS
- [ ] Dashboard з аналітикою ігор
- [ ] Real-time візуалізація Island гри
- [ ] Agent profiles на фронтенді

**Критерій готовності**: Користувач може запустити гру, спостерігати, грати як людина

### M5: INFRASTRUCTURE (5-7 днів)
**Мета**: Production-ready архітектура

- [ ] ВИС-10: Async LLM calls (або Redis/Celery, або asyncio queue)
- [ ] Database міграції (Alembic)
- [ ] Structured logging (не print)
- [ ] Error monitoring
- [ ] Config management (env-based)
- [ ] API rate limiting для OpenRouter

**Критерій готовності**: Система витримує 10+ паралельних ігор

### M6: POLISH (ongoing)
- [ ] Всі СЕР та НИЗ проблеми
- [ ] Unit тести для кожного модуля
- [ ] Integration тести для game loop
- [ ] Performance optimization
- [ ] Documentation

---

## АРХІТЕКТУРА: ПОТОЧНИЙ СТАН vs ЦІЛЬОВИЙ

### Поточний стан
```
Frontend (React/Vite:5173)
  ├── Island UI (базовий)
  └── Time Wars UI (окремий сервер :5174)

Backend (FastAPI:8000)
  ├── simulation/game_engine.py (Island loop, синхронний)
  ├── simulation/dialog_engine.py (LLM dialog)
  ├── simulation/payoff_matrix.py
  ├── simulation/reveal_skill.py
  ├── pipeline/ (soul creation, reasoning, decision)
  ├── storytell/ (narrative generation)
  └── game_modes/time_wars/ (окремий FastAPI)

Data Layer
  ├── SQLite (sessions, actions)
  ├── agents/ (SOUL.md, CORE.json, BIO.md, STATES.md, MEMORY.json)
  └── logs/ (JSONL + HTML per game)

External
  └── OpenRouter API (Gemini, GPT-4o-mini, Grok)
```

### Цільовий стан
```
Frontend (React/Vite:5173)
  ├── Auth (login/register)
  ├── Island UI (real-time, spectator mode)
  ├── Time Wars UI (integrated, human play)
  ├── Agent Profiles (SOUL/BIO/CORE viewer)
  └── Analytics Dashboard

Backend (FastAPI:8000) ← ОДИН сервер
  ├── simulation/ (Island + Time Wars, unified)
  ├── pipeline/ (deduplicated, shared LLM client)
  ├── storytell/ (connected, character arcs)
  └── config/ (centralized constants, game params)

Data Layer
  ├── PostgreSQL (production) або SQLite (dev)
  ├── agents/ (з ролями, заповненими profiles)
  └── logs/ (structured, with state_snapshots)

Queue (async LLM)
  └── asyncio TaskQueue або Celery+Redis

External
  └── OpenRouter API (з rate limiting, retry, fallback models)
```

---

## DEPENDENCY MAP

```
M0 (Stabilize) ← блокер для всього
  ↓
M1 (Connect) ← залежить від M0
  ↓
M2 (Time Wars) ← може паралельно з M3
M3 (Storytelling) ← може паралельно з M2
  ↓
M4 (Frontend) ← залежить від M1
  ↓
M5 (Infrastructure) ← може паралельно з M4
  ↓
M6 (Polish) ← після всього
```

---

## МЕТРИКИ ЯКОСТІ

| Метрика | Поточне | Ціль M0 | Ціль M3 | Ціль M6 |
|---------|---------|---------|---------|---------|
| Тести | 32 pass | 50+ | 80+ | 120+ |
| Dead code | ~30% | <15% | <5% | <2% |
| Дублювання | 5x cooperation_val | 1x | 1x | 1x |
| Inconsistent thresholds | 3 набори | 1 | 1 | 1 |
| Dialog → Decision | Розірвано | Підключено | Повноцінно | З feedback loop |
| Narrative якість | Шаблонна | Генерується | Кінематографічна | З character arc |
| Storytell тести | 0 | 5+ | 15+ | 25+ |
| Час раунду Island | ~10 хв | ~5 хв | ~3 хв | <2 хв |

---

## РИЗИКИ

| Ризик | Ймовірність | Вплив | Митigation |
|-------|-------------|-------|------------|
| OpenRouter downtime | Середня | Високий | Fallback models, retry logic |
| LLM cost explosion | Висока | Середній | Token budgets, caching, smaller models |
| Context window overflow | Середня | Високий | Truncation strategy, summarization |
| Async migration складність | Висока | Середній | Поступове впровадження, asyncio перед Celery |
| Game balance (roles) | Середня | Середній | A/B testing, tunable parameters |

---

## РЕЗЮМЕ

**Що добре**: 17 агентів з повними особистостями, працюючий decision engine, два ігрові режими, HTML логи, cross-game пам'ять, LLM-діалог.

**Що потрібно терміново**: Підключити діалог до рішень (КРИТ-1), уніфікувати пороги (КРИТ-2), призначити ролі (КРИТ-3), полагодити наратив (КРИТ-4).

**Очікуваний час до якісного запуску**: M0-M3 = 10-17 днів активної роботи. M4-M5 = додатково 10-14 днів.

---

*Документ згенеровано на основі глибокого аудиту 6 підсистем: Game Engine, Pipeline, Storytell, Agents & Schemas, Time Wars, Frontend & Server.*
