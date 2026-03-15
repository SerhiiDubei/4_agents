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
import logging
from datetime import datetime
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
from pipeline.soul_compiler import CompileInput, compile_soul, compile_from_brief
from pipeline.question_engine import load_contexts

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(__file__).parent.parent / "agents"
STATIC_DIR = Path(__file__).parent.parent / "static"
DIST_DIR = STATIC_DIR / "dist"

app = FastAPI(title="Island Agent Init", version="1.0.0")

logger = logging.getLogger("island")


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

    # Ensure agents root directory always exists
    try:
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Non-fatal: if this fails, individual endpoints will raise on write
        logger.exception("Failed to create AGENTS_DIR at startup")


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
        logger.warning(f"[session] not found session_id={session_id}")
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionState.from_dict(data)


def save_session(session_id: str, session: SessionState) -> None:
    _sessions[session_id] = session.to_dict()


# ---------------------------------------------------------------------------
# Agent storage helpers
# ---------------------------------------------------------------------------

DEFAULT_USER_ID = "local"


def _resolve_user_and_agent(
    *,
    session_id: Optional[str],
    user_id: Optional[str],
    agent_id: Optional[str],
) -> tuple[str, str]:
    """
    Resolve concrete (user_id, agent_id) for an agent.

    - user_id: defaults to DEFAULT_USER_ID when empty
    - agent_id: explicit > session-based > random
    """
    resolved_user = (user_id or "").strip() or DEFAULT_USER_ID
    if agent_id:
        resolved_agent = agent_id
    elif session_id:
        resolved_agent = f"agent_{session_id[:8]}"
    else:
        resolved_agent = f"agent_{str(uuid.uuid4())[:8]}"
    return resolved_user, resolved_agent


def _agent_dir(user_id: str, agent_id: str) -> Path:
    return AGENTS_DIR / user_id / agent_id


def _load_agent_meta(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read agent meta from %s", path)
        return None


def _write_agent_meta(
    *,
    user_id: str,
    agent_id: str,
    session_id: Optional[str],
    archetype_name: str,
    core_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Create or update meta.json for an agent and return the meta dict.
    """
    out_dir = _agent_dir(user_id, agent_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"

    existing = _load_agent_meta(meta_path) or {}
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    created_at = existing.get("created_at") or now

    meta: dict[str, Any] = {
        "agent_id": agent_id,
        "user_id": user_id,
        "session_id": session_id,
        "archetype_name": archetype_name,
        "created_at": created_at,
        "updated_at": now,
        "version": str(core_data.get("version", existing.get("version", "1.0.0"))),
        "archived": bool(existing.get("archived", False)),
        "tags": existing.get("tags") or [],
        "notes": existing.get("notes"),
    }

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return meta


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


class InitQuestionsResponse(BaseModel):
    story: dict[str, Any]  # {year, place, setup, problem, stakes, lines}
    questions: list[dict[str, Any]]  # [{id, label, text}, ...]


class InitCreateCharacterRequest(BaseModel):
    answers: list[str]  # 7 free-text answers
    user_id: Optional[str] = None


class InitCreateCharacterResponse(BaseModel):
    agent_id: str
    soul_md: str
    core: dict[str, Any]
    output_path: str


class CompileFromSessionRequest(BaseModel):
    session_id: str
    cooperation_bias: int
    deception_tendency: int
    strategic_horizon: int
    risk_appetite: int
    archetype_name: str = ""
    model: str = "openai/gpt-4o-mini"
    user_id: Optional[str] = None
    agent_id: Optional[str] = None


class CompileFromSessionResponse(BaseModel):
    session_id: str
    agent_id: str
    soul_md: str
    core: dict
    output_path: str


class AgentMetaResponse(BaseModel):
    agent_id: str
    user_id: str
    session_id: Optional[str] = None
    archetype_name: str = ""
    created_at: str
    updated_at: str
    version: str = "1.0.0"
    archived: bool = False
    tags: list[str] = []
    notes: Optional[str] = None


class AgentSummary(BaseModel):
    agent_id: str
    user_id: str
    archetype_name: str
    created_at: str
    updated_at: str
    archived: bool = False


class AgentDetailResponse(BaseModel):
    meta: AgentMetaResponse
    core: dict
    soul_md: str


class AgentListResponse(BaseModel):
    user_id: str
    agents: list[AgentSummary]


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

    # Legacy endpoint: use default user namespace
    user_id, agent_id = _resolve_user_and_agent(
        session_id=req.session_id,
        user_id=None,
        agent_id=req.agent_id,
    )
    output_dir = _agent_dir(user_id, agent_id)

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

    _write_agent_meta(
        user_id=user_id,
        agent_id=agent_id,
        session_id=req.session_id,
        archetype_name="",
        core_data=core_data,
    )

    return CompileSoulResponse(
        session_id=req.session_id,
        agent_id=agent_id,
        soul_md=soul_md,
        core=core_data,
        output_path=str(output_dir),
    )


# ---------------------------------------------------------------------------
# Open init flow: 7 questions, free-text only, compile_from_brief
# ---------------------------------------------------------------------------

# Ukrainian translations for question contexts (scenario_hint)
_INIT_QUESTIONS_UK = [
    "Ресурси обмежені — їжа, інструменти, притулок. Не всі можуть отримати рівну частку. Тобі доведеться вирішити, як діяти.",
    "Хтось із присутніх рано підходить до тебе і пропонує поділитися інформацією. Ти їх ще не знаєш. Не знаєш, чи це щиро.",
    "Хтось дав тобі обіцянку і не виконав її. Це коштувало тобі чогось реального. Вони навіть не визнали цього.",
    "Ти дізнався щось важливе, чого інші не знають. Ця інформація може суттєво змінити баланс у групі.",
    "Справи йдуть погано. Ти в невигідному становищі, ситуація затягується. Інші спостерігають, як ти реагуєш.",
    "Хтось пропонує формальний союз — ви тримаєтесь разом заради взаємної вигоди. Це спокусливо, але означає залежність від іншого.",
    "У тебе є доказ, що хтось обманював групу. Ти можеш діяти — або ні. Ніхто інший про це не знає.",
]

_INIT_QUESTIONS_LABELS_UK = [
    "Ресурси",
    "Перший контакт",
    "Зрада",
    "Приховане знання",
    "Під тиском",
    "Пропозиція союзу",
    "Момент правди",
]


def _build_init_story() -> dict[str, Any]:
    """Generate full story context for init — рік, місце, завязка, проблема, narrative lines."""
    import random
    try:
        from storytell import generate_story
        seed = random.randint(0, 2**31 - 1)
        sp = generate_story(seed)
        setup_line = (sp.setup[0].upper() + sp.setup[1:] + ".") if sp.setup else ""
        problem_line = (sp.problem[0].upper() + sp.problem[1:] + ".") if sp.problem else ""
        lines = [
            f"{sp.year}. {sp.place}.",
            "",
            setup_line,
            problem_line,
            f"Ролі: {', '.join(sp.characters)}." if sp.characters else "",
            f"На кону: {sp.stakes}." if sp.stakes else "На кону — виживання і довіра.",
            "",
            "Ти — один із них. Твої рішення формують тебе.",
            "Сім ситуацій. Сім виборів. Відповідай вільно — без готових варіантів.",
        ]
        lines = [l for l in lines if l.strip()]
        return {
            "year": sp.year,
            "place": sp.place,
            "setup": sp.setup,
            "problem": sp.problem,
            "stakes": sp.stakes or "виживання",
            "characters": sp.characters,
            "lines": lines,
        }
    except Exception:
        return {
            "year": "сучасність",
            "place": "закритий простір",
            "setup": "Ви опинилися разом з іншими. Ресурси обмежені.",
            "problem": "Довіра під питанням. Кожен вибір має наслідки.",
            "stakes": "виживання",
            "characters": [],
            "lines": [
                "Сучасність. Закритий простір.",
                "Ви опинилися разом з іншими. Ресурси обмежені. Довіра під питанням.",
                "Кожен вибір має наслідки. Ти — один із них.",
                "",
                "Сім ситуацій. Сім виборів. Відповідай вільно — без готових варіантів.",
            ],
        }


@app.post("/init-questions", response_model=InitQuestionsResponse)
async def api_init_questions() -> InitQuestionsResponse:
    """Return full story + 7 open questions for the init flow."""
    story = _build_init_story()
    contexts = load_contexts()
    questions = []
    for i, ctx in enumerate(contexts):
        text = _INIT_QUESTIONS_UK[i] if i < len(_INIT_QUESTIONS_UK) else ctx.scenario_hint
        label = _INIT_QUESTIONS_LABELS_UK[i] if i < len(_INIT_QUESTIONS_LABELS_UK) else ctx.label
        questions.append({"id": i + 1, "label": label, "text": text})
    return InitQuestionsResponse(story=story, questions=questions)


@app.post("/init-create-character", response_model=InitCreateCharacterResponse)
async def api_init_create_character(req: InitCreateCharacterRequest) -> InitCreateCharacterResponse:
    """Create a new character from 7 free-text answers using compile_from_brief."""
    if len(req.answers) != 7:
        raise HTTPException(
            status_code=422,
            detail="Exactly 7 answers required",
        )

    agent_id = f"agent_{uuid.uuid4().hex[:12]}"
    # Save to agents/{agent_id}/ for roster/game compatibility (no user_id in path)
    output_dir = AGENTS_DIR / agent_id

    try:
        from pipeline.seed_generator import generate_seed

        seed_result = generate_seed(model="openai/gpt-4o-mini")
        result = compile_from_brief(
            agent_id=agent_id,
            brief=req.answers,
            seed_text=seed_result.seed_text,
            meta_params=seed_result.meta_params.to_dict(),
            output_dir=output_dir,
            model="openai/gpt-4o-mini",
        )
    except Exception as e:
        logger.exception("init-create-character failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Extract name from SOUL first line
    name = "Новий персонаж"
    if result.get("soul_md"):
        first_line = result["soul_md"].split("\n")[0].strip()
        if first_line and len(first_line) < 50:
            name = first_line.replace("You ", "").replace("Ти ", "").strip()[:40] or name

    # Add name to CORE.json
    core_path = output_dir / "CORE.json"
    if core_path.exists():
        core_data = json.loads(core_path.read_text(encoding="utf-8"))
        core_data["name"] = name
        core_path.write_text(json.dumps(core_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Add to roster.json
    roster_path = AGENTS_DIR / "roster.json"
    roster = {"version": "1.0", "description": "Реєстр персонажів.", "agents": [], "default_count": 4, "min_participants": 2, "max_participants": 8}
    if roster_path.exists():
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    new_agent = {
        "id": agent_id,
        "name": name,
        "type": "real",
        "source": f"agents/{agent_id}",
        "profile": {"connections": "", "profession": "", "bio": ""},
    }
    roster.setdefault("agents", [])
    roster["agents"].append(new_agent)
    roster_path.write_text(json.dumps(roster, indent=2, ensure_ascii=False), encoding="utf-8")

    return InitCreateCharacterResponse(
        agent_id=agent_id,
        soul_md=result.get("soul_md", ""),
        core=result.get("core", {}),
        output_path=str(output_dir),
    )


@app.post("/compile-from-session", response_model=CompileFromSessionResponse)
async def api_compile_from_session(req: CompileFromSessionRequest) -> CompileFromSessionResponse:
    """
    Compile SOUL.md directly from the completed session, using final CORE values from the frontend.
    This ensures the same seed + meta_params + answers are used as during the question phase.
    """
    session = get_session(req.session_id)

    user_id, agent_id = _resolve_user_and_agent(
        session_id=req.session_id,
        user_id=req.user_id,
        agent_id=req.agent_id,
    )
    output_dir = _agent_dir(user_id, agent_id)

    core_values = {
        "cooperation_bias": max(0, min(100, req.cooperation_bias)),
        "deception_tendency": max(0, min(100, req.deception_tendency)),
        "strategic_horizon": max(0, min(100, req.strategic_horizon)),
        "risk_appetite": max(0, min(100, req.risk_appetite)),
    }

    compile_input = CompileInput(
        agent_id=agent_id,
        seed_text=session.seed_text,
        meta_params=session.meta_params,
        answers=session.answers,
        trait_log=session.trait_log,
        core=core_values,
    )

    soul_md = compile_soul(compile_input, output_dir, model=req.model)

    core_data = {
        "version": "1.0.0",
        **core_values,
        "point_buy": {"budget": 100, "spent": 0, "refund": 0, "notes": "Generated via React UI"},
        "meta": {
            "agent_id": agent_id,
            "user_id": user_id,
            "archetype": req.archetype_name,
            **session.meta_params,
        },
    }
    with open(output_dir / "CORE.json", "w", encoding="utf-8") as f:
        json.dump(core_data, f, indent=2, ensure_ascii=False)

    _write_agent_meta(
        user_id=user_id,
        agent_id=agent_id,
        session_id=req.session_id,
        archetype_name=req.archetype_name,
        core_data=core_data,
    )

    logger.info(
        "[compile-from-session] ok user_id=%s session_id=%s agent_id=%s core=%s",
        user_id,
        req.session_id,
        agent_id,
        core_values,
    )

    return CompileFromSessionResponse(
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
    """Extract and parse JSON array from LLM response, tolerating markdown fences and minor JSON quirks."""
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
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in LLM output: {text[:200]}")
    json_str = text[start : end + 1]
    # Fix common LLM JSON mistakes: trailing commas before ] or }
    import re
    json_str = re.sub(r",\s*]", "]", json_str)
    json_str = re.sub(r",\s*}", "}", json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM at line {e.lineno} col {e.colno}: {e.msg}. Snippet: {json_str[max(0,e.pos-50):e.pos+50]!r}")


def _read_openrouter_key_from_env_file() -> tuple[str, str]:
    """
    Read OPENROUTER_API_KEY. Used by /generate-game when you press Start.
    Key is taken from: 1) process env (e.g. Railway Variables), 2) .env file in project root.
    Returns (key, source) where source is "env" or "file".
    """
    key = (os.environ.get("OPENROUTER_API_KEY") or "").replace("\ufeff", "").strip().strip("\r\n\t ")
    if key:
        return key, "env"
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
                            return v, "file"
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

    # Key for OpenRouter: from env (Railway Variables) or from .env file — passed into call_openrouter below
    api_key, key_source = _read_openrouter_key_from_env_file()
    print(f"[generate-game] OPENROUTER_API_KEY from {key_source}, len={len(api_key)}")

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

        response = GenerateGameResponse(
            session_id=session_id,
            seed_text=seed_text,
            questions=questions,
        )
        # Simple structured log for successful game generation (useful for Railway logs)
        print(
            f"[generate-game] ok session_id={session_id} "
            f"questions={len(questions)} model={req.model}"
        )
        return response
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
    user_id: Optional[str] = None
    agent_id: Optional[str] = None


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

    user_id, agent_id = _resolve_user_and_agent(
        session_id=None,
        user_id=req.user_id,
        agent_id=req.agent_id,
    )
    output_dir = _agent_dir(user_id, agent_id)

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

    soul_md = compile_soul(compile_input, output_dir, model=req.model)

    core_data = {
        "version": "1.0.0",
        **core_values,
        "point_buy": {"budget": 100, "spent": 0, "refund": 0, "notes": "Generated via React UI"},
        "meta": {
            "agent_id": agent_id,
            "user_id": user_id,
            "archetype": req.archetype_name,
            **seed_result.meta_params.to_dict(),
        },
    }
    with open(output_dir / "CORE.json", "w", encoding="utf-8") as f:
        json.dump(core_data, f, indent=2, ensure_ascii=False)

    _write_agent_meta(
        user_id=user_id,
        agent_id=agent_id,
        session_id=None,
        archetype_name=req.archetype_name,
        core_data=core_data,
    )

    return CompileFromParamsResponse(
        agent_id=agent_id,
        soul_md=soul_md,
        core=core_data,
        output_path=str(output_dir),
    )


@app.post("/agents/from-session", response_model=AgentDetailResponse)
async def api_agents_from_session(req: CompileFromSessionRequest) -> AgentDetailResponse:
    """
    High-level endpoint: create or update an agent from a completed session.
    Wraps /compile-from-session and returns structured agent detail.
    """
    result = await api_compile_from_session(req)

    user_id, agent_id = _resolve_user_and_agent(
        session_id=req.session_id,
        user_id=req.user_id,
        agent_id=req.agent_id or result.agent_id,
    )
    out_dir = _agent_dir(user_id, agent_id)

    soul_path = out_dir / "SOUL.md"
    try:
        soul_text = soul_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        soul_text = result.soul_md

    meta_raw = _load_agent_meta(out_dir / "meta.json") or {}
    meta = AgentMetaResponse(
        agent_id=meta_raw.get("agent_id", agent_id),
        user_id=meta_raw.get("user_id", user_id),
        session_id=meta_raw.get("session_id", req.session_id),
        archetype_name=meta_raw.get("archetype_name", req.archetype_name),
        created_at=meta_raw.get("created_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        updated_at=meta_raw.get("updated_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        version=meta_raw.get("version", str(result.core.get("version", "1.0.0"))),
        archived=bool(meta_raw.get("archived", False)),
        tags=list(meta_raw.get("tags") or []),
        notes=meta_raw.get("notes"),
    )

    return AgentDetailResponse(meta=meta, core=result.core, soul_md=soul_text)


@app.post("/agents/from-core", response_model=AgentDetailResponse)
async def api_agents_from_core(req: CompileFromParamsRequest) -> AgentDetailResponse:
    """
    High-level endpoint: create an agent directly from CORE parameters.
    Wraps /compile-from-params and returns structured agent detail.
    """
    result = await api_compile_from_params(req)

    user_id, agent_id = _resolve_user_and_agent(
        session_id=None,
        user_id=req.user_id,
        agent_id=req.agent_id or result.agent_id,
    )
    out_dir = _agent_dir(user_id, agent_id)

    soul_path = out_dir / "SOUL.md"
    try:
        soul_text = soul_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        soul_text = result.soul_md

    meta_raw = _load_agent_meta(out_dir / "meta.json") or {}
    meta = AgentMetaResponse(
        agent_id=meta_raw.get("agent_id", agent_id),
        user_id=meta_raw.get("user_id", user_id),
        session_id=meta_raw.get("session_id"),
        archetype_name=meta_raw.get("archetype_name", req.archetype_name),
        created_at=meta_raw.get("created_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        updated_at=meta_raw.get("updated_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        version=meta_raw.get("version", str(result.core.get("version", "1.0.0"))),
        archived=bool(meta_raw.get("archived", False)),
        tags=list(meta_raw.get("tags") or []),
        notes=meta_raw.get("notes"),
    )

    return AgentDetailResponse(meta=meta, core=result.core, soul_md=soul_text)


@app.get("/agents/{user_id}", response_model=AgentListResponse)
async def api_list_agents(user_id: str) -> AgentListResponse:
    """
    List all agents for a given user_id based on meta.json files.
    """
    base = AGENTS_DIR / user_id
    agents: list[AgentSummary] = []

    if base.is_dir():
        for child in base.iterdir():
            if not child.is_dir():
                continue
            meta_raw = _load_agent_meta(child / "meta.json")
            if not meta_raw:
                continue
            agents.append(
                AgentSummary(
                    agent_id=str(meta_raw.get("agent_id", child.name)),
                    user_id=str(meta_raw.get("user_id", user_id)),
                    archetype_name=str(meta_raw.get("archetype_name", "")),
                    created_at=str(meta_raw.get("created_at", "")),
                    updated_at=str(meta_raw.get("updated_at", "")),
                    archived=bool(meta_raw.get("archived", False)),
                )
            )

    return AgentListResponse(user_id=user_id, agents=agents)


@app.get("/agents/{user_id}/{agent_id}", response_model=AgentDetailResponse)
async def api_get_agent(user_id: str, agent_id: str) -> AgentDetailResponse:
    """
    Return full agent detail (meta + CORE + SOUL.md) for a given user/agent.
    """
    dir_path = _agent_dir(user_id, agent_id)
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Agent not found")

    meta_raw = _load_agent_meta(dir_path / "meta.json") or {}
    core_path = dir_path / "CORE.json"
    soul_path = dir_path / "SOUL.md"

    try:
        with core_path.open(encoding="utf-8") as f:
            core_data = json.load(f)
    except FileNotFoundError:
        core_data = {}

    try:
        soul_text = soul_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        soul_text = ""

    if not meta_raw:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        meta_raw = {
            "agent_id": agent_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "version": str(core_data.get("version", "1.0.0")),
            "archived": False,
            "tags": [],
            "notes": None,
        }

    meta = AgentMetaResponse(
        agent_id=str(meta_raw.get("agent_id", agent_id)),
        user_id=str(meta_raw.get("user_id", user_id)),
        session_id=meta_raw.get("session_id"),
        archetype_name=str(meta_raw.get("archetype_name", "")),
        created_at=str(meta_raw.get("created_at", "")),
        updated_at=str(meta_raw.get("updated_at", "")),
        version=str(meta_raw.get("version", "1.0.0")),
        archived=bool(meta_raw.get("archived", False)),
        tags=list(meta_raw.get("tags") or []),
        notes=meta_raw.get("notes"),
    )

    return AgentDetailResponse(meta=meta, core=core_data, soul_md=soul_text)


# ---------------------------------------------------------------------------
# Simulation endpoints
# ---------------------------------------------------------------------------

class StartSimulationRequest(BaseModel):
    agent_ids: List[str]
    total_rounds: int = 10
    use_dialog: bool = False   # False by default — faster, no LLM cost
    model: str = GROK_MODEL
    reveal_requests: Optional[Dict[str, str]] = None  # {round_str: {revealer: target}}


class StartSimulationResponse(BaseModel):
    simulation_id: str
    agent_ids: List[str]
    winner: str
    final_scores: Dict[str, Any]
    rounds_played: int
    result: Dict[str, Any]


@app.post("/start-simulation", response_model=StartSimulationResponse)
async def api_start_simulation(req: StartSimulationRequest) -> StartSimulationResponse:
    """
    Run the full Island simulation for a set of initialized agents.
    Agent directories must exist under /agents/<id>/ with CORE.json and SOUL.md.
    """
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from simulation.game_engine import load_agents_from_disk, run_simulation
    from pipeline.state_machine import save_states
    from pipeline.memory import save_memory

    # Parse reveal_requests: {round_str: {revealer: target}} → {int: {str: str}}
    reveal_requests = None
    if req.reveal_requests:
        reveal_requests = {int(k): v for k, v in req.reveal_requests.items()}

    def _run():
        agents = load_agents_from_disk(req.agent_ids, AGENTS_DIR)
        result = run_simulation(
            agents=agents,
            total_rounds=req.total_rounds,
            model=req.model,
            use_dialog=req.use_dialog,
            reveal_requests=reveal_requests,
        )
        # Persist updated states and memories
        for agent in agents:
            agent_dir = AGENTS_DIR / agent.agent_id
            save_states(agent.states, agent_dir)
            save_memory(agent.memory, agent_dir)
        return result

    result = await asyncio.to_thread(_run)
    result_dict = result.to_dict()

    return StartSimulationResponse(
        simulation_id=result.simulation_id,
        agent_ids=result.agent_ids,
        winner=result.winner or "",
        final_scores=result.final_scores,
        rounds_played=len(result.rounds),
        result=result_dict,
    )


class SimulationStateResponse(BaseModel):
    agent_ids: List[str]
    states: Dict[str, Any]
    memories: Dict[str, Any]
    scores: Dict[str, float]


@app.get("/simulation/{agent_id}/state")
async def api_agent_state(agent_id: str) -> Dict[str, Any]:
    """Get current STATES.md and MEMORY summary for one agent."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pipeline.state_machine import load_states
    from pipeline.memory import load_memory

    agent_dir = AGENTS_DIR / agent_id
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    states = load_states(agent_dir)
    memory = load_memory(agent_dir)

    return {
        "agent_id": agent_id,
        "states": states.to_dict(),
        "memory_summary": memory.summary(),
        "rounds_played": len(memory.rounds),
        "total_score": memory.total_score,
    }


@app.get("/agents")
async def api_list_agents() -> Dict[str, Any]:
    """List all initialized agents."""
    agents = []
    if AGENTS_DIR.exists():
        for agent_dir in sorted(AGENTS_DIR.iterdir()):
            if agent_dir.is_dir():
                core_path = agent_dir / "CORE.json"
                soul_path = agent_dir / "SOUL.md"
                agents.append({
                    "agent_id": agent_dir.name,
                    "has_core": core_path.exists(),
                    "has_soul": soul_path.exists(),
                    "has_states": (agent_dir / "STATES.md").exists(),
                    "has_memory": (agent_dir / "MEMORY.json").exists(),
                })
    return {"agents": agents, "count": len(agents)}


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
