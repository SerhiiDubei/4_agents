"""
storytelling_guard.py

Quality control for Grok-generated questions.

Two-pass approach:
  Pass 1 — Python checklist (fast, deterministic)
  Pass 2 — LLM rewrite only for questions that fail Pass 1

Integrated into /generate-game after JSON parsing.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import List, Optional

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Ukrainian names that should appear in questions
UKRAINIAN_NAMES = {
    "антон", "давид", "зоя", "марта", "олег", "катя", "ліна",
    "рустам", "влад", "соня", "дмитро", "оля", "іван", "настя",
    "максим", "тарас", "юля", "богдан", "надя", "роман",
}

# Forbidden patterns — generic references instead of names
GENERIC_PATTERNS = [
    r"\bлюдина\b",
    r"\bнезнайомець\b",
    r"\bнезнайома\b",
    r"\bохоронець\b(?!\s+\w)",   # охоронець without a name following
    r"\bхтось\b",
    r"\bхтосьь\b",
    r"\bвибір\b",                  # word "choice" — forbidden per spec
    r"\bнебезпечн\w+\b.*\bяк ти відреагуєш",  # generic "dangerous thing, how do you react"
]

# Forbidden escape phrases in answer text
ESCAPE_PHRASES = [
    r"пошкодуєш",
    r"можливо",
    r"наслідки",
    r"безпечн",
]


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

def check_question(q: dict) -> list[str]:
    """
    Run the checklist on a single question dict.
    Returns list of failure reasons (empty = pass).
    """
    failures = []
    text = q.get("text", "").lower()
    answers = q.get("answers", [])

    # 1. Must contain at least one Ukrainian name
    has_name = any(name in text for name in UKRAINIAN_NAMES)
    if not has_name:
        failures.append("no_ukrainian_name")

    # 2. Forbidden generic patterns in question text
    for pattern in GENERIC_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            failures.append(f"forbidden_pattern:{pattern[:20]}")
            break

    # 3. Answer count must be 2–4
    if not (2 <= len(answers) <= 4):
        failures.append(f"bad_answer_count:{len(answers)}")

    # 4. Each answer must have effects with at least one non-zero value
    for ans in answers:
        effects = ans.get("effects", {})
        if all(v == 0 for v in effects.values()):
            failures.append(f"zero_effects_on:{ans.get('id', '?')}")

    # 5. No escape phrases in answer text
    for ans in answers:
        ans_text = ans.get("text", "").lower()
        for phrase in ESCAPE_PHRASES:
            if re.search(phrase, ans_text, re.IGNORECASE):
                failures.append(f"escape_phrase_in_answer:{ans.get('id', '?')}")
                break

    # 6. No answer text longer than 25 words (answers should be actions, not explanations)
    for ans in answers:
        word_count = len(ans.get("text", "").split())
        if word_count > 25:
            failures.append(f"answer_too_long:{ans.get('id', '?')}:{word_count}w")

    return failures


def check_set(questions: list[dict]) -> dict:
    """
    Check the full set of 12 questions.
    Returns: {index: [failures]} for questions that failed.
    """
    results = {}

    # Per-question checks
    for i, q in enumerate(questions):
        failures = check_question(q)
        if failures:
            results[i] = failures

    # Set-level checks
    allow_custom_count = sum(1 for q in questions if q.get("allowCustom", False))
    if allow_custom_count < 3:
        results["set"] = results.get("set", [])
        results["set"].append(f"too_few_allow_custom:{allow_custom_count}")

    answer_counts = [len(q.get("answers", [])) for q in questions]
    if len(set(answer_counts)) < 2:
        results["set"] = results.get("set", [])
        results["set"].append("all_same_answer_count")

    return results


# ---------------------------------------------------------------------------
# LLM rewrite for failing questions
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = """You are a quality editor for psychological narrative questions.
A question failed quality checks. Rewrite it to fix the issues while keeping the same scene premise and effects.

Rules:
- Include a Ukrainian name (Антон, Давид, Зоя, Марта, Олег, Катя, Ліна, Рустам, Влад, Соня)
- 2–4 answers, each a single action sentence
- No word "вибір" in the text
- No generic references ("людина", "незнайомець") without a name
- Keep all effects exactly as they are
- Return ONLY the fixed question as a single JSON object
"""


def _rewrite_question(q: dict, failures: list[str], seed_text: str, model: str) -> dict:
    """Call LLM to rewrite a failing question. Returns fixed question dict."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from pipeline.seed_generator import call_openrouter
        import json

        user_prompt = (
            f"Fix this question. Failures: {', '.join(failures)}\n\n"
            f"Original question:\n{json.dumps(q, ensure_ascii=False, indent=2)}\n\n"
            f"Personality seed context (use subtly):\n{seed_text[:300]}\n\n"
            "Return ONLY the fixed JSON object."
        )

        raw = call_openrouter(
            system_prompt=_REWRITE_SYSTEM,
            user_prompt=user_prompt,
            model=model,
            temperature=0.7,
            max_tokens=600,
            timeout=60,
        )

        # Parse JSON from response
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                if line.startswith("```") and in_block:
                    break
                if in_block:
                    inner.append(line)
            text = "\n".join(inner).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            fixed = json.loads(text[start:end + 1])
            # Preserve original id and effects structure
            fixed["id"] = q["id"]
            return fixed

    except Exception as e:
        pass  # on any error, return original

    return q


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_and_fix(
    questions: list[dict],
    seed_text: str = "",
    model: str = "x-ai/grok-3-mini",
    max_fixes: int = 4,
) -> list[dict]:
    """
    Review a list of questions and fix those that fail the checklist.

    - Pass 1: Python checklist (instant)
    - Pass 2: LLM rewrite for failing questions (max_fixes limit)

    Returns the fixed list.
    """
    failures_map = check_set(questions)

    # Only fix per-question failures (not set-level)
    question_failures = {k: v for k, v in failures_map.items() if isinstance(k, int)}

    if not question_failures:
        return questions  # all pass, no LLM call needed

    fixed_questions = list(questions)
    fixed_count = 0

    for idx, failures in sorted(question_failures.items()):
        if fixed_count >= max_fixes:
            break
        fixed_questions[idx] = _rewrite_question(
            questions[idx], failures, seed_text, model
        )
        fixed_count += 1

    return fixed_questions


def review_report(questions: list[dict]) -> str:
    """Return a human-readable report of checklist results."""
    failures_map = check_set(questions)

    if not failures_map:
        return f"All {len(questions)} questions passed. No fixes needed."

    lines = [f"Checklist report ({len(questions)} questions):"]
    for key, failures in failures_map.items():
        label = f"Q{key + 1}" if isinstance(key, int) else "SET"
        lines.append(f"  {label}: {', '.join(failures)}")

    total_fail = len([k for k in failures_map if isinstance(k, int)])
    lines.append(f"\n{total_fail}/{len(questions)} questions need fixes.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_questions = [
        {
            "id": 1,
            "text": "Незнайомець дивиться на тебе і тримає конверт. Що робиш?",
            "allowCustom": False,
            "answers": [
                {"id": "1a", "text": "Береш конверт.", "effects": {"cooperationBias": 5, "deceptionTendency": 0, "strategicHorizon": 0, "riskAppetite": 10}},
                {"id": "1b", "text": "Ігноруєш.", "effects": {"cooperationBias": 0, "deceptionTendency": 0, "strategicHorizon": 0, "riskAppetite": 0}},
            ],
        },
        {
            "id": 2,
            "text": "Антон стоїть біля стіни. Його телефон лежить на підлозі екраном вгору.",
            "allowCustom": True,
            "answers": [
                {"id": "2a", "text": "Підбираєш телефон і повертаєш.", "effects": {"cooperationBias": 15, "deceptionTendency": 0, "strategicHorizon": 5, "riskAppetite": 0}},
                {"id": "2b", "text": "Читаєш що на екрані.", "effects": {"cooperationBias": -5, "deceptionTendency": 15, "strategicHorizon": 10, "riskAppetite": 5}},
                {"id": "2c", "text": "Проходиш мимо.", "effects": {"cooperationBias": 0, "deceptionTendency": 0, "strategicHorizon": 0, "riskAppetite": 0}},
            ],
        },
    ]

    print(review_report(sample_questions))
