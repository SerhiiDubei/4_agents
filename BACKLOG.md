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

| ID  | Title                                                   | Dept         | Type      | Priority | Status      | Sprint | Owner | Notes |
|-----|---------------------------------------------------------|-------------|-----------|----------|-------------|--------|-------|-------|
| T1  | Stabilize OpenRouter usage & error handling             | Tech        | tech      | P0       | todo        | S1     |       | 401, таймаути, чіткі повідомлення на фронті |
| T2  | Ensure seed → questions → SOUL use the same session     | Tech        | tech      | P0       | todo        | S1     |       | session_id від /generate-game до компіляції |
| T3  | Basic logging & minimal test suite for pipeline         | Tech        | tech      | P1       | todo        | S1     |       | unit + 1–2 інтеграційних тести |
| T4  | Align frontend UI with reference screens from repo      | UX/UI       | game      | P1       | todo        | S2     |       | рефлект-екрани, анімації, стейт-переходи |
| T5  | Storyteller prompt pass: seed + 12 questions + SOUL     | Game Design | game      | P0       | todo        | S2     |       | тон, атмосфера, повторювані мотиви |
| T6  | Design 4-player environment rules & phases              | Game Design | game      | P1       | todo        | S3     |       | лоббі, раунди, кооперація/зрада |
| T7  | Architecture for 4 separate agents / tokens             | Tech        | tech/game | P2       | todo        | S3     |       | різні моделі/персони/ключі |
| T8  | Observability in prod (logs, basic monitoring)          | Infra/DevOps| tech      | P2       | done        | S2     |       | Railway, логи, healthchecks |
| T9  | UX flow for “session lost / restart ritual”             | UX/UI       | game      | P2       | done        | S2     |       | якщо сесія пропала під час compile |
| T10 | Meta-layer: storing & browsing best SOUL profiles       | Game Design | game      | P3       | todo        | S4     |       | “паспорт” персонажа, історії |

_Legend:_  
- **Priority**: `P0` (must now), `P1` (very important), `P2` (soon), `P3` (later/experiments).  
- **Status**: `todo` / `in-progress` / `done` / `blocked`.

---

## 4. Current Sprint (S1)

_Focus: зробити поточну систему стабільною й передбачуваною._  
_EN: Focus on technical stability of the existing flow._

| ID  | Title                                               | Priority | Status      | Notes |
|-----|-----------------------------------------------------|----------|------------|-------|
| T1  | Stabilize OpenRouter usage & error handling         | P0       | in-progress |      |
| T2  | Ensure seed → questions → SOUL use the same session | P0       | todo       |      |
| T3  | Basic logging & minimal test suite for pipeline     | P1       | todo       |      |

---

## 5. Done (Highlights)

| ID  | Title                                | When    | Notes |
|-----|--------------------------------------|---------|-------|
| D1  | Railway deploy with working frontend | 2026-Q1 | Початковий прод деплой |
| D2  | JSON parsing hardening for questions | 2026-Q1 | Фікс кривого JSON з LLM |

