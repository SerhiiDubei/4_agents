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

    def to_dict(self) -> dict:
        return {
            "round": self.round_number,
            "actions": {
                agent: {other: round(val, 2) for other, val in acts.items()}
                for agent, acts in self.actions.items()
            },
            "payoffs": self.payoffs.summary() if self.payoffs else {},
            "dialog": self.dialog.to_dict() if self.dialog else {},
            "reveals": [r.summary() for r in self.reveals],
            "notes": self.notes,
            "reasonings": self.reasonings,
        }


@dataclass
class GameResult:
    simulation_id: str
    agent_ids: List[str]
    rounds: List[RoundResult] = field(default_factory=list)
    final_scores: Dict[str, float] = field(default_factory=dict)
    winner: Optional[str] = None
    action_log: Dict[int, Dict[str, Dict[str, float]]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "simulation_id": self.simulation_id,
            "agents": self.agent_ids,
            "total_rounds": len(self.rounds),
            "final_scores": {k: round(v, 2) for k, v in self.final_scores.items()},
            "winner": self.winner,
            "rounds": [r.to_dict() for r in self.rounds],
        }

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
) -> GameResult:
    """
    Run the full Island simulation.

    agents: list of SimAgent (pre-loaded with soul, core, states, memory)
    reveal_requests: {round_number: {revealer_id: target_id}} — optional reveal schedule
    on_progress: callable(event) for real-time progress reporting

    Returns GameResult with full history.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from pipeline.decision_engine import CoreParams, AgentContext, choose_action
    from pipeline.state_machine import update_states, save_states, RoundOutcome
    from pipeline.memory import RoundMemory, save_memory
    from simulation.payoff_matrix import calculate_round_payoffs
    from simulation.reveal_skill import RevealTracker, visible_actions

    import uuid
    sim_id = simulation_id or str(uuid.uuid4())[:8]
    agent_ids = [a.agent_id for a in agents]

    result = GameResult(simulation_id=sim_id, agent_ids=agent_ids)
    reveal_tracker = RevealTracker.initialize(agent_ids)
    cumulative_scores: Dict[str, float] = {a.agent_id: 0.0 for a in agents}
    action_log: Dict[int, Dict[str, Dict[str, float]]] = {}

    for round_num in range(1, total_rounds + 1):

        # --- DM rotation ---
        dm_rotation = _dm_rotation(agent_ids, round_num)

        if on_progress:
            on_progress(f"round:{round_num}:{total_rounds}:dialog_start")

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
                agent_configs.append({
                    "agent_id": agent.agent_id,
                    "soul_md": agent.soul_md,
                    "states_md": agent.states.to_md() if agent.states else "",
                    "memory_summary": agent.memory.summary() if agent.memory else {},
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
                })
            for _dialog_attempt in range(2):
                try:
                    from simulation.dialog_engine import generate_round_dialog_flat
                    round_dialog = generate_round_dialog_flat(
                        round_number=round_num,
                        agent_configs=agent_configs,
                        model=model,
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

        async def _reason_one(agent):
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
                    model=agent.core.get("model", model),
                )
                return agent.agent_id, reasoning_out
            except Exception as _reason_err:
                import sys as _sys
                print(f"  [reasoning] {agent.agent_id} r{round_num}: {_reason_err}", file=_sys.stderr, flush=True)
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
        round_actions: Dict[str, Dict[str, float]] = {}

        for agent in agents:
            core_params = CoreParams.from_dict(agent.core)

            # Build trust scores from states
            trust = {}
            if agent.states and hasattr(agent.states, "trust"):
                trust = {k: v for k, v in agent.states.trust.items()}

            # Build observed actions from last round (what's visible)
            observed = {}
            if round_num > 1:
                vis = visible_actions(
                    observer_id=agent.agent_id,
                    round_number=round_num - 1,
                    all_actions=action_log.get(round_num - 1, {}),
                    reveal_tracker=reveal_tracker,
                    visibility_mode="mixed",
                )
                # Flatten: what did each agent do toward ME last round
                for other_id, other_actions in vis.items():
                    if agent.agent_id in other_actions:
                        observed[other_id] = other_actions[agent.agent_id]

            # Choose action toward each other agent
            # Priority: LLM per-target intent → CORE math fallback
            agent_actions = {}
            last_payoff = (
                agent.memory.last_round().payoff_delta
                if agent.memory and agent.memory.last_round() else 0.0
            )
            reasoning_result = agent_reasoning.get(agent.agent_id)
            llm_intents = reasoning_result.intents if reasoning_result else {}

            for other in agents:
                if other.agent_id == agent.agent_id:
                    continue

                llm_intent = llm_intents.get(other.agent_id)
                if llm_intent is not None:
                    # LLM explicitly decided — use directly (already snapped to valid ACTIONS)
                    agent_actions[other.agent_id] = float(llm_intent)
                else:
                    # Fallback: CORE math softmax
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
                    action_result = choose_action(core_params, per_target_context)
                    agent_actions[other.agent_id] = action_result.action

            round_actions[agent.agent_id] = agent_actions

        action_log[round_num] = round_actions

        if on_progress:
            on_progress(f"round:{round_num}:{total_rounds}:decisions_done")

        # --- Payoff phase ---
        payoffs = calculate_round_payoffs(round_number=round_num, actions=round_actions)
        for agent_id, payoff in payoffs.total.items():
            cumulative_scores[agent_id] = round(cumulative_scores[agent_id] + payoff, 4)

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
        for agent in agents:
            payoff_delta = payoffs.total.get(agent.agent_id, 0.0)

            outcome = RoundOutcome(
                received_actions={
                    other.agent_id: round_actions.get(other.agent_id, {}).get(agent.agent_id, 0.5)
                    for other in agents if other.agent_id != agent.agent_id
                },
                revealed_betrayal=False,  # reveal is private — no public exposure
                was_exposed=False,         # reveal is private — no public exposure
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

            # Update memory
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
                was_revealed_by=None,  # reveal is private — target never knows
                reasoning=agent_reasoning.get(agent.agent_id, ""),
            )
            agent.memory.record_round(round_mem)

            # Post-round reflection — fills round_mem.notes from LLM (non-critical)
            try:
                from pipeline.reflection import reflect_on_round
                notes = reflect_on_round(
                    agent_id=agent.agent_id,
                    soul_md=agent.soul_md,
                    round_mem=round_mem,
                    model=agent.core.get("model", model),
                )
                round_mem.notes = notes
            except Exception as _reflect_err:
                import sys as _sys
                print(f"  [reflect/round] {agent.agent_id} r{round_num}: {_reflect_err}", file=_sys.stderr, flush=True)

            # Snapshot notes and reasoning for RoundResult (before archive_game may clear memory)
            round_notes[agent.agent_id] = round_mem.notes
            # Store structured reasoning: thought text + intents dict
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
        )
        result.rounds.append(round_result)

        if on_progress:
            on_progress(f"round:{round_num}:{total_rounds}:complete")


    result.final_scores = cumulative_scores
    result.action_log = action_log
    result.winner = max(cumulative_scores, key=cumulative_scores.get)

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
                save_memory(agent.memory, agent_dir)

            # Post-game conclusion — fills game_history[-1]["conclusion"] (non-critical)
            try:
                from pipeline.reflection import reflect_on_game
                if agent.memory.game_history:
                    conclusion = reflect_on_game(
                        agent_id=agent.agent_id,
                        soul_md=agent.soul_md,
                        game_summary=agent.memory.game_history[-1],
                        recent_rounds=recent_for_conclusion,
                        model=agent.core.get("model", model),
                    )
                    agent.memory.game_history[-1]["conclusion"] = conclusion
                    # Re-save to disk if needed
                    if has_disk:
                        from pipeline.memory import save_memory
                        save_memory(agent.memory, agent_dir)
            except Exception as _game_reflect_err:
                import sys as _sys
                print(f"  [reflect/game] {agent.agent_id}: {_game_reflect_err}", file=_sys.stderr, flush=True)

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

        agents.append(SimAgent(
            agent_id=agent_id,
            soul_md=soul_md,
            core=core,
            states=states,
            memory=memory,
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
