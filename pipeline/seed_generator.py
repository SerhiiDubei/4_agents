"""
seed_generator.py

Randomly selects meta-parameters and calls OpenRouter to generate
a personality seed paragraph for an agent.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Optional

import httpx

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MetaParams:
    drive: str
    temperament: str
    blind_spot: str
    stress_response: str
    social_style: str
    intensity: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeedResult:
    seed_text: str
    meta_params: MetaParams

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_text": self.seed_text,
            "meta_params": self.meta_params.to_dict(),
        }


# ---------------------------------------------------------------------------
# Meta-param selection
# ---------------------------------------------------------------------------

def load_meta_params_schema() -> dict[str, list]:
    path = SCHEMAS_DIR / "meta_params.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def random_meta_params() -> MetaParams:
    schema = load_meta_params_schema()
    return MetaParams(
        drive=random.choice(schema["drive"]),
        temperament=random.choice(schema["temperament"]),
        blind_spot=random.choice(schema["blind_spot"]),
        stress_response=random.choice(schema["stress_response"]),
        social_style=random.choice(schema["social_style"]),
        intensity=random.choice(schema["intensity"]),
    )


# ---------------------------------------------------------------------------
# LLM prompt assembly
# ---------------------------------------------------------------------------

SEED_SYSTEM_PROMPT = """You are a personality seed generator.

Your task: write a single paragraph (80-140 words) that describes a person's temperament.

INTERNAL STRUCTURE (hidden — do not mention these, just use them):
Use this hidden scaffold to build the paragraph naturally:
1. Behavioral anchor (a habit or micro-pattern)
2. Social dynamic marker (how they relate to others)
3. Emotional reaction cue (something concrete that triggers a response)
4. Decision instinct signal (how they tend to choose)
5. Blind spot implication (a subtle flaw, shown through behavior)
6. Stress behavior cue (what shifts when pressure increases)
7. Grounded closing note (calm, not dramatic)

DO RULES:
- Write in second person ("You…").
- Use observable behaviors: pauses, tone shifts, small reactions.
- Show thinking style through action, not declaration.
- Include one mild imperfection shown through behavior.
- Imply motivation — never state it directly.
- Keep tone controlled and contemporary.
- Allow light dryness or subtle irony.
- Mix short and longer sentences.
- Keep emotional language understated.
- End calmly, not dramatically.

DON'T RULES:
- No philosophical abstractions.
- No fantasy tone or mythic metaphors (wolves, storms, fire, shadows).
- No moralizing or life advice.
- No over-explaining psychological reasons.
- No direct trait labels ("You are strategic", "You are cold").
- No heroic or tragic framing.
- No clichés.
- No mention of a game, island, or any specific scenario.
- No melodrama.
- No repeated phrasing patterns.

TONE CALIBRATION by intensity:
- 1-2: softer, observational, low friction
- 3: subtle edge, controlled sharpness
- 4-5: tighter sentences, stronger reaction cues

BLIND SPOT RULE:
Show the blind spot through behavior — never name it.
BAD: "You underestimate chaotic people."
GOOD: "You dismiss the loud ones too quickly."

STRESS RESPONSE RULE:
Show stress through behavioral shift — never explain it.
BAD: "Under pressure you withdraw."
GOOD: "When things tighten, you speak less."

OUTPUT CONSTRAINTS:
- 80-140 words exactly.
- Single paragraph.
- No bullet points, no formatting symbols, no quotation marks unless natural.
- No rhetorical questions.
- No poetic line breaks.
"""


def build_seed_user_prompt(params: MetaParams) -> str:
    return f"""Generate a personality seed paragraph for a person with these hidden parameters:

drive: {params.drive}
temperament: {params.temperament}
blind_spot: {params.blind_spot}
stress_response: {params.stress_response}
social_style: {params.social_style}
intensity: {params.intensity}

Return only the paragraph. Nothing else."""


# ---------------------------------------------------------------------------
# OpenRouter client
# ---------------------------------------------------------------------------

def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    model: str = "openai/gpt-4o-mini",
    temperature: float = 0.85,
    max_tokens: int = 300,
    timeout: int = 120,
    json_schema: Optional[dict] = None,
    api_key: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> str:
    """
    Call OpenRouter API and return the text content.

    json_schema: optional JSON Schema dict for structured output (strict schema mode).
      When provided, response_format is set to json_schema mode and the
      raw JSON string is returned (caller must parse it).
    response_format: optional raw response_format dict (e.g. {"type": "json_object"}).
      Used when caller needs simple JSON mode without a full schema.
      Ignored if json_schema is set.
    """
    if api_key:
        api_key = api_key.replace("\ufeff", "").strip().strip("\r\n\t ")
    if not api_key:
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

    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_response",
                "strict": True,
                "schema": json_schema,
            },
        }
    elif response_format is not None:
        payload["response_format"] = response_format

    max_attempts = 3
    backoff_seconds = [2, 4, 8]
    last_exc = None
    for attempt in range(max_attempts):
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if response.status_code == 401:
                body = response.text
                try:
                    err_json = response.json()
                    if "error" in err_json and isinstance(err_json["error"], dict):
                        body = err_json["error"].get("message", body)
                except Exception:
                    pass
                raise EnvironmentError(
                    f"OpenRouter 401 Unauthorized. Key invalid or disabled. OpenRouter says: {body}"
                )
            if response.status_code in (429, 502, 503):
                last_exc = RuntimeError(
                    f"OpenRouter {response.status_code} (attempt {attempt + 1}/{max_attempts})"
                )
                if attempt < max_attempts - 1:
                    delay = backoff_seconds[attempt]
                    print(f"  [OpenRouter] {last_exc}; retry in {delay}s", file=sys.stderr, flush=True)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.TimeoutException as e:
            last_exc = e
            if attempt < max_attempts - 1:
                delay = backoff_seconds[attempt]
                print(f"  [OpenRouter] timeout (attempt {attempt + 1}/{max_attempts}); retry in {delay}s", file=sys.stderr, flush=True)
                time.sleep(delay)
            else:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("OpenRouter call failed after retries")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_seed(
    meta_params: Optional[MetaParams] = None,
    model: str = "openai/gpt-4o-mini",
) -> SeedResult:
    """Generate a personality seed. If no meta_params provided, randomizes them."""
    if meta_params is None:
        meta_params = random_meta_params()

    user_prompt = build_seed_user_prompt(meta_params)
    seed_text = call_openrouter(
        system_prompt=SEED_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.85,
        max_tokens=300,
    )

    return SeedResult(seed_text=seed_text, meta_params=meta_params)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    result = generate_seed()
    print("=== META PARAMS ===")
    print(json.dumps(result.meta_params.to_dict(), indent=2))
    print("\n=== SEED TEXT ===")
    print(result.seed_text)
