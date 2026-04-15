"""
question_engine.py

Manages the 7-round initialization question flow:
- Dynamically generates a question per context using the seed text
- Applies CORE deltas from chosen answer slots
- Optionally extracts trait tags from free-text answers
- Finalizes and writes CORE.json after all contexts are processed
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from pipeline.seed_generator import call_openrouter  # ВИС-2: єдина реалізація

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnswerSlot:
    label: str
    delta_key: str


@dataclass
class QuestionContext:
    context_id: str
    label: str
    scenario_hint: str
    answer_slots: list[AnswerSlot]


@dataclass
class GeneratedQuestion:
    context_id: str
    question_text: str
    options: list[dict[str, str]]  # [{label, delta_key}]


@dataclass
class CoreValues:
    cooperation_bias: int = 50
    deception_tendency: int = 50
    strategic_horizon: int = 50
    risk_appetite: int = 50

    def apply_delta(self, delta: dict[str, int]) -> None:
        for key, value in delta.items():
            current = getattr(self, key, 50)
            setattr(self, key, max(0, min(100, current + value)))

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class SessionState:
    """Mutable session state passed through the question flow."""
    seed_text: str
    meta_params: dict[str, Any]
    core: CoreValues = field(default_factory=CoreValues)
    answers: list[dict[str, Any]] = field(default_factory=list)
    trait_log: list[str] = field(default_factory=list)
    current_context_index: int = 0
    # Raw brief — human-readable answers accumulated for two-phase SOUL generation
    brief: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_text": self.seed_text,
            "meta_params": self.meta_params,
            "core": self.core.to_dict(),
            "answers": self.answers,
            "trait_log": self.trait_log,
            "current_context_index": self.current_context_index,
            "brief": self.brief,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        core_data = data.get("core", {})
        core = CoreValues(**core_data)
        return cls(
            seed_text=data["seed_text"],
            meta_params=data["meta_params"],
            core=core,
            answers=data.get("answers", []),
            trait_log=data.get("trait_log", []),
            current_context_index=data.get("current_context_index", 0),
            brief=data.get("brief", []),
        )


# ---------------------------------------------------------------------------
# Schema loaders
# ---------------------------------------------------------------------------

def load_contexts() -> list[QuestionContext]:
    path = SCHEMAS_DIR / "question_contexts.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    result = []
    for item in raw:
        slots = [AnswerSlot(**s) for s in item["answer_slots"]]
        result.append(QuestionContext(
            context_id=item["context_id"],
            label=item["label"],
            scenario_hint=item["scenario_hint"],
            answer_slots=slots,
        ))
    return result


def load_delta_table() -> dict[str, dict[str, int]]:
    path = SCHEMAS_DIR / "core_defaults.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["delta_table"]


def load_core_base() -> dict[str, int]:
    path = SCHEMAS_DIR / "core_defaults.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["base"]


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

QUESTION_SYSTEM_PROMPT = """You generate a single scenario-based question for a personality initialization flow.

The question must:
- Be written in second person ("You…")
- Describe a concrete, slightly tense situation
- Feel grounded and real — not abstract
- Match the personality hints from the seed text
- Have a clear moment of choice implied
- Be 2-4 sentences max

Return ONLY valid JSON in this exact format:
{
  "question": "<the question text>"
}

No extra keys. No explanation. No markdown."""


def generate_question(
    context: QuestionContext,
    session: SessionState,
    model: str = "openai/gpt-4o-mini",
) -> GeneratedQuestion:
    """Generate a dynamic question for the given context, informed by the seed."""
    prev_summary = ""
    if session.answers:
        prev_summary = "Previous answers (brief):\n" + "\n".join(
            f"- {a['context_id']}: {a['choice_label']}" for a in session.answers[-3:]
        )

    user_prompt = f"""Context theme: {context.label}
Scenario hint: {context.scenario_hint}

Personality seed (how this person tends to be):
{session.seed_text}

{prev_summary}

Write a question for this moment. Keep it tight and situational."""

    raw = call_openrouter(
        system_prompt=QUESTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.75,
        max_tokens=200,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(raw)
        question_text = parsed["question"]
    except (json.JSONDecodeError, KeyError):
        question_text = context.scenario_hint

    return GeneratedQuestion(
        context_id=context.context_id,
        question_text=question_text,
        options=[
            {"label": slot.label, "delta_key": slot.delta_key}
            for slot in context.answer_slots
        ],
    )


# ---------------------------------------------------------------------------
# Trait extraction from free text
# ---------------------------------------------------------------------------

TRAIT_EXTRACT_SYSTEM = """You extract personality trait tags from a short free-text answer.

Return ONLY valid JSON:
{
  "traits": ["trait_1", "trait_2"]
}

Rules:
- Maximum 2 trait tags.
- Each tag is 1-3 words, lowercase, descriptive (e.g. "avoids confrontation", "long-term thinker").
- Tags describe observable behavior patterns, not character labels.
- If no clear trait, return empty list."""


def extract_traits(
    free_text: str,
    meta_params: dict[str, Any],
    model: str = "openai/gpt-4o-mini",
) -> list[str]:
    """Extract 0-2 trait tags from a free-text answer."""
    if not free_text or len(free_text.strip()) < 10:
        return []

    user_prompt = f"""Free-text answer: "{free_text}"

Agent temperament hint: {meta_params.get('temperament', 'unknown')}

Extract trait tags."""

    try:
        raw = call_openrouter(
            system_prompt=TRAIT_EXTRACT_SYSTEM,
            user_prompt=user_prompt,
            model=model,
            temperature=0.3,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
        traits = parsed.get("traits", [])
        return [t for t in traits if isinstance(t, str)][:2]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Delta application
# ---------------------------------------------------------------------------

def apply_delta(
    delta_key: str,
    core: CoreValues,
    delta_table: dict[str, dict[str, int]],
) -> CoreValues:
    """Apply a delta from the table to the core values. Returns updated core."""
    delta = delta_table.get(delta_key, {})
    core.apply_delta(delta)
    return core


# ---------------------------------------------------------------------------
# CORE.json finalization
# ---------------------------------------------------------------------------

def finalize_core(
    session: SessionState,
    output_path: Path,
    agent_id: str,
) -> dict[str, Any]:
    """Write the final CORE.json file and return its content."""
    output_path.mkdir(parents=True, exist_ok=True)
    core_file = output_path / "CORE.json"

    core_data = {
        "version": "1.0.0",
        **session.core.to_dict(),
        "point_buy": {
            "budget": 100,
            "spent": 0,
            "refund": 0,
            "notes": f"Generated via initialization pipeline for agent {agent_id}"
        },
        "meta": {
            "agent_id": agent_id,
            "drive": session.meta_params.get("drive"),
            "temperament": session.meta_params.get("temperament"),
            "blind_spot": session.meta_params.get("blind_spot"),
            "stress_response": session.meta_params.get("stress_response"),
            "social_style": session.meta_params.get("social_style"),
            "intensity": session.meta_params.get("intensity"),
        },
        "trait_log": session.trait_log,
    }

    with open(core_file, "w", encoding="utf-8") as f:
        json.dump(core_data, f, indent=2, ensure_ascii=False)

    return core_data


# ---------------------------------------------------------------------------
# Public API (stateless step functions for the server)
# ---------------------------------------------------------------------------

def get_context_count() -> int:
    return len(load_contexts())


def get_context_at(index: int) -> Optional[QuestionContext]:
    contexts = load_contexts()
    if index >= len(contexts):
        return None
    return contexts[index]


def process_answer(
    session: SessionState,
    delta_key: str,
    choice_label: str,
    free_text: Optional[str],
    context_id: str,
) -> SessionState:
    """Apply answer to session state. Returns mutated session."""
    delta_table = load_delta_table()

    apply_delta(delta_key, session.core, delta_table)

    answer_record: dict[str, Any] = {
        "context_id": context_id,
        "delta_key": delta_key,
        "choice_label": choice_label,
    }

    # Accumulate raw brief entry for two-phase SOUL generation
    brief_entry = choice_label
    if free_text:
        brief_entry = free_text  # prefer free text for richer brief
        traits = extract_traits(free_text, session.meta_params)
        session.trait_log.extend(traits)
        answer_record["free_text"] = free_text
        answer_record["extracted_traits"] = traits
    session.brief.append(brief_entry)

    session.answers.append(answer_record)
    session.current_context_index += 1
    return session


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    session = SessionState(
        seed_text="You notice things. Not dramatically — just quietly, consistently. You remember who speaks first and who waits.",
        meta_params={"drive": "clarity", "temperament": "measured", "blind_spot": "chaos", "stress_response": "narrow_focus", "social_style": "quiet", "intensity": 3},
    )

    contexts = load_contexts()
    delta_table = load_delta_table()

    for i, ctx in enumerate(contexts[:2]):
        print(f"\n=== CONTEXT: {ctx.label} ===")
        q = generate_question(ctx, session)
        print(f"Q: {q.question_text}")
        for j, opt in enumerate(q.options):
            print(f"  {j+1}. {opt['label']}")

        chosen = q.options[0]
        session = process_answer(
            session,
            delta_key=chosen["delta_key"],
            choice_label=chosen["label"],
            free_text=None,
            context_id=ctx.context_id,
        )
        print(f"CORE after: {session.core.to_dict()}")

    print("\n=== FINAL CORE ===")
    print(json.dumps(session.core.to_dict(), indent=2))
