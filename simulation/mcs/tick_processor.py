"""
MCS Tick Processor — двіжок автономного життя NPC.

Рівень 1 (cheap): математика, без LLM, відбувається завжди
Рівень 2 (expensive): LLM, тільки по тригеру
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from simulation.mcs.state import NpcState, DeltaType
from simulation.mcs.persona import (
    WorldEvent,
    apply_event_to_personas,
    compute_mood_delta,
    classify_delta,
)

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemini-2.0-flash-001"
_LLM_TIMEOUT = 15.0  # seconds

_MOOD_LABELS = {
    (0.0, 0.2): "дуже поганий",
    (0.2, 0.4): "поганий",
    (0.4, 0.6): "нейтральний",
    (0.6, 0.8): "добрий",
    (0.8, 1.01): "відмінний",
}


def _mood_label(state: NpcState) -> str:
    """Map mood energy to a human-readable label."""
    energy = state.mood.energy
    for (lo, hi), label in _MOOD_LABELS.items():
        if lo <= energy < hi:
            return label
    return "невідомий"


class TickProcessor:
    """Two-level tick processor for NPC autonomous life."""

    def __init__(self, llm_interval: int = 10):
        """
        llm_interval — every N ticks call LLM for memory consolidation.
        """
        self.llm_interval = llm_interval

    # ------------------------------------------------------------------
    # Level 1 — cheap math, no LLM, always runs
    # ------------------------------------------------------------------

    def tick_level1(
        self, state: NpcState, event: WorldEvent
    ) -> tuple[NpcState, DeltaType]:
        """
        Cheap tick. No LLM. Always called.

        1. apply_event_to_personas → new persona weights
        2. compute_mood_delta → new mood
        3. classify_delta → DeltaType
        4. tick_count += 1
        5. Append event.description to recent_events (keep last 5)
        6. Return (updated_state, delta_type)
        """
        old_mood = state.mood

        # Update persona weights based on incoming event
        new_personas = apply_event_to_personas(state, event)
        state.personas = new_personas

        # Recompute mood from event impact
        new_mood = compute_mood_delta(state, event)
        state.mood = new_mood

        delta_type = classify_delta(old_mood, new_mood)

        state.tick_count += 1

        # Keep only the last 5 recent events
        state.recent_events.append(event.description)
        if len(state.recent_events) > 5:
            state.recent_events = state.recent_events[-5:]

        return state, delta_type

    # ------------------------------------------------------------------
    # Level 2 — expensive LLM, only on trigger
    # ------------------------------------------------------------------

    def tick_level2(
        self,
        state: NpcState,
        agents_root: Path,
        openrouter_key: str,
    ) -> NpcState:
        """
        Expensive tick. Uses LLM.

        Triggered when:
        - delta == EXPLOSIVE
        - or state.needs_llm(self.llm_interval)

        Steps:
        1. Load SOUL.md for the agent
        2. Build prompt with current state context
        3. POST to OpenRouter
        4. Parse JSON response → state.pending_action
        5. Update state.last_llm_tick
        6. Return updated state

        Defensive: on any error, log and return state unchanged.
        """
        try:
            soul_path = agents_root / state.agent_id / "SOUL.md"
            soul_text = ""
            if soul_path.exists():
                soul_text = soul_path.read_text(encoding="utf-8")[:500]

            dominant_persona = state.personas.dominant()
            mood_summary = (
                f"енергія={state.mood.energy:.2f}, "
                f"страх={state.mood.fear:.2f}, "
                f"напруга={state.mood.tension:.2f} ({_mood_label(state)})"
            )
            recent = "; ".join(state.recent_events) if state.recent_events else "нічого"

            prompt = (
                f"Ти {state.agent_name}. {soul_text}\n\n"
                f"Поточний стан: {mood_summary}\n"
                f"Домінуюча персона: {dominant_persona}\n"
                f"Останні події: {recent}\n\n"
                f"Що ти думаєш і що хочеш зробити далі?\n"
                f'Відповідай ТІЛЬКИ JSON без markdown: '
                f'{{"thought": "...", "action": "...", "target": "agent_id або null"}}'
            )

            response = httpx.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.8,
                },
                timeout=_LLM_TIMEOUT,
            )
            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"].strip()

            # Strip possible markdown code fences
            if content.startswith("```"):
                lines = content.splitlines()
                content = "\n".join(
                    ln for ln in lines if not ln.startswith("```")
                ).strip()

            parsed = json.loads(content)
            state.pending_action = {
                "thought": str(parsed.get("thought", "")),
                "action": str(parsed.get("action", "")),
                "target": parsed.get("target"),
            }
            state.last_llm_tick = state.tick_count
            logger.info(
                "[%s] LLM tick %d: action=%s",
                state.agent_id,
                state.tick_count,
                state.pending_action.get("action"),
            )

        except Exception as exc:
            logger.warning(
                "[%s] Level 2 tick failed (tick=%d): %s",
                state.agent_id,
                state.tick_count,
                exc,
            )

        return state

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process(
        self,
        state: NpcState,
        event: WorldEvent,
        agents_root: Path,
        openrouter_key: str,
    ) -> NpcState:
        """
        Main method. Runs Level 1, and Level 2 if triggered.

        1. state, delta = self.tick_level1(state, event)
        2. if delta == EXPLOSIVE or state.needs_llm(self.llm_interval):
               state = self.tick_level2(state, agents_root, openrouter_key)
        3. return state
        """
        state, delta = self.tick_level1(state, event)

        needs_llm = (
            delta == DeltaType.EXPLOSIVE
            or state.needs_llm(self.llm_interval)
        )

        if needs_llm and openrouter_key:
            state = self.tick_level2(state, agents_root, openrouter_key)
        elif needs_llm:
            logger.debug(
                "[%s] Level 2 skipped — no openrouter_key", state.agent_id
            )

        return state
