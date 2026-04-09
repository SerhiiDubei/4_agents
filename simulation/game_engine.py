"""
game_engine.py

Stochastic Game loop for Island — 4 agents, 10 rounds.

Each round:
  1. Dialog phase — agents send public messages and optional DMs (via LLM)
  2. Decision phase — each agent chooses action toward each other (via decision_engine)
  3. Payoff phase — calculate rewards for all pairs
  4. State update — update STATES.md and MEMORY.json for each agent
  5. Reveal window — agents can use reveal skill (optional, async trigger)

The game engine is stateless — it receives agent configs and returns
a full GameResult. Persistence (file I/O) is handled by the caller.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def _action_label_uk(val: float) -> str:
    """Human-readable action label in Ukrainian."""
    if val <= 0.2:
        return "зрадив"
    if val <= 0.45:
        return "майже зрадив"
    if val <= 0.75:
        return "частково підтримав"
    return "повністю підтримав"


def _build_story_context_from_rounds(
    rounds: List["RoundResult"],
    agent_names: Dict[str, str],
    max_chars: int = 700,
) -> str:
    """
    Збирає контекст для LLM: що вирішив кожен агент у попередніх раундах + наслідки.
    Історія розвивається в контексті рішень.
    """
    if not rounds:
        return ""
    names = agent_names or {}

    def _dn(aid: str) -> str:
        return names.get(aid) or (aid.split("_")[-1][:8] if "_" in aid else aid[:8])

    parts = []
    for r in rounds[-4:]:  # останні 4 раунди
        rnum = r.round_number
        acts = getattr(r, "actions", None) or {}
        conseq = getattr(r, "consequences", None) or ""

        # Рішення кожного: X підтримав/зрадив Y
        decisions = []
        for agent_id, targets in acts.items():
            aname = _dn(agent_id)
            for target_id, val in targets.items():
                if agent_id == target_id:
                    continue
                tname = _dn(target_id)
                label = _action_label_uk(float(val))
                decisions.append(f"{aname} {label} {tname}")
        dec_str = "; ".join(decisions) if decisions else "—"
        block = f"Акт {rnum}. Рішення: {dec_str}."
        if conseq:
            block += f" Наслідки: {conseq[:150]}"
        parts.append(block)

    text = " ".join(parts)
    return text[:max_chars] if len(text) > max_chars else text


# ---------------------------------------------------------------------------
# Agent config for simulation
# ---------------------------------------------------------------------------

@dataclass
class SimAgent:
    agent_id: str
    soul_md: str
    core: dict           # full CORE.json dict
    states: object       # AgentState (lazy import)
    memory: object       # AgentMemory (lazy import)
    name: str = ""       # human-readable display name
    dm_target: Optional[str] = None   # who to DM this round (rotates)


# ---------------------------------------------------------------------------
# Round result
# ---------------------------------------------------------------------------

@dataclass
class RoundResult:
    round_number: int
    actions: Dict[str, Dict[str, float]]     # {agent_id: {other_id: action}}
    payoffs: object                           # RoundPayoffs
    dialog: object                            # RoundDialog
    reveals: List[object] = field(default_factory=list)  # RevealRecord list
    state_snapshots: Dict[str, dict] = field(default_factory=dict)
    # Per-agent LLM-generated fields — populated before archive_game clears memory
    notes: Dict[str, str] = field(default_factory=dict)       # post-round reflections
    reasonings: Dict[str, dict] = field(default_factory=dict)  # {thought, intents} per agent
    # Storytell — optional narrative context
    situation: str = ""
    situations_per_agent: Dict[str, str] = field(default_factory=dict)  # agent_id -> LLM situation (500+ chars)
    consequences: str = ""
    situation_reflections: Dict[str, str] = field(default_factory=dict)  # agent_id -> reaction to situation
    round_event: dict = field(default_factory=dict)  # {template, involved_count, formatted_per_agent}
    participants_per_agent: Dict[str, List[str]] = field(default_factory=dict)  # agent_id -> [participant_ids]
    round_narrative: str = ""  # широкий опис: що відбулося для кожного і всіх разом
    # 🔷 Social Fabric — new fields (empty when fabric not active)
    social_actions: Dict[str, List[dict]] = field(default_factory=dict)   # {agent_id: [{target,type,value,vis}]}
    budget_state: Dict[str, dict] = field(default_factory=dict)           # {agent_id: {pool,spent,carryover,received}}
    trust_delta: Dict[str, Dict[str, float]] = field(default_factory=dict) # {agent_id: {peer_id: delta}}

    def _round_action_val(self, val):
        """Round action value for JSON; supports legacy float or multi-dim dict."""
        if isinstance(val, dict):
            return {k: round(v, 2) for k, v in val.items()}
        return round(val, 2)

    def to_dict(self) -> dict:
        d = {
            "round": self.round_number,
            "actions": {
                agent: {other: self._round_action_val(val) for other, val in acts.items()}
                for agent, acts in self.actions.items()
            },
            "payoffs": self.payoffs.summary() if self.payoffs else {},
            "dialog": self.dialog.to_dict() if self.dialog else {},
            "reveals": [r.summary() for r in self.reveals],
            "notes": self.notes,
            "reasonings": self.reasonings,
        }
        if self.situation:
            d["situation"] = self.situation
        if self.situations_per_agent:
            d["situations_per_agent"] = self.situations_per_agent
        if self.consequences:
            d["consequences"] = self.consequences
        if self.situation_reflections:
            d["situation_reflections"] = self.situation_reflections
        if self.round_event:
            d["round_event"] = self.round_event
        if self.participants_per_agent:
            d["participants_per_agent"] = self.participants_per_agent
        if self.round_narrative:
            d["round_narrative"] = self.round_narrative
        # 🔷 Social Fabric fields — only included when fabric was active
        if self.social_actions:
            d["🔷_social_actions"] = self.social_actions
        if self.budget_state:
            d["🔷_budget_state"] = self.budget_state
        if self.trust_delta:
            d["🔷_trust_delta"] = self.trust_delta
        return d


@dataclass
class GameResult:
    simulation_id: str
    agent_ids: List[str]
    agent_names: Dict[str, str] = field(default_factory=dict)  # {agent_id: display_name}
    rounds: List[RoundResult] = field(default_factory=list)
    final_scores: Dict[str, float] = field(default_factory=dict)
    winner: Optional[str] = None
    action_log: Dict[int, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    story_params: dict = field(default_factory=dict)  # storytell: year, place, setup, problem, etc.

    def to_dict(self) -> dict:
        d = {
            "simulation_id": self.simulation_id,
            "agents": self.agent_ids,
            "agent_names": self.agent_names,
            "total_rounds": len(self.rounds),
            "final_scores": {k: round(v, 2) for k, v in self.final_scores.items()},
            "winner": self.winner,
            "rounds": [r.to_dict() for r in self.rounds],
        }
        if self.story_params:
            d["story_params"] = self.story_params
        return d

    def score_range(self) -> dict:
        """
        Calculate theoretical min/max scores for this game configuration.
        Uses PD constants T (Temptation) and S (Sucker) from payoff_matrix.
        """
        from simulation.payoff_matrix import T, S, R, P
        n_agents = len(self.agent_ids)
        n_rounds = len(self.rounds)
        pairs = n_agents - 1  # each agent faces 3 others per round

        max_possible = T * pairs * n_rounds   # always defecting vs cooperating others
        min_possible = S * pairs * n_rounds   # always cooperating vs defecting others
        mutual_coop  = R * pairs * n_rounds   # all cooperate
        mutual_defect = P * pairs * n_rounds  # all defect

        return {
            "n_rounds": n_rounds,
            "n_agents": n_agents,
            "max_possible": round(max_possible, 1),
            "min_possible": round(min_possible, 1),
            "mutual_coop_score": round(mutual_coop, 1),
            "mutual_defect_score": round(mutual_defect, 1),
            "score_range": round(max_possible - min_possible, 1),
            "note": "T>R>P>S — defecting against cooperators wins most, cooperating against defectors loses most",
        }


# ---------------------------------------------------------------------------
# DM rotation — each agent gets to DM someone different each round
# ---------------------------------------------------------------------------

def _dm_rotation(agent_ids: List[str], round_number: int) -> Dict[str, Optional[str]]:
    """Simple rotation: agent i DMs agent (i + round) % n."""
    result = {}
    n = len(agent_ids)
    for i, agent_id in enumerate(agent_ids):
        target_idx = (i + round_number) % n
        # Don't DM yourself
        if target_idx == i:
            target_idx = (target_idx + 1) % n
        result[agent_id] = agent_ids[target_idx] if n > 1 else None
    return result


# ---------------------------------------------------------------------------
# Core game loop
# ---------------------------------------------------------------------------

def run_simulation(
    agents: List[SimAgent],
    total_rounds: int = 20,
    model: str = "google/gemini-2.0-flash-001",
    use_dialog: bool = True,
    simulation_id: Optional[str] = None,
    reveal_requests: Optional[Dict[int, Dict[str, str]]] = None,
    on_progress=None,  # optional callback(event: str) for live logging
    verbose: bool = False,  # if True, print per-call timing to stderr
    story_params_override=None,  # optional StoryParams for custom setup (e.g. Mars)
) -> GameResult:
    """
    Run the full Island simulation.

    agents: list of SimAgent (pre-loaded with soul, core, states, memory)
    reveal_requests: {round_number: {revealer_id: target_id}} — optional reveal schedule
    on_progress: callable(event) for real-time progress reporting
    verbose: if True, print per-LLM-call timing lines to stderr

    Returns GameResult with full history.
    """
    import sys
    import os as _os
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    # Ensure OpenRouter key is available for all per-agent LLM calls (dialog, reasoning, reflection)
    _env_file = _root / ".env"
    if _env_file.exists():
        _txt = _env_file.read_text(encoding="utf-8-sig")
        for _line in _txt.splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k, _v = _k.strip(), _v.strip().strip('"\'')
                if _k == "OPENROUTER_API_KEY" and _v:
                    _os.environ["OPENROUTER_API_KEY"] = _v
                    break

    from pipeline.decision_engine import CoreParams, AgentContext, choose_action, choose_actions
    from pipeline.state_machine import update_states, save_states, RoundOutcome
    from simulation.interaction_dimensions import get_action_for_dim, get_dimension_ids
    from pipeline.memory import RoundMemory, save_memory
    from simulation.payoff_matrix import calculate_round_payoffs
    from simulation.reveal_skill import RevealTracker, visible_actions
    from simulation.social_fabric import SocialFabric, SocialState, SocialAction

    import uuid
    sim_id = simulation_id or str(uuid.uuid4())[:8]
    agent_ids = [a.agent_id for a in agents]

    agent_names = {a.agent_id: (a.name or a.agent_id) for a in agents}
    result = GameResult(simulation_id=sim_id, agent_ids=agent_ids, agent_names=agent_names)
    reveal_tracker = RevealTracker.initialize(agent_ids)
    cumulative_scores: Dict[str, float] = {a.agent_id: 0.0 for a in agents}
    action_log: Dict[int, Dict[str, Dict[str, Dict[str, float]]]] = {}

    # 🔷 Social Fabric — initialize per-agent states
    social_fabric = SocialFabric()
    for _agent in agents:
        social_fabric.add(SocialState.from_core(_agent.agent_id, _agent.core))
    # Trust map mirrors AgentState.trust — fabric updates this each round
    social_trust_map: Dict[str, Dict[str, float]] = {
        a.agent_id: dict(a.states.trust) if (a.states and hasattr(a.states, "trust")) else {}
        for a in agents
    }
    if verbose:
        import sys as _sys
        print(f"  🔷 SocialFabric initialized: {len(agents)} agents", file=_sys.stderr, flush=True)

    # Storytell — one story for the whole game (or custom override)
    story_params = None
    try:
        from storytell import generate_story, get_round_event, get_participants_for_event, generate_situation, generate_consequences
        if story_params_override is not None:
            story_params = story_params_override
        else:
            story_seed = hash(sim_id) % (2**31) if sim_id else 42
            story_params = generate_story(story_seed)
        result.story_params = {
            "year": story_params.year,
            "place": story_params.place,
            "setup": story_params.setup,
            "problem": story_params.problem,
            "characters": story_params.characters,
            "genre": story_params.genre,
            "mood": story_params.mood,
            "stakes": story_params.stakes,
        }
    except Exception:
        pass

    try:
        for round_num in range(1, total_rounds + 1):
            # --- DM rotation ---
            dm_rotation = _dm_rotation(agent_ids, round_num)

            if on_progress:
                on_progress(f"round:{round_num}:{total_rounds}:dialog_start")

            # --- Storytell: per-agent LLM situations (500+ chars each) ---
            round_situation = ""
            situations_per_agent: Dict[str, str] = {}
            round_event = None
            participants_per_agent: Dict[str, List[str]] = {}
            round_event_dict: dict = {}
            if story_params:
                try:
                    from storytell import get_round_event, get_participants_for_event, generate_situation_llm
                    round_event = get_round_event(
                        round_num, total_rounds, story_params, agent_ids, result.agent_names
                    )
                    for agent in agents:
                        parts = get_participants_for_event(
                            round_event, agent_ids, agent.agent_id,
                            seed=story_params.seed,
                        )
                        participants_per_agent[agent.agent_id] = parts
                    round_event_dict = {
                        "template": round_event.template,
                        "involved_count": round_event.involved_count,
                        "formatted_per_agent": {
                            aid: round_event.format(
                                agent_names=result.agent_names,
                                focus_agent=aid,
                                participants=participants_per_agent.get(aid, []),
                            )
                            for aid in agent_ids
                        },
                    }
                    prev_rounds_summary = _build_story_context_from_rounds(
                        result.rounds, result.agent_names, max_chars=700
                    )
                    roster_path = Path(__file__).parent.parent / "agents" / "roster.json"
                    agent_profiles = {}
                    if roster_path.exists():
                        roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
                        for a in roster_data.get("agents", []):
                            aid = a.get("id")
                            if aid in agent_ids and a.get("profile"):
                                agent_profiles[aid] = dict(a["profile"])
                    # Enrich bio from agents/{id}/BIO.md if present
                    for aid in list(agent_profiles.keys()):
                        bio_path = AGENTS_DIR / aid / "BIO.md"
                        if bio_path.exists():
                            agent_profiles[aid]["bio"] = bio_path.read_text(encoding="utf-8").strip()
                    import asyncio as _asyncio
                    import sys as _sys

                    def _gen_sit(agent):
                        try:
                            return agent.agent_id, generate_situation_llm(
                                agent_id=agent.agent_id,
                                round_num=round_num,
                                total_rounds=total_rounds,
                                story_params=story_params,
                                round_event=round_event,
                                agent_names=result.agent_names,
                                prev_rounds_summary=prev_rounds_summary,
                                agent_profiles=agent_profiles,
                            )
                        except Exception as _e:
                            if verbose:
                                print(f"    [sit-gen] {agent.agent_id} ERROR: {_e}", file=_sys.stderr, flush=True)
                            return agent.agent_id, ""

                    _loop = _asyncio.get_event_loop()
                    try:
                        if _loop.is_closed():
                            raise RuntimeError("closed")
                    except RuntimeError:
                        _loop = _asyncio.new_event_loop()
                        _asyncio.set_event_loop(_loop)
                    sit_gen_results = _loop.run_until_complete(
                        _asyncio.gather(*[_asyncio.to_thread(_gen_sit, a) for a in agents])
                    )
                    for aid, text in sit_gen_results:
                        situations_per_agent[aid] = text
                    if situations_per_agent:
                        round_situation = next(iter(situations_per_agent.values()), "")
                except Exception:
                    pass

            # --- Situation reflections (each agent reacts to their situation before dialog) ---
            situation_reflections: Dict[str, str] = {}
            if situations_per_agent and use_dialog:
                try:
                    import sys as _sys
                    from pipeline.reflection import reflect_on_situation
                    if verbose:
                        print(f"  [r{round_num}] situation reflections (parallel)...", file=_sys.stderr, flush=True)
                    import asyncio as _asyncio
                    import time as _time

                    def _run_sit_reflect(agent):
                        _name = result.agent_names.get(agent.agent_id, agent.agent_id)
                        _t0 = _time.time()
                        if verbose:
                            print(f"    [sit]  {_name}...", file=_sys.stderr, flush=True)
                        try:
                            text = reflect_on_situation(
                                agent_id=agent.agent_id,
                                soul_md=agent.soul_md,
                                situation_text=situations_per_agent.get(agent.agent_id, ""),
                                round_num=round_num,
                                agent_names=result.agent_names,
                                model=agent.core.get("model", model),
                            )
                            if verbose:
                                print(f"    [sit]  {_name} done ({_time.time()-_t0:.1f}s)", file=_sys.stderr, flush=True)
                            return agent.agent_id, text
                        except Exception as _e:
                            if verbose:
                                print(f"    [sit]  {_name} ERROR: {_e}", file=_sys.stderr, flush=True)
                            return agent.agent_id, ""

                    _loop = _asyncio.get_event_loop()
                    try:
                        if _loop.is_closed():
                            raise RuntimeError("closed")
                    except RuntimeError:
                        _loop = _asyncio.new_event_loop()
                        _asyncio.set_event_loop(_loop)
                    sit_results = _loop.run_until_complete(
                        _asyncio.gather(*[_asyncio.to_thread(_run_sit_reflect, a) for a in agents])
                    )
                    for aid, text in sit_results:
                        situation_reflections[aid] = text
                except Exception:
                    pass

            # --- Dialog phase ---
            round_dialog = None
            if use_dialog:
                agent_configs = []
                for agent in agents:
                    vis = visible_actions(
                        observer_id=agent.agent_id,
                        round_number=round_num - 1,
                        all_actions=action_log.get(round_num - 1, {}),
                        reveal_tracker=reveal_tracker,
                        visibility_mode="mixed",
                    )
                    last_round = agent.memory.last_round() if agent.memory else None
                    mem_sum = agent.memory.summary() if agent.memory else {}
                    from pipeline.memory import memory_summary_to_narrative
                    bio_path = AGENTS_DIR / agent.agent_id / "BIO.md"
                    bio_text = (bio_path.read_text(encoding="utf-8").strip()[:550]) if bio_path.exists() else ""
                    cfg = {
                        "agent_id": agent.agent_id,
                        "soul_md": agent.soul_md,
                        "states_md": agent.states.to_md() if agent.states else "",
                        "memory_summary": mem_sum,
                        "memory_narrative": memory_summary_to_narrative(mem_sum, agent.agent_id, result.agent_names),
                        "bio": bio_text,
                        "deception_tendency": agent.core.get("deception_tendency", 50),
                        "cooperation_bias": agent.core.get("cooperation_bias", 50),
                        "total_rounds": total_rounds,
                        "visible_history": vis,
                        "dm_target": dm_rotation.get(agent.agent_id),
                        "model": agent.core.get("model", model),
                        "last_round_summary": {
                            "payoff": last_round.payoff_delta,
                            "received": last_round.actions_received,
                            "given": last_round.actions_given,
                        } if last_round else None,
                    }
                    if story_params:
                        cfg["situation_text"] = situations_per_agent.get(agent.agent_id, "")
                        cfg["situation_reflection"] = situation_reflections.get(agent.agent_id, "")
                        cfg["story_context"] = story_params.to_context_str()
                        cfg["round_event_formatted"] = round_event_dict.get("formatted_per_agent", {}).get(agent.agent_id, "")
                        cfg["event_participants"] = participants_per_agent.get(agent.agent_id, [])
                    agent_configs.append(cfg)
                for _dialog_attempt in range(2):
                    try:
                        from simulation.dialog_engine import generate_round_dialog_flat
                        round_dialog = generate_round_dialog_flat(
                            round_number=round_num,
                            agent_configs=agent_configs,
                            model=model,
                            agent_names=result.agent_names,
                            verbose=verbose,
                        )
                        break
                    except Exception as _dialog_err:
                        import sys as _sys
                        print(
                            f"  [dialog] r{round_num} attempt {_dialog_attempt + 1}/2: {_dialog_err}",
                            file=_sys.stderr, flush=True,
                        )
                        if _dialog_attempt == 0:
                            import time as _time
                            _time.sleep(2)
                        else:
                            round_dialog = None

            if on_progress:
                on_progress(f"round:{round_num}:{total_rounds}:dialog_done")

            # --- Pre-decision reasoning (structured: thought + per-target intents)
            # Run all agents' reasoning in parallel to reduce latency
            from pipeline.reasoning import ReasoningResult, generate_reasoning
            import asyncio

            import time as _time
            import sys as _sys

            if verbose:
                print(f"  [r{round_num}] reasoning (parallel)...", file=_sys.stderr, flush=True)

            async def _reason_one(agent):
                _t0 = _time.time()
                _name = result.agent_names.get(agent.agent_id, agent.agent_id)
                if verbose:
                    print(f"    [rsn]  {_name}...", file=_sys.stderr, flush=True)
                try:
                    last_round = agent.memory.last_round() if agent.memory else None
                    peer_ids = [a.agent_id for a in agents if a.agent_id != agent.agent_id]

                    # Build dialog_heard: prefix DM messages with "dm:" so reasoning.py
                    # can separate public from private context
                    dialog_heard: dict = {}
                    if round_dialog:
                        for m in round_dialog.visible_to(agent.agent_id):
                            if m.sender_id == agent.agent_id:
                                continue
                            if m.channel.startswith("dm_"):
                                dialog_heard[f"dm:{m.sender_id}"] = m.text
                            else:
                                dialog_heard[m.sender_id] = m.text

                    trust = {}
                    if agent.states and hasattr(agent.states, "trust"):
                        trust = {k: v for k, v in agent.states.trust.items()}

                    last_reflection = ""
                    if last_round and last_round.notes:
                        last_reflection = last_round.notes
                    mem_summary = agent.memory.summary() if agent.memory else {}
                    from pipeline.memory import memory_summary_to_narrative
                    memory_narrative = memory_summary_to_narrative(mem_summary, agent.agent_id, result.agent_names)
                    _bio_path = AGENTS_DIR / agent.agent_id / "BIO.md"
                    bio_text = (_bio_path.read_text(encoding="utf-8").strip()[:500]) if _bio_path.exists() else ""

                    story_ctx = story_params.to_context_str() if story_params else ""
                    sit_text = (situations_per_agent.get(agent.agent_id, "") or "")[:400]
                    ev_text = round_event_dict.get("formatted_per_agent", {}).get(agent.agent_id, "")
                    ev_parts = participants_per_agent.get(agent.agent_id, [])

                    reasoning_out = await asyncio.to_thread(
                        generate_reasoning,
                        agent_id=agent.agent_id,
                        soul_md=agent.soul_md,
                        round_number=round_num,
                        total_rounds=total_rounds,
                        peer_ids=peer_ids,
                        last_round_summary={
                            "received": last_round.actions_received,
                            "given": last_round.actions_given,
                        } if last_round else None,
                        dialog_heard=dialog_heard,
                        trust_scores=trust,
                        last_reflection=last_reflection,
                        last_conclusion=mem_summary.get("last_conclusion", ""),
                        memory_narrative=memory_narrative,
                        bio=bio_text,
                        model=agent.core.get("model", model),
                        agent_names=result.agent_names,
                        story_context=story_ctx,
                        situation_text=sit_text,
                        situation_reflection=situation_reflections.get(agent.agent_id, ""),
                        round_event_text=ev_text,
                        event_participants=ev_parts,
                        budget_pool=social_fabric.get(agent.agent_id).budget_pool
                            if social_fabric.get(agent.agent_id) else 1.0,
                    )
                    if verbose:
                        print(f"    [rsn]  {_name} done ({_time.time()-_t0:.1f}s)", file=_sys.stderr, flush=True)
                    return agent.agent_id, reasoning_out
                except Exception as _reason_err:
                    print(f"  [reasoning] {_name} r{round_num}: {_reason_err}", file=_sys.stderr, flush=True)
                    return agent.agent_id, None

            async def _run_all_reasoning():
                tasks = [_reason_one(a) for a in agents]
                return await asyncio.gather(*tasks)

            agent_reasoning: Dict[str, ReasoningResult] = {}
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            reasoning_results = loop.run_until_complete(_run_all_reasoning())
            for aid, r_out in reasoning_results:
                if r_out is not None:
                    agent_reasoning[aid] = r_out

            if on_progress:
                on_progress(f"round:{round_num}:{total_rounds}:reasoning_done")

            # --- Decision phase ---
            round_actions: Dict[str, Dict[str, Dict[str, float]]] = {}

            for agent in agents:
                core_params = CoreParams.from_dict(agent.core)

                # Build trust scores from states
                trust = {}
                if agent.states and hasattr(agent.states, "trust"):
                    trust = {k: v for k, v in agent.states.trust.items()}

                # Build observed actions from last round (cooperation only for context)
                observed = {}
                if round_num > 1:
                    prev_actions = action_log.get(round_num - 1, {})
                    for other in agents:
                        if other.agent_id == agent.agent_id:
                            continue
                        obs_val = get_action_for_dim(
                            prev_actions, other.agent_id, agent.agent_id, "cooperation"
                        )
                        observed[other.agent_id] = obs_val

                # Choose action toward each other agent (per dimension)
                agent_actions: Dict[str, Dict[str, float]] = {}
                last_payoff = (
                    agent.memory.last_round().payoff_delta
                    if agent.memory and agent.memory.last_round() else 0.0
                )
                reasoning_result = agent_reasoning.get(agent.agent_id)
                llm_intents = reasoning_result.intents if reasoning_result else {}

                for other in agents:
                    if other.agent_id == agent.agent_id:
                        continue

                    per_target_context = AgentContext(
                        round_number=round_num,
                        total_rounds=total_rounds,
                        trust_scores={other.agent_id: trust.get(other.agent_id, 0.5)},
                        observed_actions={other.agent_id: observed.get(other.agent_id, 0.5)} if observed else {},
                        current_score=cumulative_scores[agent.agent_id],
                        betrayals_received=(
                            agent.memory.betrayals_by(other.agent_id) if agent.memory else 0
                        ),
                        cooperations_received=(
                            agent.memory.cooperations_by(other.agent_id) if agent.memory else 0
                        ),
                        last_round_payoff=last_payoff,
                    )

                    llm_intent = llm_intents.get(other.agent_id)
                    dim_actions: Dict[str, float] = {}

                    if llm_intent is not None:
                        # LLM gave one value (legacy) -> cooperation; other dims from CORE
                        if isinstance(llm_intent, (int, float)):
                            dim_actions["cooperation"] = float(llm_intent)
                            for dim_id in get_dimension_ids():
                                if dim_id != "cooperation":
                                    res = choose_action(core_params, per_target_context, dim_id=dim_id)
                                    dim_actions[dim_id] = res.action
                        else:
                            # LLM gave dict per dim
                            for dim_id in get_dimension_ids():
                                dim_actions[dim_id] = float(
                                    llm_intent.get(dim_id)
                                    if isinstance(llm_intent.get(dim_id), (int, float))
                                    else choose_action(core_params, per_target_context, dim_id=dim_id).action
                                )
                    else:
                        # Fallback: CORE math for all dimensions
                        dim_actions = choose_actions(core_params, per_target_context)

                    agent_actions[other.agent_id] = dim_actions

                round_actions[agent.agent_id] = agent_actions

            action_log[round_num] = round_actions

            # 🔷 Social Fabric — build SocialAction list from reasoning results
            round_social_actions: Dict[str, list] = {}
            for _agent in agents:
                _r = agent_reasoning.get(_agent.agent_id)
                _sa_dicts = _r.social_actions if _r and _r.social_actions else []
                _peer_ids = [a.agent_id for a in agents if a.agent_id != _agent.agent_id]
                _state = social_fabric.get(_agent.agent_id)

                if _sa_dicts:
                    # Convert dicts → SocialAction objects (validate)
                    _sa_objs = []
                    _peer_set = set(_peer_ids)
                    for _sa in _sa_dicts:
                        try:
                            _t = _sa.get("target", "")
                            if _t not in _peer_set:
                                # 🔷 target hallucination — silently drop invalid target
                                import sys as _sys
                                print(
                                    f"  🔷 [r{round_num}] {result.agent_names.get(_agent.agent_id, _agent.agent_id)}"
                                    f" → invalid target '{_t}' (not in peers), dropped",
                                    file=_sys.stderr, flush=True,
                                )
                                continue
                            _sa_objs.append(SocialAction(
                                target=_t,
                                type=_sa.get("type", "ignore"),
                                value=float(_sa.get("value", 0.0)),
                                visibility=_sa.get("visibility", "public"),
                            ))
                        except (KeyError, ValueError):
                            pass
                    # Enforce minimum + normalize to budget
                    _sa_objs = social_fabric.enforce_minimum_action(_agent.agent_id, _sa_objs, _peer_ids)
                    if _state:
                        _sa_objs = _state.normalize_actions(_sa_objs)
                    round_social_actions[_agent.agent_id] = [s.to_dict() for s in _sa_objs]
                else:
                    # Legacy path: no social_actions from LLM — inject ignore as minimum
                    _sa_objs = social_fabric.enforce_minimum_action(_agent.agent_id, [], _peer_ids)
                    round_social_actions[_agent.agent_id] = [s.to_dict() for s in _sa_objs]

            # Apply round: update trust + recalculate budgets
            _trust_before = {aid: dict(t) for aid, t in social_trust_map.items()}
            _sa_objs_map = {}
            for _aid, _sa_list in round_social_actions.items():
                _sa_objs_map[_aid] = [
                    SocialAction(s["target"], s["type"], s["value"], s["visibility"])
                    for s in _sa_list
                ]
            social_trust_map = social_fabric.apply_round(_sa_objs_map, social_trust_map)

            # Build budget_state snapshot + trust_delta for logging
            _budget_state_snap: Dict[str, dict] = {}
            _trust_delta_snap: Dict[str, Dict[str, float]] = {}
            for _agent in agents:
                _state = social_fabric.get(_agent.agent_id)
                if _state:
                    _budget_state_snap[_agent.agent_id] = {
                        "pool": _state.budget_pool,
                        "spent": _state.budget_spent_last,
                        "carryover": round(max(0.0, _state.budget_pool - _state.budget_base), 3),
                        "received": dict(_state.received_last_round),
                    }
                _before = _trust_before.get(_agent.agent_id, {})
                _after  = social_trust_map.get(_agent.agent_id, {})
                _deltas = {pid: round(_after.get(pid, 0.5) - _before.get(pid, 0.5), 4)
                           for pid in set(list(_before.keys()) + list(_after.keys()))}
                _trust_delta_snap[_agent.agent_id] = {k: v for k, v in _deltas.items() if abs(v) > 0.001}

            # 🔷 Verbose logging for social fabric
            if verbose:
                print(f"  🔷 [r{round_num}] social fabric:", file=_sys.stderr, flush=True)
                for _aid, _sa_list in round_social_actions.items():
                    _name = agent_names.get(_aid, _aid)
                    _bs = _budget_state_snap.get(_aid, {})
                    _acts_str = ", ".join(
                        f"{s['type']}→{agent_names.get(s['target'], s['target'][:6])}({s['value']:.2f},{s['visibility'][:3]})"
                        for s in _sa_list
                    )
                    print(
                        f"    🔷 {_name}: [{_acts_str}]  budget={_bs.get('pool','?')}",
                        file=_sys.stderr, flush=True,
                    )

            if on_progress:
                on_progress(f"round:{round_num}:{total_rounds}:decisions_done")

            # --- Payoff phase ---
            payoffs = calculate_round_payoffs(round_number=round_num, actions=round_actions)
            for agent_id, payoff in payoffs.total.items():
                cumulative_scores[agent_id] = round(cumulative_scores[agent_id] + payoff, 4)

            # --- Storytell: consequences after payoffs ---
            round_consequences = ""
            round_narrative = ""
            if story_params:
                try:
                    from storytell import generate_consequences
                    payoffs_summary = payoffs.total if hasattr(payoffs, "total") else {}
                    round_consequences = generate_consequences(
                        round_num, round_actions, payoffs_summary, story_params, result.agent_names
                    )
                except Exception as _cons_err:
                    import sys as _sys
                    print(f"  [storytell] consequences r{round_num}: {_cons_err}", file=_sys.stderr, flush=True)

                # --- Storytell: широкий опис раунду (що відбулося для кожного і всіх) ---
                try:
                    from storytell import generate_round_narrative
                    roster_path = Path(__file__).parent.parent / "agents" / "roster.json"
                    agent_profiles = {}
                    if roster_path.exists():
                        roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
                        for a in roster_data.get("agents", []):
                            aid = a.get("id")
                            if aid in agent_ids and a.get("profile"):
                                agent_profiles[aid] = dict(a["profile"])
                    for aid in list(agent_profiles.keys()):
                        bio_path = AGENTS_DIR / aid / "BIO.md"
                        if bio_path.exists():
                            agent_profiles[aid]["bio"] = bio_path.read_text(encoding="utf-8").strip()
                    prev_narr = " ".join(
                        r.round_narrative for r in result.rounds[-2:] if getattr(r, "round_narrative", "")
                    )[:500]
                    round_narrative = generate_round_narrative(
                        round_num=round_num,
                        total_rounds=total_rounds,
                        actions=round_actions,
                        payoffs=payoffs.total if hasattr(payoffs, "total") else {},
                        story_params=story_params,
                        agent_names=result.agent_names,
                        round_event_template=round_event_dict.get("template", ""),
                        prev_rounds_narrative=prev_narr,
                        agent_profiles=agent_profiles,
                    )
                except Exception as _narr_err:
                    import sys as _sys
                    print(f"  [storytell] round_narrative r{round_num}: {_narr_err}", file=_sys.stderr, flush=True)

            # --- Reveal window ---
            round_reveals = []
            if reveal_requests and round_num in reveal_requests:
                for revealer_id, target_id in reveal_requests[round_num].items():
                    record = reveal_tracker.use_reveal(
                        revealer_id=revealer_id,
                        target_id=target_id,
                        round_number=round_num,
                        action_log=action_log,
                        all_agent_ids=agent_ids,
                    )
                    if record:
                        round_reveals.append(record)
                        # Apply trust delta privately to the revealer only
                        revealer_agent = next(
                            (a for a in agents if a.agent_id == revealer_id), None
                        )
                        if revealer_agent and record.trust_delta_applied != 0.0:
                            current_trust = revealer_agent.states.trust.get(target_id, 0.5)
                            new_trust = max(0.0, min(1.0, current_trust + record.trust_delta_applied))
                            revealer_agent.states.trust[target_id] = round(new_trust, 4)

            # --- State update ---
            # Collect LLM-generated fields per agent for RoundResult (must happen before archive_game clears memory)
            round_notes: Dict[str, str] = {}
            round_reasoning_snapshot: Dict[str, str] = {}

            dialog_signals: Dict[str, Dict[str, str]] = {}
            if round_dialog:
                # Use talk_signals from stepped dialog (real transition outcomes)
                if hasattr(round_dialog, "talk_signals") and round_dialog.talk_signals:
                    for listener_id, signal in round_dialog.talk_signals.items():
                        if listener_id not in dialog_signals:
                            dialog_signals[listener_id] = {}
                        # Find who most recently signalled this listener
                        for msg in reversed(round_dialog.public_messages()):
                            if msg.sender_id != listener_id:
                                dialog_signals[listener_id][msg.sender_id] = signal
                                break
                else:
                    # Fallback: infer from is_deceptive flag
                    for msg in round_dialog.public_messages():
                        signal = "deceptive" if msg.is_deceptive else "cooperative" if random.random() > 0.5 else "neutral"
                        for other_id in agent_ids:
                            if other_id != msg.sender_id:
                                if other_id not in dialog_signals:
                                    dialog_signals[other_id] = {}
                                dialog_signals[other_id][msg.sender_id] = signal

            state_snapshots = {}
            # Build per-agent state + memory objects (sync, fast — no LLM)
            agent_round_mems: Dict[str, object] = {}
            for agent in agents:
                payoff_delta = payoffs.total.get(agent.agent_id, 0.0)

                outcome = RoundOutcome(
                    received_actions={
                        other.agent_id: dict(round_actions.get(other.agent_id, {}).get(agent.agent_id, {"cooperation": 0.5}))
                        for other in agents if other.agent_id != agent.agent_id
                    },
                    revealed_betrayal=False,
                    was_exposed=False,
                    payoff_delta=payoff_delta,
                    dialog_signals=dialog_signals.get(agent.agent_id, {}),
                )

                new_state = update_states(
                    agent.states,
                    outcome,
                    core_cooperation_bias=agent.core.get("cooperation_bias", 50),
                )
                agent.states = new_state
                state_snapshots[agent.agent_id] = new_state.to_dict()

                round_mem = RoundMemory(
                    round_number=round_num,
                    actions_given=round_actions.get(agent.agent_id, {}),
                    actions_received=outcome.received_actions,
                    dialog_heard={
                        m.sender_id: m.text
                        for m in (round_dialog.visible_to(agent.agent_id) if round_dialog else [])
                    },
                    payoff_delta=payoff_delta,
                    total_score=cumulative_scores[agent.agent_id],
                    mood=new_state.mood,
                    reveal_used=next(
                        (r.target_id for r in round_reveals if r.revealer_id == agent.agent_id), None
                    ),
                    was_revealed_by=None,
                    reasoning=agent_reasoning.get(agent.agent_id, ""),
                )
                agent.memory.record_round(round_mem)
                agent_round_mems[agent.agent_id] = round_mem

            # Post-round reflections — parallel LLM calls (non-critical)
            from pipeline.reflection import reflect_on_round as _reflect_fn, log_reflection_error as _log_reflection_error

            if verbose:
                print(f"  [r{round_num}] reflections (parallel)...", file=_sys.stderr, flush=True)

            def _run_reflect_one(agent):
                _name = result.agent_names.get(agent.agent_id, agent.agent_id)
                _t0 = _time.time()
                if verbose:
                    print(f"    [ref]  {_name}...", file=_sys.stderr, flush=True)
                try:
                    notes = _reflect_fn(
                        agent_id=agent.agent_id,
                        soul_md=agent.soul_md,
                        round_mem=agent_round_mems[agent.agent_id],
                        model=agent.core.get("model", model),
                        agent_names=result.agent_names,
                        situation_text=situations_per_agent.get(agent.agent_id, round_situation),
                    )
                    if verbose:
                        print(f"    [ref]  {_name} done ({_time.time()-_t0:.1f}s)", file=_sys.stderr, flush=True)
                    return agent.agent_id, notes
                except Exception as _reflect_err:
                    print(f"  [reflect/round] {_name} r{round_num}: {_reflect_err}", file=_sys.stderr, flush=True)
                    _log_reflection_error(agent.agent_id, f"round r{round_num}", _reflect_err)
                    return agent.agent_id, ""

            async def _gather_reflections():
                return await asyncio.gather(
                    *[asyncio.to_thread(_run_reflect_one, a) for a in agents]
                )

            reflect_results = loop.run_until_complete(_gather_reflections())
            for aid, notes in reflect_results:
                agent_round_mems[aid].notes = notes

            # Snapshot reasoning + notes for RoundResult
            for agent in agents:
                round_mem = agent_round_mems[agent.agent_id]
                round_notes[agent.agent_id] = round_mem.notes
                r_result = agent_reasoning.get(agent.agent_id)
                if r_result:
                    round_mem.reasoning = r_result.thought
                    round_reasoning_snapshot[agent.agent_id] = r_result.to_dict()
                else:
                    round_reasoning_snapshot[agent.agent_id] = {"thought": round_mem.reasoning, "intents": {}}

            # --- Record round ---
            round_result = RoundResult(
                round_number=round_num,
                actions=round_actions,
                payoffs=payoffs,
                dialog=round_dialog,
                reveals=round_reveals,
                state_snapshots=state_snapshots,
                notes=round_notes,
                reasonings=round_reasoning_snapshot,
                situation=round_situation,
                situations_per_agent=situations_per_agent,
                consequences=round_consequences,
                situation_reflections=situation_reflections,
                round_event=round_event_dict,
                participants_per_agent=participants_per_agent,
                round_narrative=round_narrative,
                social_actions=round_social_actions,
                budget_state=_budget_state_snap,
                trust_delta=_trust_delta_snap,
            )
            result.rounds.append(round_result)

            if on_progress:
                # Pass round_result as optional second arg so live renderers
                # can display the round immediately without waiting for all rounds
                try:
                    on_progress(f"round:{round_num}:{total_rounds}:complete", round_result)
                except TypeError:
                    on_progress(f"round:{round_num}:{total_rounds}:complete")

    finally:
        # Always archive and save — even on interrupt/crash. "Якщо лог добавився — він в історії"
        result.final_scores = cumulative_scores
        result.action_log = action_log
        result.winner = max(cumulative_scores, key=cumulative_scores.get) if cumulative_scores else (agent_ids[0] if agent_ids else "")

        # --- Archive game in each agent's memory for cross-game persistence ---
        for agent in agents:
            if agent.memory:
                agent_dir = AGENTS_DIR / agent.agent_id
                has_disk = agent_dir.exists()

                # Collect recent rounds BEFORE archive_game clears them (real agents)
                recent_for_conclusion = [r.to_dict() for r in agent.memory.rounds[-5:]]

                # Only clear rounds when saving to disk (real agents with persistent storage)
                agent.memory.archive_game(
                    game_id=result.simulation_id,
                    winner=result.winner,
                    clear_rounds=has_disk,
                )
                if has_disk:
                    from pipeline.memory import save_memory
                    from pipeline.state_machine import save_states
                    save_memory(agent.memory, agent_dir)
                    save_states(agent.states, agent_dir, display_name=agent.name)

                # Post-game conclusion — fills game_history[-1]["conclusion"] (non-critical)
                if agent.memory.game_history:
                    import time as _time
                    from pipeline.reflection import reflect_on_game, log_reflection_error as _log_reflection_error
                    conclusion = None
                    for attempt in range(2):  # initial + 1 retry
                        try:
                            conclusion = reflect_on_game(
                                agent_id=agent.agent_id,
                                soul_md=agent.soul_md,
                                game_summary=agent.memory.game_history[-1],
                                recent_rounds=recent_for_conclusion,
                                model=agent.core.get("model", model),
                                agent_names=result.agent_names,
                            )
                            break
                        except Exception as _game_reflect_err:
                            import sys as _sys
                            print(f"  [reflect/game] {agent.agent_id}: {_game_reflect_err}", file=_sys.stderr, flush=True)
                            _log_reflection_error(agent.agent_id, f"game {result.simulation_id}", _game_reflect_err)
                            if attempt == 0:
                                _time.sleep(2)
                    if conclusion is not None:
                        agent.memory.game_history[-1]["conclusion"] = conclusion
                        if has_disk:
                            from pipeline.memory import save_memory
                            save_memory(agent.memory, agent_dir)

    return result


# ---------------------------------------------------------------------------
# Load agents from disk
# ---------------------------------------------------------------------------

def load_agents_from_disk(agent_ids: List[str], agents_dir: Path = AGENTS_DIR) -> List[SimAgent]:
    """Load SimAgent objects from saved agent directories."""
    import sys
    sys.path.insert(0, str(agents_dir.parent))
    from pipeline.state_machine import load_states, initialize_states
    from pipeline.memory import load_memory, initialize_memory

    agents = []
    for agent_id in agent_ids:
        agent_dir = agents_dir / agent_id

        # SOUL.md
        soul_path = agent_dir / "SOUL.md"
        soul_md = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

        # CORE.json
        core_path = agent_dir / "CORE.json"
        core = json.loads(core_path.read_text(encoding="utf-8")) if core_path.exists() else {}

        # STATES.md
        peers = [a for a in agent_ids if a != agent_id]
        states = load_states(agent_dir)
        if not states.trust:
            states = initialize_states(agent_id, peers, agent_dir)

        # MEMORY.json
        memory = load_memory(agent_dir)
        if not memory.rounds and not (agent_dir / "MEMORY.json").exists():
            memory = initialize_memory(agent_id, agent_dir)

        # Seed trust from last game's snapshot so "memory" of others carries over
        if memory.game_history:
            snapshot = memory.game_history[-1].get("trust_snapshot", {})
            for peer_id, value in snapshot.items():
                if peer_id in peers:
                    states.trust[peer_id] = value

        agents.append(SimAgent(
            agent_id=agent_id,
            soul_md=soul_md,
            core=core,
            states=states,
            memory=memory,
            name=core.get("name", ""),
        ))

    return agents


# ---------------------------------------------------------------------------
# CLI smoke test (offline — no LLM)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from pipeline.decision_engine import CoreParams
    from pipeline.state_machine import AgentState
    from pipeline.memory import AgentMemory

    agent_ids = ["agent_a", "agent_b", "agent_c", "agent_d"]

    cores = [
        {"cooperation_bias": 80, "deception_tendency": 10, "strategic_horizon": 70, "risk_appetite": 30},
        {"cooperation_bias": 15, "deception_tendency": 85, "strategic_horizon": 30, "risk_appetite": 60},
        {"cooperation_bias": 55, "deception_tendency": 40, "strategic_horizon": 90, "risk_appetite": 20},
        {"cooperation_bias": 50, "deception_tendency": 50, "strategic_horizon": 50, "risk_appetite": 95},
    ]

    agents = []
    for i, agent_id in enumerate(agent_ids):
        peers = [a for a in agent_ids if a != agent_id]
        agents.append(SimAgent(
            agent_id=agent_id,
            soul_md=f"Agent {agent_id} placeholder soul.",
            core=cores[i],
            states=AgentState(agent_id=agent_id, trust={p: 0.5 for p in peers}),
            memory=AgentMemory(agent_id=agent_id),
        ))

    print("Running simulation (no dialog, offline)...")
    result = run_simulation(agents, total_rounds=3, use_dialog=False)

    print(json.dumps({
        "winner": result.winner,
        "final_scores": result.final_scores,
        "rounds_played": len(result.rounds),
    }, indent=2))

    for rnd in result.rounds:
        print(f"\nRound {rnd.round_number} payoffs:", rnd.payoffs.summary()["payoffs"])
