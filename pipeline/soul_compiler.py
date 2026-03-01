"""
soul_compiler.py

Compiles the final SOUL.md file from the full session context:
  seed_text + meta_params + answers + trait_log + final CORE values + soul_template sections

Each section is generated individually to guarantee quality and respect per-section instructions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

import httpx

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SoulSection:
    section: str
    instruction: str
    tov_example: str
    max_lines: int


@dataclass
class CompileInput:
    agent_id: str
    seed_text: str
    meta_params: dict[str, Any]
    answers: list[dict[str, Any]]
    trait_log: list[str]
    core: dict[str, int]


# ---------------------------------------------------------------------------
# Schema loader
# ---------------------------------------------------------------------------

def load_soul_template() -> list[SoulSection]:
    path = SCHEMAS_DIR / "soul_template.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [SoulSection(**item) for item in raw]


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    model: str = "openai/gpt-4o-mini",
    temperature: float = 0.75,
    max_tokens: int = 400,
) -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    raw_key = os.environ.get("OPENROUTER_API_KEY") or ""
    api_key = raw_key.replace("\ufeff", "").strip().strip("\r\n\t ")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "IslandAgentInit",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Section compiler
# ---------------------------------------------------------------------------

SECTION_SYSTEM_PROMPT = """You write one section of a SOUL.md file for an AI agent.

SOUL.md is a personality definition file written in second person ("You…").
It describes behavior, instincts, and patterns — never labels, never moralizing.

CRITICAL RULES:
- Write in second person.
- Only observable behaviors — no trait labels ("You are strategic" is forbidden).
- No philosophical abstractions.
- No game, island, or scenario references.
- No heroic or tragic framing.
- No clichés (wolves, storms, fire, shadows, etc.).
- Keep emotional language understated.
- Match the tone-of-voice example closely — same register, same restraint.
- Respect the max_lines limit strictly."""


def build_section_context(
    compile_input: CompileInput,
    answers_summary: str,
) -> str:
    core = compile_input.core
    traits = compile_input.trait_log
    mp = compile_input.meta_params

    return f"""SEED TEXT (the base personality paragraph):
{compile_input.seed_text}

META PARAMETERS (internal, do not mention directly):
- drive: {mp.get('drive')}
- temperament: {mp.get('temperament')}
- blind_spot: {mp.get('blind_spot')}
- stress_response: {mp.get('stress_response')}
- social_style: {mp.get('social_style')}
- intensity: {mp.get('intensity')}

CORE VALUES (0-100, do not mention numbers directly — translate to behavior):
- cooperation_bias: {core.get('cooperation_bias')} (50=neutral, >50=more cooperative)
- deception_tendency: {core.get('deception_tendency')} (50=neutral, >50=more deceptive)
- strategic_horizon: {core.get('strategic_horizon')} (50=neutral, >50=longer-term thinker)
- risk_appetite: {core.get('risk_appetite')} (50=neutral, >50=more risk-tolerant)

BEHAVIORAL SIGNALS FROM INITIALIZATION ANSWERS:
{answers_summary}

EXTRACTED TRAIT TAGS:
{', '.join(traits) if traits else 'none'}"""


def build_answers_summary(answers: list[dict[str, Any]]) -> str:
    if not answers:
        return "No answers recorded."
    lines = []
    for a in answers:
        line = f"- [{a['context_id']}] chose: \"{a['choice_label']}\""
        if a.get("free_text"):
            line += f" | wrote: \"{a['free_text'][:80]}\""
        if a.get("extracted_traits"):
            line += f" | traits: {', '.join(a['extracted_traits'])}"
        lines.append(line)
    return "\n".join(lines)


def compile_section(
    section: SoulSection,
    compile_input: CompileInput,
    answers_summary: str,
    model: str = "openai/gpt-4o-mini",
) -> str:
    """Generate content for a single SOUL.md section."""
    context = build_section_context(compile_input, answers_summary)

    user_prompt = f"""{context}

---

NOW WRITE THE SECTION: ## {section.section}

INSTRUCTION:
{section.instruction}

TONE-OF-VOICE EXAMPLE (match this register — do not copy literally):
"{section.tov_example}"

MAX LINES: {section.max_lines}

Write only the section content. No section header. No markdown formatting. No explanation."""

    return call_openrouter(
        system_prompt=SECTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.75,
        max_tokens=350,
    )


# ---------------------------------------------------------------------------
# SOUL.md assembler
# ---------------------------------------------------------------------------

SOUL_HEADER_TEMPLATE = """# SOUL.md — Agent {agent_id}
# Generated by initialization pipeline
# Version: 1.0.0
# Temperament: {temperament} | Drive: {drive} | Intensity: {intensity}

"""


def assemble_soul_md(
    sections: list[tuple[str, str]],
    compile_input: CompileInput,
) -> str:
    """Build the full SOUL.md text from section name + content pairs."""
    mp = compile_input.meta_params
    header = SOUL_HEADER_TEMPLATE.format(
        agent_id=compile_input.agent_id,
        temperament=mp.get("temperament", "unknown"),
        drive=mp.get("drive", "unknown"),
        intensity=mp.get("intensity", 3),
    )

    body_parts = []
    for section_name, content in sections:
        body_parts.append(f"## {section_name}\n\n{content}")

    return header + "\n\n".join(body_parts) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_soul(
    compile_input: CompileInput,
    output_dir: Path,
    model: str = "openai/gpt-4o-mini",
) -> str:
    """
    Compile all SOUL.md sections and write the file.
    Returns the full SOUL.md text.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    template = load_soul_template()
    answers_summary = build_answers_summary(compile_input.answers)

    sections: list[tuple[str, str]] = []
    for section in template:
        content = compile_section(
            section=section,
            compile_input=compile_input,
            answers_summary=answers_summary,
            model=model,
        )
        sections.append((section.section, content))

    soul_md = assemble_soul_md(sections, compile_input)

    output_file = output_dir / "SOUL.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(soul_md)

    return soul_md


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_input = CompileInput(
        agent_id="agent_test_001",
        seed_text=(
            "You notice things. Not dramatically — just quietly, consistently. "
            "You remember who speaks first and who waits. "
            "You don't rush to answer. You let the silence stretch; it usually tells you more than the words do. "
            "A clean decision satisfies you. Sloppy reasoning bothers you more than it should. "
            "And if someone changes their story halfway through, you won't call it out immediately — you'll just file it away."
        ),
        meta_params={
            "drive": "clarity",
            "temperament": "measured",
            "blind_spot": "chaos",
            "stress_response": "narrow_focus",
            "social_style": "quiet",
            "intensity": 3,
        },
        answers=[
            {"context_id": "resource", "delta_key": "share_selectively", "choice_label": "Share, but keep more for yourself quietly"},
            {"context_id": "trust", "delta_key": "wait_and_observe", "choice_label": "Listen but reveal nothing"},
            {"context_id": "conflict", "delta_key": "passive_retaliation", "choice_label": "Say nothing now — but adjust your behavior"},
        ],
        trait_log=["long-term thinker", "avoids confrontation"],
        core={
            "cooperation_bias": 45,
            "deception_tendency": 55,
            "strategic_horizon": 68,
            "risk_appetite": 40,
        },
    )

    output = Path(__file__).parent.parent / "agents" / "agent_test_001"
    soul_text = compile_soul(test_input, output)

    print("=== SOUL.md ===")
    print(soul_text)
