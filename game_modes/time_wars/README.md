# TIME WARS

Режим гри: час як ресурс, дії ADD/Steal/Cooperate, ролі зі скілами. Модель даних і подій вирівняна з [TIMER](https://github.com/SerhiiDubei/TIMER) для подальшого підключення UI або Supabase.

## Запуск

З кореня репозиторію:

```bash
python run_time_wars.py
python run_time_wars.py --duration 120 --agents agent_synth_g,agent_synth_c,agent_synth_h
python run_time_wars.py --duration 60 --ticks-per-action 10 --seed 42
```

- `--duration` — тривалість гри в тиках (секундах симуляції).
- `--agents` — список agent_id через кому; за замовчуванням з `agents/roster.json`.
- `--ticks-per-action` — фаза дій (cooperate/steal/code) кожні N тіків.
- `--seed` — seed для відтворюваності.
- `--log-dir` — каталог для логів (за замовчуванням `logs/`).

## Логи

Після гри у каталозі `logs/` з’являється файл `time_wars_<session_id>_<timestamp>.jsonl` — по одному JSON-рядку на подію. Поля подій: `event_type`, `actor_id`, `target_id`, `time_delta_seconds`, `tick`, `timestamp`, та додаткові за типом події.

## Ролі та скіли

Опис у `roles.json`: Змій, Миротворець, Банкір, Авантюрист. Тригери скілів: `BEFORE_STEAL_ROLL`, `ON_STEAL_FAIL`, `ON_STEAL_SUCCESS`, `ON_CODE_USE`, `ON_GAME_END`, `BLOCK`.

## Сумісність з TIMER

Див. [TIMER_COMPAT.md](TIMER_COMPAT.md) — маппінг `event_type` та payload на схему TIMER (rooms, players, events, codes) для імпорту в Supabase або відтворення в UI.
