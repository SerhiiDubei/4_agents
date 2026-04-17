"""
llm_client.py — спільний LLM-клієнт для pipeline.

Раніше кожен модуль pipeline мав власну обгортку навколо call_openrouter:
  reasoning.py   → _call_structured() без retry
  reflection.py  → _call() з 2 спробами, temperature=0.7

Тепер один клієнт з retry, логуванням, і підтримкою JSON schema.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger("llm_client")


def call_llm(
    system: str,
    user: str,
    model: str,
    temperature: float = 0.75,
    max_tokens: int = 300,
    timeout: int = 45,
    json_schema: Optional[dict] = None,
    retries: int = 2,
    retry_delay: float = 2.0,
    label: str = "",
) -> str:
    """
    Unified LLM call with retry logic.

    Args:
        system: system prompt
        user: user prompt
        model: OpenRouter model ID
        temperature: sampling temperature
        max_tokens: max output tokens
        timeout: request timeout in seconds
        json_schema: optional JSON schema for structured output
        retries: number of attempts (default 2)
        retry_delay: seconds between retries
        label: optional label for error logging

    Returns:
        Raw string response from LLM.

    Raises:
        Exception on all retries exhausted.
    """
    from pipeline.seed_generator import call_openrouter

    last_err = None
    for attempt in range(retries):
        try:
            return call_openrouter(
                system_prompt=system,
                user_prompt=user,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                json_schema=json_schema,
            )
        except Exception as e:
            last_err = e
            tag = f"llm_client{f'/{label}' if label else ''}"
            logger.warning("%s attempt %d/%d failed: %s", tag, attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(retry_delay)

    raise last_err
