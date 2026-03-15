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
# Two-phase initialization — compile SOUL directly from a brief
# ---------------------------------------------------------------------------

def compile_from_brief(
    agent_id: str,
    brief: list[str],
    seed_text: str,
    meta_params: dict,
    output_dir: Optional[Path] = None,
    model: str = "x-ai/grok-3-mini",
) -> dict:
    """
    Two-phase initialization: compile SOUL.md and CORE.json from a raw brief.

    Instead of converting each answer to CORE deltas immediately, all raw answers
    are passed to the LLM at once so it can form a coherent personality.

    Returns {"soul_md": str, "core": dict}
    """
    from pipeline.seed_generator import call_openrouter

    brief_text = "\n".join(f"- {entry}" for entry in brief if entry.strip())

    meta_text = (
        f"Drive: {meta_params.get('drive', '?')}, "
        f"Temperament: {meta_params.get('temperament', '?')}, "
        f"Blind spot: {meta_params.get('blind_spot', '?')}, "
        f"Stress: {meta_params.get('stress_response', '?')}, "
        f"Social style: {meta_params.get('social_style', '?')}"
    )

    system_prompt = """You are generating a personality file for a social simulation agent.
You receive a seed description and a brief of raw questionnaire answers.
Your job: synthesize them into a coherent person — not a game avatar, a real human with history.

Return a JSON object with exactly two fields:
{
  "soul_md": "...",
  "core": {
    "cooperation_bias": <0-100>,
    "deception_tendency": <0-100>,
    "strategic_horizon": <0-100>,
    "risk_appetite": <0-100>
  }
}

SOUL.md rules:
- Written in second person ("You...")
- 200-400 words
- Specific, grounded, no clichés — concrete observations about behavior
- Include: how they think under pressure, what they want, what they hide, how they relate to others
- No game/simulation references

CORE rules:
- cooperation_bias: willingness to help others (0=never, 100=always)
- deception_tendency: tendency to mislead or hide true intentions (0=honest, 100=deceptive)
- strategic_horizon: long-term (100) vs short-term (0) thinking
- risk_appetite: comfort with uncertainty and bold choices (0=cautious, 100=reckless)

Return ONLY valid JSON. No explanation."""

    user_prompt = f"""Seed description:
{seed_text}

Meta profile: {meta_text}

Questionnaire brief:
{brief_text}

Generate personality JSON:"""

    raw = call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=0.75,
        max_tokens=800,
        timeout=120,
    )

    # Parse JSON response
    import re
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"compile_from_brief: no JSON in response: {raw[:200]}")

    result = json.loads(json_match.group())
    soul_md = result.get("soul_md", "")
    core = result.get("core", {})

    # Ensure all CORE keys exist with defaults
    core.setdefault("cooperation_bias", 50)
    core.setdefault("deception_tendency", 50)
    core.setdefault("strategic_horizon", 50)
    core.setdefault("risk_appetite", 50)
    # Add model field
    core["model"] = "x-ai/grok-3-mini"

    # Write files if output_dir provided
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

        soul_path = output_dir / "SOUL.md"
        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(soul_md)

        core_data = {
            "version": "1.0.0",
            **{k: v for k, v in core.items() if k != "model"},
            "model": core["model"],
            "point_buy": {
                "budget": 100,
                "spent": 0,
                "refund": 0,
                "notes": f"Generated via brief-based initialization for agent {agent_id}",
            },
            "meta": {
                "agent_id": agent_id,
                **meta_params,
            },
            "trait_log": [],
        }
        core_path = output_dir / "CORE.json"
        with open(core_path, "w", encoding="utf-8") as f:
            json.dump(core_data, f, indent=2, ensure_ascii=False)

    return {"soul_md": soul_md, "core": core}


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
