"""
test_pipeline.py

Automated QA tests for the Island Agent Init pipeline.

Groups:
  - OFFLINE tests (no API calls, instant)
  - ONLINE tests  (1-2 real OpenRouter calls, require OPENROUTER_API_KEY)

Run:
    python3 tests/test_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Make sure imports resolve from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Minimal test runner (no external deps)
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: list[dict] = []


def test(name: str):
    """Decorator to register and run a test function."""
    def decorator(fn):
        start = time.time()
        status = PASS
        error = ""
        try:
            fn()
        except AssertionError as e:
            status = FAIL
            error = str(e) or "Assertion failed"
        except Exception as e:
            status = FAIL
            error = f"{type(e).__name__}: {e}"
        elapsed = round((time.time() - start) * 1000)
        results.append({"name": name, "status": status, "ms": elapsed, "error": error})
        icon = "P" if status == PASS else ("F" if status == FAIL else "-")
        print(f"  {icon} [{status}] {name} ({elapsed}ms)" + (f"\n      -> {error}" if error else ""))
        return fn
    return decorator


def skip_test(name: str, reason: str):
    results.append({"name": name, "status": SKIP, "ms": 0, "error": reason})
    print(f"  - [SKIP] {name}\n      -> {reason}")


# ---------------------------------------------------------------------------
# OFFLINE TESTS
# ---------------------------------------------------------------------------

print("\n=======================================")
print("  OFFLINE TESTS (no API)")
print("=======================================")


@test("meta_params: schema loads without error")
def _():
    from pipeline.seed_generator import load_meta_params_schema
    schema = load_meta_params_schema()
    assert isinstance(schema, dict)
    for key in ["drive", "temperament", "blind_spot", "stress_response", "social_style", "intensity"]:
        assert key in schema, f"Missing key: {key}"
        assert len(schema[key]) >= 4, f"Too few options for {key}"


@test("meta_params: random_meta_params returns valid values")
def _():
    from pipeline.seed_generator import random_meta_params, load_meta_params_schema
    schema = load_meta_params_schema()
    for _ in range(20):
        p = random_meta_params()
        assert p.drive in schema["drive"], f"Invalid drive: {p.drive}"
        assert p.temperament in schema["temperament"], f"Invalid temperament: {p.temperament}"
        assert p.blind_spot in schema["blind_spot"], f"Invalid blind_spot: {p.blind_spot}"
        assert p.stress_response in schema["stress_response"]
        assert p.social_style in schema["social_style"]
        assert p.intensity in schema["intensity"]


@test("meta_params: random produces variety (not always the same)")
def _():
    from pipeline.seed_generator import random_meta_params
    seen = set()
    for _ in range(30):
        p = random_meta_params()
        seen.add(p.drive + p.temperament + p.blind_spot)
    assert len(seen) >= 3, f"Too little variety, got {len(seen)} unique combos in 30 runs"


@test("env: _read_openrouter_key_from_env_file prefers process env and errors when missing")
def _():
    # Import inside test to avoid side effects at module import time
    import server.main as server_main

    original_env_value = os.environ.get("OPENROUTER_API_KEY")
    original_project_root = server_main._PROJECT_ROOT
    original_cwd = os.getcwd()

    try:
        # Happy path: key from process env
        os.environ["OPENROUTER_API_KEY"] = "test-key-from-env"
        key, source = server_main._read_openrouter_key_from_env_file()
        assert key == "test-key-from-env", f"Expected key from env, got {key!r}"
        assert source == "env", f"Expected source 'env', got {source!r}"

        # Error path: no key in env and no .env in either _PROJECT_ROOT or CWD
        os.environ.pop("OPENROUTER_API_KEY", None)
        tmp_root = Path(__file__).parent / "_no_env_root"
        tmp_root.mkdir(exist_ok=True)
        server_main._PROJECT_ROOT = tmp_root
        os.chdir(tmp_root)
        # Ensure there is no .env file in tmp_root
        env_path = tmp_root / ".env"
        if env_path.exists():
            env_path.unlink()

        try:
            server_main._read_openrouter_key_from_env_file()
            assert False, "Expected EnvironmentError when OPENROUTER_API_KEY is missing everywhere"
        except EnvironmentError:
            pass
    finally:
        # Restore env var
        if original_env_value is not None:
            os.environ["OPENROUTER_API_KEY"] = original_env_value
        else:
            os.environ.pop("OPENROUTER_API_KEY", None)
        # Restore project root and cwd
        server_main._PROJECT_ROOT = original_project_root
        os.chdir(original_cwd)


@test("core_defaults: schema loads correctly")
def _():
    from pipeline.question_engine import load_core_base, load_delta_table
    base = load_core_base()
    delta_table = load_delta_table()
    for key in ["cooperation_bias", "deception_tendency", "strategic_horizon", "risk_appetite"]:
        assert key in base, f"Missing base key: {key}"
        assert base[key] == 50, f"Base value for {key} should be 50"
    assert len(delta_table) >= 10, "Too few delta entries"


@test("core: delta apply stays within 0–100")
def _():
    from pipeline.question_engine import CoreValues
    core = CoreValues()
    # Push extreme positive
    for _ in range(50):
        core.apply_delta({"cooperation_bias": 10, "deception_tendency": 10,
                          "strategic_horizon": 10, "risk_appetite": 10})
    for key, val in core.to_dict().items():
        assert val <= 100, f"{key} exceeded 100: {val}"
    # Push extreme negative
    core2 = CoreValues()
    for _ in range(50):
        core2.apply_delta({"cooperation_bias": -10, "deception_tendency": -10,
                           "strategic_horizon": -10, "risk_appetite": -10})
    for key, val in core2.to_dict().items():
        assert val >= 0, f"{key} went below 0: {val}"


@test("core: delta table keys all map to valid CORE fields")
def _():
    from pipeline.question_engine import load_delta_table
    valid_fields = {"cooperation_bias", "deception_tendency", "strategic_horizon", "risk_appetite"}
    delta_table = load_delta_table()
    for delta_key, delta in delta_table.items():
        for field in delta:
            assert field in valid_fields, f"Unknown field '{field}' in delta '{delta_key}'"


@test("question_contexts: all 7 contexts load with required fields")
def _():
    from pipeline.question_engine import load_contexts
    contexts = load_contexts()
    assert len(contexts) == 7, f"Expected 7 contexts, got {len(contexts)}"
    for ctx in contexts:
        assert ctx.context_id, "context_id missing"
        assert ctx.scenario_hint, "scenario_hint missing"
        assert len(ctx.answer_slots) >= 3, f"Too few answer slots in {ctx.context_id}"
        for slot in ctx.answer_slots:
            assert slot.label, "slot label missing"
            assert slot.delta_key, "slot delta_key missing"


@test("question_contexts: all delta_keys exist in delta_table")
def _():
    from pipeline.question_engine import load_contexts, load_delta_table
    delta_table = load_delta_table()
    contexts = load_contexts()
    for ctx in contexts:
        for slot in ctx.answer_slots:
            assert slot.delta_key in delta_table, \
                f"delta_key '{slot.delta_key}' in context '{ctx.context_id}' not found in delta_table"


@test("soul_template: 6 sections load with instruction and tov_example")
def _():
    from pipeline.soul_compiler import load_soul_template
    sections = load_soul_template()
    assert len(sections) == 6, f"Expected 6 sections, got {len(sections)}"
    expected = ["Identity", "How You See Others", "What You Never Say Out Loud",
                "What Makes You Feel Safe", "Under Pressure", "Decision Instinct"]
    for i, sec in enumerate(sections):
        assert sec.section == expected[i], f"Section {i} mismatch: {sec.section}"
        assert sec.instruction, f"Missing instruction in '{sec.section}'"
        assert sec.tov_example, f"Missing tov_example in '{sec.section}'"
        assert sec.max_lines >= 2, f"max_lines too low in '{sec.section}'"


@test("session_state: serialization round-trip is lossless")
def _():
    from pipeline.question_engine import SessionState, CoreValues
    original = SessionState(
        seed_text="You notice things.",
        meta_params={"drive": "clarity", "temperament": "measured", "intensity": 3},
        core=CoreValues(cooperation_bias=60, deception_tendency=40, strategic_horizon=70, risk_appetite=45),
        answers=[{"context_id": "trust", "delta_key": "wait_and_observe", "choice_label": "Wait"}],
        trait_log=["long-term thinker"],
        current_context_index=1,
    )
    as_dict = original.to_dict()
    restored = SessionState.from_dict(as_dict)
    assert restored.seed_text == original.seed_text
    assert restored.core.cooperation_bias == 60
    assert restored.core.deception_tendency == 40
    assert restored.current_context_index == 1
    assert restored.trait_log == ["long-term thinker"]
    assert restored.answers[0]["context_id"] == "trust"


@test("process_answer: correctly applies delta and increments index")
def _():
    from pipeline.question_engine import SessionState, CoreValues, process_answer
    session = SessionState(
        seed_text="Test.",
        meta_params={"drive": "clarity", "temperament": "measured", "intensity": 2},
        core=CoreValues(),
    )
    before_coop = session.core.cooperation_bias
    session = process_answer(
        session=session,
        delta_key="trust_immediately",
        choice_label="Trust immediately",
        free_text=None,
        context_id="trust",
    )
    assert session.current_context_index == 1
    assert len(session.answers) == 1
    # trust_immediately gives +10 to cooperation
    assert session.core.cooperation_bias == before_coop + 10, \
        f"Expected {before_coop + 10}, got {session.core.cooperation_bias}"


@test("existing agents: CORE.json files are valid")
def _():
    agents_dir = Path(__file__).parent.parent / "agents"
    core_files = list(agents_dir.glob("*/CORE.json"))
    if len(core_files) < 1:
        skip_test("existing agents: CORE.json files are valid", "No agents found — run initialization first")
        return
    for path in core_files:
        with open(path) as f:
            data = json.load(f)
        for field in ["cooperation_bias", "deception_tendency", "strategic_horizon", "risk_appetite"]:
            val = data.get(field)
            assert val is not None, f"Missing {field} in {path.parent.name}"
            assert 0 <= val <= 100, f"{field}={val} out of range in {path.parent.name}"
        assert data.get("version"), f"Missing version in {path.parent.name}"


@test("existing agents: SOUL.md files have all 6 sections")
def _():
    agents_dir = Path(__file__).parent.parent / "agents"
    soul_files = list(agents_dir.glob("*/SOUL.md"))
    if len(soul_files) < 1:
        skip_test("existing agents: SOUL.md files have all 6 sections", "No SOUL.md files found")
        return
    required_sections = [
        "## Identity", "## How You See Others", "## What You Never Say Out Loud",
        "## What Makes You Feel Safe", "## Under Pressure", "## Decision Instinct"
    ]
    for path in soul_files:
        content = path.read_text()
        for section in required_sections:
            assert section in content, f"Missing '{section}' in {path.parent.name}/SOUL.md"
        assert "You" in content, f"No second-person ('You') found in {path.parent.name}/SOUL.md"


@test("existing agents: different agents have different CORE values")
def _():
    agents_dir = Path(__file__).parent.parent / "agents"
    core_files = list(agents_dir.glob("*/CORE.json"))
    if len(core_files) < 2:
        skip_test("existing agents: different agents have different CORE values",
                  "Need at least 2 agents to compare — run initialization again")
        return
    values = []
    for path in core_files:
        with open(path) as f:
            data = json.load(f)
        values.append((data["cooperation_bias"], data["deception_tendency"],
                        data["strategic_horizon"], data["risk_appetite"]))
    assert len(set(values)) >= 2, "All agents have identical CORE values — generator may be broken"


@test("parse_questions_json: handles plain JSON, trailing commas and fenced blocks")
def _():
    from server.main import _parse_questions_json

    # Plain JSON array
    src1 = '[{"id": 1, "text": "Q1", "answers": []}]'
    parsed1 = _parse_questions_json(src1)
    assert isinstance(parsed1, list), "Expected list from _parse_questions_json"
    assert len(parsed1) == 1 and parsed1[0]["id"] == 1

    # Trailing comma before closing bracket
    src2 = '[{"id": 2, "text": "Q2", "answers": []},]'
    parsed2 = _parse_questions_json(src2)
    assert len(parsed2) == 1 and parsed2[0]["id"] == 2

    # Markdown fenced block with ```json
    src3 = "```json\n[{\"id\": 3, \"text\": \"Q3\", \"answers\": []}]\n```"
    parsed3 = _parse_questions_json(src3)
    assert len(parsed3) == 1 and parsed3[0]["id"] == 3


# ---------------------------------------------------------------------------
# ONLINE TESTS (real API)
# ---------------------------------------------------------------------------

print("\n=======================================")
print("  ONLINE TESTS (OpenRouter API)")
print("=======================================")

api_key = os.environ.get("OPENROUTER_API_KEY", "")
run_online = os.environ.get("RUN_ONLINE_TESTS") == "1"

if not api_key or not run_online:
    reason = "ONLINE tests disabled (set RUN_ONLINE_TESTS=1 and OPENROUTER_API_KEY to enable)"
    skip_test("seed: generates paragraph", reason)
    skip_test("seed: output is 80-140 words", reason)
    skip_test("question: generates valid JSON with question + options", reason)
else:
    @test("seed: LLM generates a non-empty paragraph")
    def _():
        from pipeline.seed_generator import random_meta_params, generate_seed
        result = generate_seed(random_meta_params())
        assert result.seed_text, "seed_text is empty"
        assert len(result.seed_text) > 50, "seed_text too short"
        assert result.meta_params is not None


    @test("seed: output is within 80-140 word target (±20 tolerance)")
    def _():
        from pipeline.seed_generator import random_meta_params, generate_seed
        result = generate_seed(random_meta_params())
        word_count = len(result.seed_text.split())
        assert 60 <= word_count <= 160, f"Word count out of range: {word_count}"


    @test("question: LLM generates valid question JSON for context 0 (resource)")
    def _():
        from pipeline.question_engine import SessionState, load_contexts, generate_question
        session = SessionState(
            seed_text="You notice things. Not dramatically — just quietly.",
            meta_params={"drive": "clarity", "temperament": "measured",
                         "blind_spot": "chaos", "stress_response": "narrow_focus",
                         "social_style": "quiet", "intensity": 3},
        )
        ctx = load_contexts()[0]
        q = generate_question(ctx, session)
        assert q.question_text, "question_text is empty"
        assert len(q.options) >= 3, f"Expected ≥3 options, got {len(q.options)}"
        for opt in q.options:
            assert opt["label"], "option label missing"
            assert opt["delta_key"], "option delta_key missing"


# ---------------------------------------------------------------------------
# Save log
# ---------------------------------------------------------------------------

print("\n=======================================")

passed = sum(1 for r in results if r["status"] == PASS)
failed = sum(1 for r in results if r["status"] == FAIL)
skipped = sum(1 for r in results if r["status"] == SKIP)
total_ms = sum(r["ms"] for r in results)

summary = f"  TOTAL: {len(results)} | PASS: {passed} | FAIL: {failed} | SKIP: {skipped} | {total_ms}ms"
print(summary)
print("=======================================\n")

# Write log
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_path = log_dir / f"test_run_{timestamp}.json"

log_data = {
    "run_at": datetime.now().isoformat(),
    "summary": {"total": len(results), "pass": passed, "fail": failed, "skip": skipped, "total_ms": total_ms},
    "results": results,
}
with open(log_path, "w", encoding="utf-8") as f:
    json.dump(log_data, f, indent=2, ensure_ascii=False)

print(f"  Log saved -> {log_path}\n")

if failed:
    sys.exit(1)
