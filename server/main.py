"""
main.py — FastAPI server for the Agent Initialization Pipeline

Endpoints:
  POST /generate-seed       → generates random seed + stores session
  POST /generate-question   → returns next question for current context
  POST /submit-answer       → applies answer delta, returns updated state
  POST /compile-soul        → compiles SOUL.md + CORE.json, returns result

Session state is stored in-memory (dict keyed by session_id).
For production use, replace with Redis or DB persistence.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Project root (absolute) for .env loading
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env when uvicorn imports this; override=False so env vars (e.g. Railway) win
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

# Pipeline imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.seed_generator import generate_seed, MetaParams
from pipeline.question_engine import (
    SessionState,
    get_context_count,
    get_context_at,
    generate_question,
    process_answer,
    finalize_core,
)
from pipeline.soul_compiler import CompileInput, compile_soul

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(__file__).parent.parent / "agents"
STATIC_DIR = Path(__file__).parent.parent / "static"
DIST_DIR = STATIC_DIR / "dist"

app = FastAPI(title="Island Agent Init", version="1.0.0")


@app.on_event("startup")
def _ensure_env_loaded():
    """Load .env on startup so worker always has OPENROUTER_API_KEY (fixes uvicorn reload)."""
    env_file = _PROJECT_ROOT / ".env"
    if env_file.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except Exception:
            pass
        # Fallback: set OPENROUTER_API_KEY from file if still missing
        if not (os.environ.get("OPENROUTER_API_KEY") or "").strip():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        if k.strip() == "OPENROUTER_API_KEY" and v.strip():
                            os.environ["OPENROUTER_API_KEY"] = v.strip().strip('"\'')
                            break
            except Exception:
                pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: session_id → SessionState dict
_sessions: dict[str, dict[str, Any]] = {}


def get_session(session_id: str) -> SessionState:
    data = _sessions.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionState.from_dict(data)


def save_session(session_id: str, session: SessionState) -> None:
    _sessions[session_id] = session.to_dict()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateSeedRequest(BaseModel):
    model: str = "openai/gpt-4o-mini"


class GenerateSeedResponse(BaseModel):
    session_id: str
    seed_text: str
    meta_params: dict[str, Any]
    total_questions: int


class GenerateQuestionRequest(BaseModel):
    session_id: str
    model: str = "openai/gpt-4o-mini"


class QuestionOption(BaseModel):
    label: str
    delta_key: str


class GenerateQuestionResponse(BaseModel):
    session_id: str
    context_id: str
    context_label: str
    question_number: int
    total_questions: int
    question_text: str
    options: list[QuestionOption]
    is_last: bool


class SubmitAnswerRequest(BaseModel):
    session_id: str
    delta_key: str
    choice_label: str
    free_text: Optional[str] = None


class SubmitAnswerResponse(BaseModel):
    session_id: str
    context_id: str
    core_preview: dict[str, int]
    current_context_index: int
    total_questions: int
    is_complete: bool


class CompileSoulRequest(BaseModel):
    session_id: str
    agent_id: Optional[str] = None
    model: str = "openai/gpt-4o-mini"


class CompileSoulResponse(BaseModel):
    session_id: str
    agent_id: str
    soul_md: str
    core: dict[str, Any]
    output_path: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/generate-seed", response_model=GenerateSeedResponse)
async def api_generate_seed(req: GenerateSeedRequest) -> GenerateSeedResponse:
    """Generate a random personality seed and initialize a session."""
    result = generate_seed(model=req.model)

    session_id = str(uuid.uuid4())
    session = SessionState(
        seed_text=result.seed_text,
        meta_params=result.meta_params.to_dict(),
    )
    save_session(session_id, session)

    return GenerateSeedResponse(
        session_id=session_id,
        seed_text=result.seed_text,
        meta_params=result.meta_params.to_dict(),
        total_questions=get_context_count(),
    )


@app.post("/generate-question", response_model=GenerateQuestionResponse)
async def api_generate_question(req: GenerateQuestionRequest) -> GenerateQuestionResponse:
    """Generate the next question for the current context in the session."""
    session = get_session(req.session_id)
    total = get_context_count()

    if session.current_context_index >= total:
        raise HTTPException(
            status_code=400,
            detail="All questions already answered. Call /compile-soul.",
        )

    context = get_context_at(session.current_context_index)
    if context is None:
        raise HTTPException(status_code=500, detail="Context not found")

    question = generate_question(context, session, model=req.model)

    return GenerateQuestionResponse(
        session_id=req.session_id,
        context_id=context.context_id,
        context_label=context.label,
        question_number=session.current_context_index + 1,
        total_questions=total,
        question_text=question.question_text,
        options=[QuestionOption(**o) for o in question.options],
        is_last=(session.current_context_index == total - 1),
    )


@app.post("/submit-answer", response_model=SubmitAnswerResponse)
async def api_submit_answer(req: SubmitAnswerRequest) -> SubmitAnswerResponse:
    """Submit an answer for the current context question."""
    session = get_session(req.session_id)
    total = get_context_count()

    if session.current_context_index >= total:
        raise HTTPException(status_code=400, detail="No more questions to answer")

    context = get_context_at(session.current_context_index)
    if context is None:
        raise HTTPException(status_code=500, detail="Context not found")

    valid_keys = {slot.delta_key for slot in context.answer_slots}
    if req.delta_key not in valid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid delta_key '{req.delta_key}' for context '{context.context_id}'"
        )

    session = process_answer(
        session=session,
        delta_key=req.delta_key,
        choice_label=req.choice_label,
        free_text=req.free_text,
        context_id=context.context_id,
    )
    save_session(req.session_id, session)

    is_complete = session.current_context_index >= total

    return SubmitAnswerResponse(
        session_id=req.session_id,
        context_id=context.context_id,
        core_preview=session.core.to_dict(),
        current_context_index=session.current_context_index,
        total_questions=total,
        is_complete=is_complete,
    )


@app.post("/compile-soul", response_model=CompileSoulResponse)
async def api_compile_soul(req: CompileSoulRequest) -> CompileSoulResponse:
    """Compile SOUL.md and CORE.json from the completed session."""
    session = get_session(req.session_id)
    total = get_context_count()

    if session.current_context_index < total:
        raise HTTPException(
            status_code=400,
            detail=f"Session incomplete: {session.current_context_index}/{total} questions answered",
        )

    agent_id = req.agent_id or f"agent_{req.session_id[:8]}"
    output_dir = AGENTS_DIR / agent_id

    core_data = finalize_core(session, output_dir, agent_id)

    compile_input = CompileInput(
        agent_id=agent_id,
        seed_text=session.seed_text,
        meta_params=session.meta_params,
        answers=session.answers,
        trait_log=session.trait_log,
        core=session.core.to_dict(),
    )

    soul_md = compile_soul(compile_input, output_dir, model=req.model)

    return CompileSoulResponse(
        session_id=req.session_id,
        agent_id=agent_id,
        soul_md=soul_md,
        core=core_data,
        output_path=str(output_dir),
    )


# ---------------------------------------------------------------------------
# generate-game: seed + 12 dark questions via Grok in one call
# ---------------------------------------------------------------------------

# Model for /generate-game; override in .env as DEFAULT_MODEL if Grok returns 401
GROK_MODEL = os.environ.get("DEFAULT_MODEL", "x-ai/grok-3-mini").strip() or "x-ai/grok-3-mini"
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


class AnswerEffects(BaseModel):
    cooperationBias: int = 0
    deceptionTendency: int = 0
    strategicHorizon: int = 0
    riskAppetite: int = 0


class GameAnswer(BaseModel):
    id: str
    text: str
    effects: AnswerEffects


class GameQuestion(BaseModel):
    id: int
    text: str
    allowCustom: bool = False
    answers: List[GameAnswer]


class GenerateGameRequest(BaseModel):
    model: str = GROK_MODEL


class GenerateGameResponse(BaseModel):
    session_id: str
    seed_text: str
    questions: List[GameQuestion]


def _load_question_prompt_spec() -> str:
    path = SCHEMAS_DIR / "question_generator_prompt.md"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _parse_questions_json(raw: str) -> List[Dict]:
    """Extract and parse JSON array from LLM response, tolerating markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first and last fence lines
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
    # find first [ … ]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in LLM output: {text[:200]}")
    return json.loads(text[start : end + 1])


def _read_openrouter_key_from_env_file() -> str:
    """Read OPENROUTER_API_KEY from .env file (worker may not have it in os.environ)."""
    key = (os.environ.get("OPENROUTER_API_KEY") or "").replace("\ufeff", "").strip().strip("\r\n\t ")
    if key:
        return key
    # Try project root, then cwd (worker may have different cwd)
    for env_path in [_PROJECT_ROOT / ".env", Path.cwd() / ".env"]:
        if not env_path.is_file():
            continue
        try:
            text = env_path.read_text(encoding="utf-8-sig")  # -sig strips BOM
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "OPENROUTER_API_KEY":
                        v = v.strip().strip("\"'").replace("\ufeff", "").strip("\r\n\t ")
                        if v:
                            os.environ["OPENROUTER_API_KEY"] = v
                            return v
        except Exception:
            continue
    raise EnvironmentError("OPENROUTER_API_KEY not set and not found in .env")


@app.post("/generate-game", response_model=GenerateGameResponse)
async def api_generate_game(req: GenerateGameRequest) -> GenerateGameResponse:
    """
    Generate a personality seed + 12 dark atmospheric questions via Grok.
    Returns everything needed for the frontend to run the initialization flow.
    """
    import asyncio
    from pipeline.seed_generator import random_meta_params, call_openrouter
    from pipeline.seed_generator import build_seed_user_prompt, SEED_SYSTEM_PROMPT

    # Read key from .env and pass explicitly (uvicorn reload worker often has no env)
    api_key = _read_openrouter_key_from_env_file()

    try:
        # 1. Generate seed (run sync httpx in thread to avoid blocking event loop)
        meta_params = random_meta_params()
        seed_text = await asyncio.to_thread(
            call_openrouter,
            SEED_SYSTEM_PROMPT,
            build_seed_user_prompt(meta_params),
            req.model,
            0.9,   # temperature
            350,   # max_tokens
            120,   # timeout seconds
            api_key,
        )

        # 2. Load question spec
        spec = _load_question_prompt_spec()

        # 3. Call Grok to generate 12 questions (long call — 4000 tokens, needs more time)
        question_user_prompt = (
            f"Personality seed for this player:\n\n{seed_text}\n\n"
            "Generate exactly 12 questions following the specification above. "
            "Return ONLY the JSON array. No markdown, no commentary."
        )

        raw_questions = await asyncio.to_thread(
            call_openrouter,
            spec,
            question_user_prompt,
            req.model,
            0.92,   # temperature
            4000,   # max_tokens
            180,    # timeout seconds — Grok needs time for 12 questions
            api_key,
        )

        # 4. Parse
        questions_data = _parse_questions_json(raw_questions)

        questions: List[GameQuestion] = []
        for q in questions_data:
            answers = []
            for a in q.get("answers", []):
                effects_raw = a.get("effects", {})
                effects = AnswerEffects(
                    cooperationBias=int(effects_raw.get("cooperationBias", 0)),
                    deceptionTendency=int(effects_raw.get("deceptionTendency", 0)),
                    strategicHorizon=int(effects_raw.get("strategicHorizon", 0)),
                    riskAppetite=int(effects_raw.get("riskAppetite", 0)),
                )
                answers.append(GameAnswer(id=str(a["id"]), text=str(a["text"]), effects=effects))
            questions.append(GameQuestion(
                id=int(q["id"]),
                text=str(q["text"]),
                allowCustom=bool(q.get("allowCustom", False)),
                answers=answers,
            ))

        # 5. Store session
        session_id = str(uuid.uuid4())
        session = SessionState(
            seed_text=seed_text,
            meta_params=meta_params.to_dict(),
        )
        save_session(session_id, session)

        return GenerateGameResponse(
            session_id=session_id,
            seed_text=seed_text,
            questions=questions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Direct params → SOUL.md (for frontend with local questions)
# ---------------------------------------------------------------------------

class CompileFromParamsRequest(BaseModel):
    cooperation_bias: int
    deception_tendency: int
    strategic_horizon: int
    risk_appetite: int
    archetype_name: str = ""
    model: str = GROK_MODEL


class CompileFromParamsResponse(BaseModel):
    agent_id: str
    soul_md: str
    core: dict
    output_path: str


@app.post("/compile-from-params", response_model=CompileFromParamsResponse)
async def api_compile_from_params(req: CompileFromParamsRequest) -> CompileFromParamsResponse:
    """
    Compile SOUL.md directly from CORE parameter values.
    Used by the React frontend which handles questions locally.
    """
    from pipeline.seed_generator import random_meta_params, generate_seed

    agent_id = f"agent_{str(uuid.uuid4())[:8]}"
    output_dir = AGENTS_DIR / agent_id

    seed_result = generate_seed(model=req.model)

    core_values = {
        "cooperation_bias": max(0, min(100, req.cooperation_bias)),
        "deception_tendency": max(0, min(100, req.deception_tendency)),
        "strategic_horizon": max(0, min(100, req.strategic_horizon)),
        "risk_appetite": max(0, min(100, req.risk_appetite)),
    }

    compile_input = CompileInput(
        agent_id=agent_id,
        seed_text=seed_result.seed_text,
        meta_params=seed_result.meta_params.to_dict(),
        answers=[{"context_id": "frontend_questions", "delta_key": "via_ui",
                  "choice_label": f"Archetype: {req.archetype_name}"}],
        trait_log=[req.archetype_name] if req.archetype_name else [],
        core=core_values,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    soul_md = compile_soul(compile_input, output_dir, model=req.model)

    core_data = {
        "version": "1.0.0",
        **core_values,
        "point_buy": {"budget": 100, "spent": 0, "refund": 0, "notes": "Generated via React UI"},
        "meta": {
            "agent_id": agent_id,
            "archetype": req.archetype_name,
            **seed_result.meta_params.to_dict(),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "CORE.json", "w", encoding="utf-8") as f:
        json.dump(core_data, f, indent=2, ensure_ascii=False)

    return CompileFromParamsResponse(
        agent_id=agent_id,
        soul_md=soul_md,
        core=core_data,
        output_path=str(output_dir),
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Static files (UI)
# ---------------------------------------------------------------------------

def _index_path() -> Path:
    return DIST_DIR / "index.html"


@app.get("/")
async def serve_index():
    idx = _index_path()
    if idx.exists():
        return FileResponse(idx)
    return HTMLResponse(
        "<!DOCTYPE html><html><body><h1>Frontend not built</h1>"
        "<p>Run <code>npm run build</code> in frontend/ and deploy again.</p>"
        "<p><a href='/health'>/health</a></p></body></html>",
        status_code=503,
    )


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React SPA for all non-API routes."""
    file_path = DIST_DIR / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    idx = _index_path()
    if idx.exists():
        return FileResponse(idx)
    return PlainTextResponse("Not found", status_code=404)


# Ensure static/dist/assets exists so mount doesn't fail (created by frontend build)
_assets_dir = DIST_DIR / "assets"
_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
