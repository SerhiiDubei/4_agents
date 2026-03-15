# storytell — генеративний сторітейл

Окремий модуль від game engine. Мета: зробити гру «живою» через художній контекст.

## Ідея

- **Генеративна тема**: кожен раунд унікальний
- **Загальний сторітейл** (з random seed): рік, місце, дійові особи, проблема, завязка
- **Драматична архітектура**: параметри в вигляді структурованих полів
- **Події раунду**: герої переживають ряд подій; рішення (зрада/підтримка) мапляться на 1..N учасників

## Структура

```
storytell/
├── __init__.py
├── story_params.py    # StoryParams, RoundEvent
├── story_generator.py # generate_story(seed) → StoryParams
├── round_events.py    # get_round_event(), get_participants_for_event()
└── README.md
```

## Використання (поки без інтеграції)

```python
from storytell import generate_story, get_round_event, StoryParams, RoundEvent

# Генерація сторітейлу
params = generate_story(seed=42)
print(params.to_context_str())
# "Рік: 1943. Місце: острів у Тихому океані. Завязка: корабель потонув..."

# Подія для раунду
event = get_round_event(
    round_number=1,
    total_rounds=10,
    story_params=params,
    agent_ids=["agent_a", "agent_b", "agent_c", "agent_d"],
    agent_names={"agent_a": "Кир", "agent_b": "Надя", ...},
)
# event.template: "Ти береш {name} з собою на човен — і тільки її в цей раунд."
# event.involved_count: 1
```

## Маппінг на гру

- `involved_count=1`: герой вирішує щодо **одного** учасника (напр. «береш Кіру на човен»)
- `involved_count=2`: щодо двох (напр. «ділишся з X і Y»)
- `involved_count=N`: щодо всіх

Це дозволяє перетворити абстрактні «cooperate/betray» на читабельні сценарії.

## Реагрегабельність

- Модуль **не залежить** від `simulation/` і `pipeline/`
- Інтеграція: передати `StoryParams` у dialog/reasoning як контекст; використовувати `RoundEvent` для формулювання промптів
- Розширення параметрів: додати поля в `StoryParams`, пресети в `story_generator.py`
