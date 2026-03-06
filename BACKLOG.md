# 4_agents Backlog

## 1. Vision & Pillars

- **Vision**: 4 агенти-особистості проходять ритуал ініціалізації, отримують SOUL-профілі та зустрічаються в спільному середовищі для напружених, атмосферних рішень.
- **Pillars**:
- Глибокий **сторітеллінг** і лор.
- Відчутний **ритуал ініціалізації** (12 питань + SOUL).
- **4-гравцева взаємодія** з чіткими правилами.
- Технічно **стабільна, передбачувана система**.

_EN: This file acts as our lightweight ClickUp / single source of truth for planning._

---

## 2. Departments

- **Tech** – бекенд, фронтенд, архітектура коду.
- **Game Design** – лор, промпти, правила, механіки.
- **UX/UI** – екрани, анімації, флоу, візуал.
- **Infra/DevOps** – деплой, моніторинг, середовища.

---

## 3. Global Backlog

### 3.1 TODO / In‑Progress

| ID  | Title                                                   | Dept         | Type      | Priority | Status      | Sprint | Owner | Notes                                                   | Tags                                   |
|-----|---------------------------------------------------------|-------------|-----------|----------|-------------|--------|-------|---------------------------------------------------------|----------------------------------------|
| T4  | Align frontend UI with reference screens from repo      | UX/UI       | game      | P1       | todo        | S2     |       | рефлект-екрани, анімації, стейт-переходи                | #ux #frontend #flow                    |
| T5  | Storyteller prompt pass: seed + 12 questions + SOUL     | Game Design | game      | P0       | todo        | S2     |       | тон, атмосфера, повторювані мотиви                      | #game-design #prompt #lore             |
| T6  | Design 4-player environment rules & phases              | Game Design | game      | P1       | todo        | S3     |       | лоббі, раунди, кооперація/зрада                         | #game-design #multiplayer              |
| T7  | Architecture for 4 separate agents / tokens             | Tech        | tech/game | P2       | todo        | S3     |       | різні моделі/персони/ключі                              | #tech #agents #architecture            |
| T10 | Meta-layer: storing & browsing best SOUL profiles       | Game Design | game      | P3       | todo        | S4     |       | “паспорт” персонажа, історії                            | #meta #profiles #agents                |

### 3.2 Done (Global)

| ID  | Title                                                   | Dept         | Type      | Priority | Status      | Sprint | Owner | Notes                                                   | Tags                                   |
|-----|---------------------------------------------------------|-------------|-----------|----------|-------------|--------|-------|---------------------------------------------------------|----------------------------------------|
| T1  | Stabilize OpenRouter usage & error handling             | Tech        | tech      | P0       | done        | S1     |       | 401, таймаути, чіткі повідомлення на фронті             | #tech #backend #openrouter #errors     |
| T2  | Ensure seed → questions → SOUL use the same session     | Tech        | tech      | P0       | done        | S1     |       | session_id від /generate-game до компіляції             | #tech #pipeline #session               |
| T3  | Basic logging & minimal test suite for pipeline         | Tech        | tech      | P1       | done        | S1     |       | unit + 1–2 інтеграційних тести                          | #tech #logging #tests                  |
| T8  | Observability in prod (logs, basic monitoring)          | Infra/DevOps| tech      | P2       | done        | S2     |       | Railway, логи, healthchecks                             | #infra #logging #monitoring #railway   |
| T9  | UX flow for “session lost / restart ritual”             | UX/UI       | game      | P2       | done        | S2     |       | якщо сесія пропала під час compile                      | #ux #errors #recovery                  |

_Legend:_  
- **Priority**: `P0` (must now), `P1` (very important), `P2` (soon), `P3` (later/experiments).  
- **Status**: `todo` / `in-progress` / `done` / `blocked`.

---

## 4. Current Sprint

**S1 completed.** (T1, T2, T3 — done.)  
_Next focus: S2 — UI + Storyteller (T4, T5)._

| ID  | Title                                               | Priority | Status | Notes |
|-----|-----------------------------------------------------|----------|--------|-------|
| T4  | Align frontend UI with reference screens from repo  | P1       | todo   | рефлект-екрани, анімації |
| T5  | Storyteller prompt pass: seed + 12 questions + SOUL | P0       | todo   | тон, атмосфера, лор |

---

## 5. Done (Highlights)

| ID  | Title                                | When    | Notes |
|-----|--------------------------------------|---------|-------|
| D1  | Railway deploy with working frontend | 2026-Q1 | Початковий прод деплой |
| D2  | JSON parsing hardening for questions | 2026-Q1 | Фікс кривого JSON з LLM |
| S1  | T1+T2+T3 (OpenRouter, compile-from-session, tests, logging) | 2026-Q1 | Технічна стабільність |
| D3  | T8+T9 Observability + session-lost UX | 2026-Q1 | Логи в проді, UX при втраті сесії |

