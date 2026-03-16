# TIME WARS — сумісність з TIMER

Цей документ описує маппінг подій і полів TIME WARS на модель даних [TIMER](https://github.com/SerhiiDubei/TIMER) (rooms, players, events, codes), щоб події можна було імпортувати в Supabase або відтворювати в TIMER UI.

## Формула часу (спільна)

```
remaining = base_seconds - elapsed + SUM(events.time_delta_seconds WHERE target = player)
```

- **base_seconds** — стартовий час гравця.
- **elapsed** — реальний час з початку гри.
- Події з `time_delta_seconds` змінюють залишок для відповідного гравця.

## Маппінг event_type та payload

| TIME WARS event_type | TIMER / примітка | Поля події |
|----------------------|------------------|-------------|
| `self_add` | TIMER: effect_type `self_add`, payload `{ "seconds": N }` | actor_id, target_id (=actor), time_delta_seconds |
| `self_subtract` | TIMER: effect_type `self_subtract` | actor_id, time_delta_seconds (від’ємний) |
| `steal` | TIMER: effect_type `steal`, payload `{ "from_player_id": id, "seconds": N }` | actor_id, target_id (жертва), time_delta_seconds (для актора +N, окрема подія для цілі -M або одна подія з двома таргетами) |
| `team_add` | TIMER: effect_type `team_add` | time_delta_seconds, scope |
| `cooperate` | TIME WARS extension | actor_id, target_id (партнер), time_delta_seconds (+30 кожному; два запису або один з payload) |
| `storm` | TIME WARS extension | event_type storm, time_delta_seconds = -30, застосовується до всіх |
| `crisis` | TIME WARS extension | event_type crisis, умова (напр. time_remaining < 300), time_delta_seconds = -60 |
| `skill_trigger` | TIME WARS extension | skill_id, actor_id, time_delta_seconds (якщо скіл змінює час) |
| `elimination` | Відповідає вибуттю в TIMER | target_id (вибувший), status = eliminated |
| `game_start` / `game_over` | Мета-події | session_id, timestamp |

## Таблиці TIMER

- **rooms** — одна кімната = одна TIME WARS сесія (session_id).
- **players** — кожен гравець: player_id (= agent_id), room_id, base_seconds; можна додати role_id, inventory (JSON).
- **events** — append-only: room_id, event_type, actor_id, target_id, time_delta_seconds, payload (JSON), timestamp.
- **codes** — як у TIMER; в TIME WARS коди можуть бути в інвентарі гравця (inventory) і використовуватися через подію `code_use` / `self_add`.

## Експорт для Supabase

При експорті логів у формат TIMER для кожної події створювати запис з:

- `session_id` (room_id)
- `event_type`
- `actor_id`, `target_id` (де застосовно)
- `time_delta_seconds`
- `payload` (JSON з додатковими полями: skill_id, outcome, code_id тощо)
- `timestamp` або `tick`
