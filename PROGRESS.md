# PROGRESS LOG — 4 AGENTS

> Автоматично ведеться після кожного етапу роботи.

---

## S2.5 — Технічний борг (2026-03-19)

### Що зроблено

| ID | Задача | Файл | Статус |
|----|--------|------|--------|
| SEC-1 | JWT secret — генерується рандомний при відсутності env var | `db/auth.py` | ✅ |
| SEC-2 | Rate limit — додано `threading.Lock()` | `server/main.py` | ✅ |
| SEC-3 | Session TTL — expire 4 год + cleanup при доступі | `server/main.py` | ✅ |
| SEC-4 | CORS — тепер конфігурується через `CORS_ORIGINS` env var | `server/main.py` | ✅ |
| ROB-3 | MEMORY.json — атомарний запис (tmp → os.replace) | `pipeline/memory.py` | ✅ |
| TEST | Тест `roll_bonus` оновлено під v6 баланс (2→1) | `tests/test_time_wars.py` | ✅ |

### ROB-1/ROB-2 — вже були реалізовані

| ID | Де | Деталі |
|----|-----|--------|
| ROB-1 | `pipeline/seed_generator.py:215-259` | `call_openrouter` вже має 3 спроби + exponential backoff (2/4/8с) |
| ROB-2 | `simulation/dialog_engine.py:174` | `call_openrouter(..., timeout=45)` вже передається |

### Результати тестів

```
test_pipeline.py   → 22 PASS | 0 FAIL | 5 SKIP (online API)
test_time_wars.py  → 21 PASS | 0 FAIL
```

---

## 2026-03-20 — Sprint 2: Core mechanic fix + COMM + SEC/ROB

### T1.1 + T1.3 - Role-based CORE overlays OK
File: game_modes/time_wars/agent_context.py
ROLE_CORE_OVERLAYS: gambler coop-30/deception+35/risk+30, snake coop-25/deception+30, banker coop+20, peacekeeper coop+25
Test result: Gambler steal rate 60% (was 0%). Banker coop rate 60%.

### T1.2 - COMM to decisions OK
Files: agent_context.py + decision_engine.py
reasoning_hint now includes public + DM messages (was DM only). Delta +-20 (was +-8).

### T2.2 - Support mechanic OK
File: serve_time_wars.py
Supportive COMM keywords -> trust boost (DM: +0.06, public: +0.03)

### T2.3 - game_over player_stats OK
File: game_modes/time_wars/loop.py
game_over event now includes player_stats: role, steals, coops, end_bonus

### ROB-1 + ROB-2 - LLM retry + timeout OK
File: serve_time_wars.py
3 retries with backoff 1s/2s, 90s timeout per attempt. Graceful skip on failure.

### SEC-1 - _require_user fix OK
Fixed __wrapped__ bug in server/main.py

### SEC-2 - Rate limit on LLM endpoints OK
/generate-seed, /generate-question: 30 req/60s. /compile-soul: 10 req/60s.

Tests: 18 passed (test_tw_integration.py)

---

## What is next

| ID | Задача | Потребує |
|----|--------|----------|
| T5 | Storyteller prompt pass | Твоє рішення: тон, атмосфера, лор |
| T4 | Frontend UI align | Твоє рішення: яка reference |
| T6 | 4-player environment rules | Твоє рішення: механіки |
| T7 | Архітектура 4 окремих агентів | Архітектурне рішення |
| GP-1 | Людський гравець у Time Wars | Дизайн + реалізація |
| BAL-1 | Peacekeeper тюнінг 14.8% → 16.7% | Можна автономно |
