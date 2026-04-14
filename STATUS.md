# 4 AGENTS — ПОВНИЙ СТАТУС ПРОЕКТУ
> Складено: 2026-04-13 | Охоплює всі документи за 2 тижні

---

## 🟢 ЗРОБЛЕНО — 18 оновлень (v0.1 → v0.18)

### 🔧 КОР МЕХАНІКА (Island + Time Wars спільне)

| ID | Версія | Дата | Що зроблено | Файл |
|----|--------|------|-------------|------|
| КРИТ-1 / T1.1 | v0.1 | 2026-04-10 | `strategic_score` переписано — тепер диференціює за personality. Gambler=63% defect, Banker=44% coop | `pipeline/decision_engine.py` |
| T1.2 | v0.2 | 2026-04-10 | COMM → рішення: `last_messages` передається з loop.py в decision phase | `serve_time_wars.py:571` |
| T1.3 | v0.3 | 2026-04-10 | `ROLE_CORE_OVERLAYS` застосовуються до CoreParams з clamping [0,100] | `game_modes/time_wars/agent_context.py` |
| КРИТ-2 | v0.4 | 2026-04-10 | Action thresholds 0.33/0.66 уніфіковані в `simulation/constants.py` — єдине джерело правди | `simulation/constants.py` |
| КРИТ-5/6 | v0.5 | 2026-04-10 | `was_target` alias + auto-reveal heuristic (trust<0.40 → агент сам шпигує в раундах 1/3..N-1) | `simulation/game_engine.py` |

### 🛡 БЕЗПЕКА + НАДІЙНІСТЬ

| ID | Версія | Дата | Що зроблено | Файл |
|----|--------|------|-------------|------|
| ROB-1,2,3 | v0.6 | 2026-04-11 | Atomic MEMORY.json write (tmp→rename) + LLM retry+backoff + 90s dialog timeout | `pipeline/memory.py`, `llm_client.py`, `serve_time_wars.py` |
| SEC-1,2 | v0.7 | 2026-04-11 | JWT expiry валідується + rate limiting 30 req/хв на всіх LLM endpoints | `db/auth.py`, `server/main.py` |
| SEC-3 | v0.13 | 2026-04-13 | TW Session TTL 4h — `_tw_cleanup_sessions()` прибирає старі сесії з RAM | `serve_time_wars.py` |

### 📊 ЗВІТИ + ЛОГУВАННЯ

| ID | Версія | Дата | Що зроблено | Файл |
|----|--------|------|-------------|------|
| T2.1 | — | авто | Skills тригеряться: `ON_STEAL_SUCCESS`, `ON_STEAL_FAIL`, `ON_GAME_END` — активно після T1.1 | `game_modes/time_wars/loop.py` |
| T2.3 | v0.8 | 2026-04-12 | Фінальна таблиця TW: Роль + Стілів + Кооп% + Бонус з `player_stats` | `game_modes/time_wars/log_to_html.py` |
| CRIT-3 | v0.11 | 2026-04-13 | SOUL.md ін'єктується в TW `build_context()` (line 97-100) і Island `soul_md` | `game_modes/time_wars/agent_context.py` |
| CRIT-4 | v0.12 | 2026-04-13 | `round_narrative` → non-blocking daemon thread після кожного action phase | `serve_time_wars.py` |

### 🖥 FRONTEND + ВІЗУАЛІЗАЦІЯ

| ID | Версія | Дата | Що зроблено | Файл |
|----|--------|------|-------------|------|
| SF | v0.9 | 2026-04-12 | Social Fabric live в SSE accordion — 9 секцій, кольори alliance/betray/deceive | `island_launcher.html` |
| FastAPI | v0.10 | 2026-04-12 | Starlette 1.0.0 → FastAPI 0.135.3 — 61/61 тестів GREEN | `requirements.txt` |
| F1.1 | v0.14 | 2026-04-13 | TW live UI: скіли агента як `skill-tag` бейджі під роллю | `serve_time_wars.py` |
| F1.2 | v0.15 | 2026-04-13 | Island WE-tab: comm_messages (діалог) у реальному часі — блок "💬 Діалог" | `island_launcher.html`, `run_simulation_live.py` |
| F1.3 | v0.16 | 2026-04-13 | Island WE-tab: `intents` (cooperation_level per target) — прогрес-бар + колір | `island_launcher.html` |
| log | v0.17 | 2026-04-13 | `round_narrative` рендерується в TW HTML звіті (фіолетовий italic) | `game_modes/time_wars/log_to_html.py` |

### 🌿 ISLAND СПЕЦИФІЧНО

| ID | Версія | Дата | Що зроблено | Файл |
|----|--------|------|-------------|------|
| T2.2 | v0.18 | 2026-04-13 | **Support механіка**: `support_bias` auto-derived з personality. support≥0.66 → +trust effect. "💚 Підтримка" блок в WE-tab | `pipeline/decision_engine.py`, `simulation/game_engine.py`, `island_launcher.html` |
| BAL-1 | v0.19 | 2026-04-13 | **Personality anchoring**: `generate_reasoning()` отримує `core_params` → явні числа (coop/dec/risk) в LLM промпті. Батч 20 ігор: dec≥70→betray 69%, dec≤30→betray 43% (+27% різниця ✓). Вова: 42%→22% зрад | `pipeline/reasoning.py`, `simulation/game_engine.py` |
| F2 | v0.21 | 2026-04-14 | **Human player в Island**: `--human-agent` CLI param, HUMAN_TURN stdout protocol, stdin pipe (bidirectional IPC), `/api/island/human_action` endpoint, human turn overlay з кнопками Кооперація/Нейтрально/Зрада, sim_id tracking | `server/island_routes.py`, `run_simulation_live.py`, `simulation/game_engine.py`, `island_launcher.html` |
| T5 | v0.20 | 2026-04-13 | **Storyteller prompt pass**: WorldBible (12 питань, 1 LLM-виклик/гру) → єдиний тон, голос, метафора, agent_roles. SOUL-anchored narrative: round_narrative отримує Voice+Instinct з SOUL.md. Ситуації з WorldBible тоном. UI: блок "📖 Розповідь" у WE-tab. Нова сторінка `docs/arch_storytell.html` | `storytell/world_bible.py` (new), `round_narrative.py`, `situation.py`, `game_engine.py`, `island_launcher.html` |

---

## 🟡 НЕ ПОЧИНАЛИ — РУКИ НЕ ДІЙШЛИ

### 🎮 GAME DESIGN / МЕХАНІКИ

| ID | Пріоритет | Що потрібно | Складність |
|----|-----------|-------------|------------|
| ~~**F2**~~ | ~~P0~~ | ~~ВИКОНАНО v0.21~~ — human player overlay, HUMAN_TURN protocol, stdin IPC |
| **F3** | P1 | 4-player архітектура — баланс механік для рівно 4 агентів (зараз 13), нова payoff матриця | Висока |
| **T4** | P1 | Frontend React UI — рефлект-екрани, анімації, стейт-переходи (з BACKLOG.md S2) | Середня |
| **T5** | P0 | Storyteller prompt pass — seed + 12 питань + SOUL → єдиний тон, атмосфера, лор (з BACKLOG.md S2) | Середня |
| **T6** | P1 | 4-player environment rules & phases — лобі, раунди, кооперація/зрада між 4 людьми | Висока |

### 📈 АНАЛІТИКА + БАЛАНС

| ID | Пріоритет | Що потрібно |
|----|-----------|-------------|
| ~~**BAL-1**~~ | ~~P1~~ | ~~ВИКОНАНО v0.19~~ — personality anchoring підтверджено (+27% кореляція) |
| **BAL-2** | P2 | Agent analytics dashboard — win rate per agent/role, cooperation%, steal%, за всі ігри |
| **BAL-3** | P2 | Leaderboard persistency — зберігати результати всіх ігор в БД, не тільки в пам'яті |
| **BAL-4** | P3 | A/B параметри — фреймворк для тестування різних ваг (strategic_score, trust_delta, etc.) |

### 🏗 АРХІТЕКТУРА / ТЕХНІЧНИЙ БОРГ

| ID | Пріоритет | Що потрібно | З якого документа |
|----|-----------|-------------|-------------------|
| **T7** | P2 | Architecture for 4 separate agents/tokens — різні моделі, персони, API-ключі | BACKLOG.md |
| **T10** | P3 | Meta-layer: зберігання та перегляд кращих SOUL-профілів ("паспорт персонажа") | BACKLOG.md |
| **REF-1** | P2 | Уніфікувати `GamesSummaryResponse` interface між `GamesResultsView` і `LeaderboardView` | REFACTOR_AUDIT.md |
| **REF-2** | P3 | `deploy._free_port` — тільки Windows (netstat+taskkill). Додати Linux/macOS (fuser) | REFACTOR_AUDIT.md |
| **INF-1** | P2 | Performance monitoring — метрики LLM latency, game duration, error rate в Railway | — |
| **INF-2** | P3 | Versioned API (v1/v2) — поки всі ендпоінти без версії | — |

### 🖥 FRONTEND НЕ ЗАВЕРШЕНО

| ID | Пріоритет | Що потрібно |
|----|-----------|-------------|
| **UI-1** | P1 | Island: Notes/reflections агентів в WE-tab (є в `RoundResult.notes` але не рендерується) |
| **UI-2** | P2 | TW: Reveal mechanic live у SSE stream (є в HTML-звіті, але не в live UI) |
| **UI-3** | P2 | TW: Code cards shop UI improvements — показати які коди купив агент і що вони дають |
| **UI-4** | P3 | Multi-game statistics / leaderboard між матчами |
| **UI-5** | P3 | Game admin panel — старт/стоп/рестарт ігор без CLI |
| **UI-6** | P3 | Spectator mode / replay — перегляд записаних ігор крок за кроком |

### 📄 ДОКУМЕНТИ ПОТРЕБУЮТЬ ОНОВЛЕННЯ

| Файл | Проблема |
|------|----------|
| `BACKLOG.md` | Застарілий — S1/S2 sprint з 2026-Q1, не відображає поточний стан |
| `PROGRESS.md` | Замерз на 2026-03-20, тільки 1 запис |
| `SIMULATION_ANALYSIS.md` | Аналіз v6 (heuristic агенти) — не відображає LLM-агентів |
| `docs/PRODUCT_ROADMAP.html` | Не переглядався |
| `arch_server.html`, `arch_frontend.html`, `arch_story.html`, `arch_data.html` | Не оновлювались під час останньої ревізії (квітень 2026) |

---

## ✅ КРИТЕРІЙ УСПІХУ — ПЕРЕВІРКА

| Метрика | Очікується | Статус |
|---------|-----------|--------|
| Gambler краде ≥ 30% раундів | ≥30% | ⚠️ Виправлено в коді, але реальна LLM гра не запускалась |
| Snake краде ≥ 20% раундів | ≥20% | ⚠️ Аналогічно |
| Banker ніколи не краде | 0% | ⚠️ Аналогічно |
| player_intent згадує COMM | >0% | ✅ T1.2 виправлено |
| Різні агенти — різна кількість coop | не рівно у всіх | ✅ T1.1+T1.3 виправлено |
| Всі тести | 61/61 | ✅ GREEN |
| Island support events логуються | є | ✅ v0.18 |

---

## 🔢 ПІДСУМОК ЦИФРАМИ

```
Всього задач в плані:          ~40
✅ Зроблено:                   18  (45%)
⚠️ Зроблено в коді, не протестовано LLM:  5  (12%)
🔴 Не починали:                ~17  (43%)

Тести: 61/61 GREEN
Версії: v0.1 → v0.18
Комітів за 2 тижні: 36
```

---

## 🗺 ПРІОРИТЕТИ НАСТУПНОГО КРОКУ

```
ЗАРАЗ (P0):
  BAL-1 → запустити run_batch_250.py → перевірити реальний баланс з LLM
  F2    → Human player в Island

СКОРО (P1):
  F3    → 4-player архітектура (потребує game design рішень від тебе)
  T5    → Storyteller prompt pass (атмосфера + SOUL → єдиний тон)
  UI-1  → Island notes/reflections в WE-tab

ПОТІМ (P2-P3):
  BAL-2 → Analytics dashboard
  T7    → 4 окремі агенти з різними API ключами
  REF-1 → Уніфікувати GamesSummaryResponse
```
