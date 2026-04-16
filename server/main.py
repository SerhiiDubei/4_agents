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
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

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

# Структурований logging
from config.logging_config import setup_logging
setup_logging()

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

# ---------------------------------------------------------------------------
# DB + Auth setup
# ---------------------------------------------------------------------------
from db.database import init_db, get_db, SessionLocal
from db.models import User, GameSession
from db.auth import hash_password, verify_password, create_access_token, decode_token
from sqlalchemy.orm import Session as DbSession
import uuid as _uuid_mod

_http_bearer = HTTPBearer(auto_error=False)


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: DbSession = Depends(get_db),
) -> Optional[User]:
    """Returns current User or None (endpoints that accept optional auth)."""
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    return user


def _require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: DbSession = Depends(get_db),
) -> User:
    """Like _get_current_user but raises 401 if not authenticated."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@app.on_event("startup")
def _ensure_env_loaded():
    """Load .env on startup and initialize DB."""
    init_db()
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


_cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


import collections as _collections
import threading as _threading
import time as _time
_auth_rate: dict[str, list] = _collections.defaultdict(list)
_auth_rate_lock = _threading.Lock()

def _auth_rate_limit(key: str, max_calls: int = 5, window: float = 60.0) -> bool:
    now = _time.time()
    with _auth_rate_lock:
        _auth_rate[key] = [t for t in _auth_rate[key] if now - t < window]
        if len(_auth_rate[key]) >= max_calls:
            return False
        _auth_rate[key].append(now)
        return True

from fastapi import Request as _Request

@app.post("/auth/register", response_model=TokenResponse, tags=["auth"])
def auth_register(body: RegisterRequest, request: _Request, db: DbSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not _auth_rate_limit(f"register:{ip}"):
        raise HTTPException(status_code=429, detail="Too many registration attempts")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        id=str(_uuid_mod.uuid4()),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def auth_login(body: LoginRequest, request: _Request, db: DbSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not _auth_rate_limit(f"login:{ip}", max_calls=10):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@app.get("/auth/me", tags=["auth"])
def auth_me(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: DbSession = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user.id, "username": user.username, "email": user.email, "created_at": user.created_at}


@app.get("/api/my-games", tags=["auth"])
def my_games(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: DbSession = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    sessions = (
        db.query(GameSession)
        .filter(GameSession.human_player_id == payload.get("sub"))
        .order_by(GameSession.started_at.desc())
        .limit(50)
        .all()
    )
    return {"games": [
        {
            "session_id": s.session_id,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "winner_id": s.winner_id,
            "rounds": s.rounds,
            "report_path": s.report_path,
        }
        for s in sessions
    ]}


# In-memory session store: session_id → SessionState dict
_sessions: dict[str, dict[str, Any]] = {}
_session_timestamps: dict[str, float] = {}
_SESSION_TTL_SECONDS = 4 * 3600  # 4 hours


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than _SESSION_TTL_SECONDS."""
    now = _time.time()
    expired = [sid for sid, ts in list(_session_timestamps.items()) if now - ts > _SESSION_TTL_SECONDS]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_timestamps.pop(sid, None)
    if expired:
        logger.info(f"[session] cleaned up {len(expired)} expired sessions")


def get_session(session_id: str) -> SessionState:
    _cleanup_expired_sessions()
    data = _sessions.get(session_id)
    if not data:
        logger.warning(f"[session] not found session_id={session_id}")
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionState.from_dict(data)


def save_session(session_id: str, session: SessionState) -> None:
    _sessions[session_id] = session.to_dict()
    _session_timestamps[session_id] = _time.time()


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
async def api_generate_seed(req: GenerateSeedRequest, request: _Request) -> GenerateSeedResponse:
    """Generate a random personality seed and initialize a session."""
    ip = request.client.host if request.client else "unknown"
    if not _auth_rate_limit(f"llm:{ip}", max_calls=30, window=60.0):
        raise HTTPException(status_code=429, detail="Too many requests")
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
async def api_generate_question(req: GenerateQuestionRequest, request: _Request) -> GenerateQuestionResponse:
    """Generate the next question for the current context in the session."""
    ip = request.client.host if request.client else "unknown"
    if not _auth_rate_limit(f"llm:{ip}", max_calls=30, window=60.0):
        raise HTTPException(status_code=429, detail="Too many requests")
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
async def api_compile_soul(req: CompileSoulRequest, request: _Request) -> CompileSoulResponse:
    """Compile SOUL.md and CORE.json from the completed session."""
    ip = request.client.host if request.client else "unknown"
    if not _auth_rate_limit(f"llm:{ip}", max_calls=10, window=60.0):
        raise HTTPException(status_code=429, detail="Too many requests")
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


_NUMERIC_EFFECT_KEYS = {
    "cooperationBias",
    "deceptionTendency",
    "strategicHorizon",
    "riskAppetite",
}


def _coerce_effects(effects_raw: Dict[str, Any]) -> Dict[str, int]:
    """
    Normalize effects from LLM JSON into a dict of ints.
    Handles numbers, strings like \"+10\" / \" 5 \" and falls back to 0 on errors.
    """
    coerced: Dict[str, int] = {}
    for key in _NUMERIC_EFFECT_KEYS:
        value = effects_raw.get(key, 0)
        num: float
        if isinstance(value, (int, float)):
            num = float(value)
        elif isinstance(value, str):
            s = value.strip()
            if s.startswith("+"):
                s = s[1:]
            try:
                num = float(s)
            except ValueError:
                num = 0.0
        else:
            num = 0.0
        # Clamp to a reasonable range to avoid extreme outliers from the model
        clamped = max(-100.0, min(100.0, num))
        coerced[key] = int(round(clamped))
    return coerced


def _load_question_prompt_spec() -> str:
    path = SCHEMAS_DIR / "question_generator_prompt.md"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sanitize_llm_json(raw: str) -> str:
    """
    Extract the JSON array from the LLM response and normalize common quirks
    so that json.loads can consume it safely.
    """
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
    # Fix common LLM JSON mistakes: trailing commas before ] or }; unary + in numbers
    import re
    json_str = re.sub(r",\s*]", "]", json_str)
    json_str = re.sub(r",\s*}", "}", json_str)
    # Map `: +10` / `: + 10` / `: +\n10` to valid JSON numbers (allow whitespace between + and number)
    json_str = re.sub(r"(:\s*)\+\s*(\d+(?:\.\d+)?)", r"\1\2", json_str)
    return json_str


def _parse_questions_json(raw: str) -> List[Dict]:
    """Extract and parse JSON array from LLM response, tolerating markdown fences and minor JSON quirks."""
    json_str = _sanitize_llm_json(raw)
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
    logger.info("OPENROUTER_API_KEY from %s, len=%d", key_source, len(api_key))

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

        # 4. Parse and normalize effects
        questions_data = _parse_questions_json(raw_questions)

        questions: List[GameQuestion] = []
        for q in questions_data:
            answers: List[GameAnswer] = []
            for a in q.get("answers", []):
                effects_raw = a.get("effects", {}) or {}
                effects_coerced = _coerce_effects(effects_raw)
                effects = AnswerEffects(
                    cooperationBias=effects_coerced["cooperationBias"],
                    deceptionTendency=effects_coerced["deceptionTendency"],
                    strategicHorizon=effects_coerced["strategicHorizon"],
                    riskAppetite=effects_coerced["riskAppetite"],
                )
                answers.append(
                    GameAnswer(
                        id=str(a["id"]),
                        text=str(a["text"]),
                        effects=effects,
                    )
                )
            questions.append(
                GameQuestion(
                    id=int(q["id"]),
                    text=str(q["text"]),
                    allowCustom=bool(q.get("allowCustom", False)),
                    answers=answers,
                )
            )

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
        logger.info("generate-game ok session_id=%s questions=%d model=%s", session_id, len(questions), req.model)
        return response
    except Exception as e:
        detail = str(e) or "Internal server error"
        status_code = 500
        if isinstance(e, ValueError) and detail.startswith("Invalid JSON from LLM"):
            logger.error("generate-game JSON parse error from LLM: %s", detail)
            detail = "Модель повернула некоректні дані. Спробуйте ще раз або змініть налаштування."
            status_code = 502
        raise HTTPException(status_code=status_code, detail=detail)


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
    export_html: bool = True   # Export HTML report to logs/ and return reportPath


class StartSimulationResponse(BaseModel):
    simulation_id: str
    agent_ids: List[str]
    winner: str
    final_scores: Dict[str, Any]
    rounds_played: int
    result: Dict[str, Any]
    report_path: Optional[str] = None  # /logs/game_xxx.html when export_html=True


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
            save_states(agent.states, agent_dir, display_name=agent.name)
            save_memory(agent.memory, agent_dir)

        report_path = None
        if req.export_html and LOGS_DIR:
            from export_game_log import export_to_html

            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            extended_log = result.to_dict()
            extended_log["score_range"] = result.score_range()

            agent_reflections = {a.agent_id: [] for a in agents}
            agent_reasonings = {a.agent_id: [] for a in agents}
            for rr in result.rounds:
                for aid in agent_reflections:
                    note = rr.notes.get(aid, "")
                    if note:
                        agent_reflections[aid].append({"round": rr.round_number, "notes": note})
                    reasoning = rr.reasonings.get(aid)
                    if reasoning:
                        agent_reasonings[aid].append({"round": rr.round_number, "reasoning": reasoning})
            extended_log["agent_reflections"] = agent_reflections
            extended_log["agent_reasonings"] = agent_reasonings

            extended_log["game_conclusions"] = {}
            for a in agents:
                if a.memory.game_history:
                    last = a.memory.game_history[-1]
                    if last.get("conclusion"):
                        extended_log["game_conclusions"][a.agent_id] = last["conclusion"]

            roster_path = AGENTS_DIR / "roster.json"
            agent_profiles = {}
            if roster_path.exists():
                roster = json.loads(roster_path.read_text(encoding="utf-8"))
                for a in roster.get("agents", []):
                    aid = a.get("id")
                    if aid in result.agent_ids and a.get("profile"):
                        agent_profiles[aid] = dict(a["profile"])
            for aid in list(agent_profiles.keys()):
                bio_path = AGENTS_DIR / aid / "BIO.md"
                if bio_path.exists():
                    agent_profiles[aid]["bio"] = bio_path.read_text(encoding="utf-8").strip()
            extended_log["agent_profiles"] = agent_profiles

            html_name = f"game_{result.simulation_id}.html"
            html_path = LOGS_DIR / html_name
            export_to_html(extended_log, output_path=html_path)
            report_path = f"/logs/{html_name}"

        return result, report_path

    result, report_path = await asyncio.to_thread(_run)
    result_dict = result.to_dict()

    return StartSimulationResponse(
        simulation_id=result.simulation_id,
        agent_ids=result.agent_ids,
        winner=result.winner or "",
        final_scores=result.final_scores,
        rounds_played=len(result.rounds),
        result=result_dict,
        report_path=report_path,
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
# Roster profiles — для Agent Profiles UI (M4)
# ---------------------------------------------------------------------------

_ROLE_LABELS: dict[str, str] = {
    "role_snake":       "Змія",
    "role_gambler":     "Гравець",
    "role_banker":      "Банкір",
    "role_peacekeeper": "Миротворець",
}

_ROLE_COLORS: dict[str, str] = {
    "role_snake":       "red",
    "role_gambler":     "pink",
    "role_banker":      "cyan",
    "role_peacekeeper": "gold",
}

# Копія ROLE_CORE_OVERLAYS щоб не залежати від simulation import у server
_ROLE_OVERLAYS: dict[str, dict[str, int]] = {
    "role_snake":       {"cooperation_bias": -25, "deception_tendency": 30, "risk_appetite": 15},
    "role_gambler":     {"cooperation_bias": -30, "deception_tendency": 35, "risk_appetite": 30},
    "role_banker":      {"cooperation_bias": 20, "deception_tendency": -10},
    "role_peacekeeper": {"cooperation_bias": 25, "deception_tendency": -25, "risk_appetite": -10},
}


@app.get("/api/roster/profiles")
async def roster_profiles() -> dict[str, Any]:
    """Повертає всіх агентів з roster.json з CORE-параметрами та bio-витягом.
    Використовується в Agent Profiles UI (M4 ВИС-15)."""
    roster_path = _PROJECT_ROOT / "agents" / "roster.json"
    if not roster_path.exists():
        return {"profiles": []}

    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    except Exception:
        return {"profiles": []}

    profiles: list[dict[str, Any]] = []
    for entry in roster.get("agents", []):
        agent_id = entry.get("id") or entry.get("source", "").split("/")[-1]
        if not agent_id:
            continue

        agent_dir = _PROJECT_ROOT / "agents" / agent_id

        # Завантажуємо CORE.json
        core: dict[str, Any] = {}
        core_path = agent_dir / "CORE.json"
        if core_path.exists():
            try:
                core = json.loads(core_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        role = core.get("role") or entry.get("role") or "role_peacekeeper"
        overlay = _ROLE_OVERLAYS.get(role, {})

        # Застосовуємо role overlay до CORE параметрів (clamp 0-100)
        def apply(param: str) -> int:
            base = int(core.get(param, 50))
            delta = overlay.get(param, 0)
            return max(0, min(100, base + delta))

        # Bio-витяг з BIO.md (перший абзац, до 350 символів)
        bio_excerpt = ""
        bio_path = agent_dir / "BIO.md"
        if bio_path.exists():
            try:
                bio_text = bio_path.read_text(encoding="utf-8").strip()
                # Шукаємо перший абзац з текстом (пропускаємо заголовки ##)
                for line in bio_text.split("\n"):
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        bio_excerpt = stripped[:350]
                        break
            except Exception:
                pass

        profiles.append({
            "id": agent_id,
            "name": core.get("name") or entry.get("name") or agent_id,
            "role": role,
            "roleLabel": _ROLE_LABELS.get(role, role),
            "roleColor": _ROLE_COLORS.get(role, "cyan"),
            "core": {
                "cooperation_bias":   apply("cooperation_bias"),
                "deception_tendency": apply("deception_tendency"),
                "strategic_horizon":  apply("strategic_horizon"),
                "risk_appetite":      apply("risk_appetite"),
            },
            "profession": entry.get("profile", {}).get("profession") or "",
            "bio":        entry.get("profile", {}).get("bio") or bio_excerpt,
            "connections": entry.get("profile", {}).get("connections") or "",
        })

    return {"profiles": profiles, "count": len(profiles)}


# ---------------------------------------------------------------------------
# Games summary (for UI results table)
# ---------------------------------------------------------------------------

LOGS_DIR = _PROJECT_ROOT / "logs" / "island"

_GAMES_SUMMARY_PATTERN = re.compile(r"game_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_game_(\d+)\.json")
_GAMES_CUSTOM_PATTERN = re.compile(r"game_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_(.+)\.json")
_GAMES_BARE_PATTERN = re.compile(r"game_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.json")


def _match_island_game(path: Path) -> re.Match | None:
    """Match game_*.json: game_DATE_TIME_game_N.json, game_DATE_TIME_customname.json, or bare game_DATE_TIME.json."""
    m = _GAMES_SUMMARY_PATTERN.match(path.name)
    if m:
        return m
    m = _GAMES_CUSTOM_PATTERN.match(path.name)  # e.g. jesus_6players
    if m:
        return m
    return _GAMES_BARE_PATTERN.match(path.name)  # legacy: game_2026-03-15_21-09-54.json


def _island_game_sort_key(path: Path, m: re.Match) -> tuple:
    """Sort by (date, time, game_num or 0 for custom)."""
    date_str, time_str = m.group(1), m.group(2)
    if len(m.groups()) >= 3 and m.group(3).isdigit():
        return (date_str, time_str, int(m.group(3)))
    return (date_str, time_str, 0)


@app.get("/api/games-count")
async def games_count() -> dict[str, int]:
    """Return total number of games (for dynamic tab/button label)."""
    if not LOGS_DIR.exists():
        return {"count": 0}
    paths = [f for f in LOGS_DIR.glob("game_*.json") if _match_island_game(f)]
    return {"count": len(paths)}


@app.get("/api/games-summary")
async def games_summary() -> dict[str, Any]:
    """Return summary of game_*.json logs: games grouped by run, + total score per agent.
    All agents from roster are included in the table (even with 0 games/score).
    IDEA: agentAvgPerRound — нормалізований (100=середній). AgentTotals/Rounds — сирі."""
    # Pre-load ALL agents from roster — table shows everyone, not just those who played
    roster_names: dict[str, str] = {}
    roster_path = _PROJECT_ROOT / "agents" / "roster.json"
    if roster_path.exists():
        try:
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
            for a in roster.get("agents", []):
                if a.get("id") and a.get("name"):
                    roster_names[a["id"]] = a["name"]
        except Exception:
            pass
    all_display_names = list(roster_names.values()) if roster_names else []

    if not LOGS_DIR.exists():
        agent_totals = {name: 0.0 for name in all_display_names}
        agent_games: dict[str, int] = {name: 0 for name in all_display_names}
        agent_rounds: dict[str, int] = {name: 0 for name in all_display_names}
        agent_avg: dict[str, float] = {name: 0.0 for name in all_display_names}
        return {"games": [], "runs": [], "agentTotals": agent_totals, "agentNames": all_display_names,
                "agentGamesPlayed": agent_games, "agentRoundsPlayed": agent_rounds, "agentAvgPerRound": agent_avg}
    paths = [f for f in LOGS_DIR.glob("game_*.json") if _match_island_game(f)]
    paths.sort(key=lambda p: _island_game_sort_key(p, _match_island_game(p)), reverse=True)
    games: list[dict[str, Any]] = []
    runs_order: list[dict[str, Any]] = []
    seen_run: dict[str, dict[str, Any]] = {}
    # IDEA: Всі агенти з roster у таблиці (навіть 0 ігор). names з roster, не з games.
    agent_totals: dict[str, float] = {name: 0.0 for name in all_display_names}
    agent_games: dict[str, int] = {name: 0 for name in all_display_names}
    agent_rounds: dict[str, int] = {name: 0 for name in all_display_names}
    agent_names_order: list[str] = all_display_names.copy()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        m = _match_island_game(path)
        if not m:
            continue
        date_str, time_str = m.group(1), m.group(2)
        try:
            g3 = m.group(3)
            game_display = int(g3) if g3.isdigit() else g3
        except IndexError:
            game_display = 1  # bare pattern: game_DATE_TIME.json has no suffix
        run_id = f"{date_str}_{time_str}"
        if run_id not in seen_run:
            time_display_run = time_str.replace("-", ":")
            runs_order.append({"runId": run_id, "runLabel": f"{date_str} {time_display_run}", "gameCount": 0})
            seen_run[run_id] = runs_order[-1]
        seen_run[run_id]["gameCount"] = seen_run[run_id]["gameCount"] + 1
        names = data.get("agent_names") or {}
        scores = data.get("final_scores") or {}
        winner_id = data.get("winner") or ""
        winner_name = names.get(winner_id, winner_id)
        rounds = data.get("total_rounds") or 0
        # Fallback: if roster was empty, build agent_names_order from first game
        if not agent_names_order and data.get("agents") and names:
            agent_names_order = [names.get(aid, aid) for aid in data["agents"] if names.get(aid)]
            if not agent_names_order:
                agent_names_order = list(names.values())
        scores_by_name = {names.get(aid, aid): scores.get(aid, 0) for aid in scores}
        # Ensure game agents are in agent_totals (for legacy games with different roster)
        for name in scores_by_name:
            if name and name not in agent_totals:
                agent_totals[name] = 0.0
                agent_games[name] = 0
                agent_rounds[name] = 0
        for name, val in scores_by_name.items():
            agent_totals[name] = agent_totals.get(name, 0) + val
            agent_games[name] = agent_games.get(name, 0) + 1
            agent_rounds[name] = agent_rounds.get(name, 0) + rounds
        html_name = path.name.replace(".json", ".html")
        time_display = time_str.replace("-", ":")  # 22-58-50 → 22:58:50
        played_at = f"{date_str} {time_display}"
        games.append({
            "game": game_display,
            "rounds": rounds,
            "winner": winner_name,
            "scores": scores_by_name,
            "reportPath": f"/logs/{html_name}",
            "runId": run_id,
            "runLabel": played_at,
            "playedAt": played_at,
        })
    for r in runs_order:
        n = r["gameCount"]
        r["runTitle"] = f"3×7 (3 ігри)" if n == 3 else f"7 ігор" if n == 7 else f"{n} ігор"
    # IDEA [REFACTOR: ЗБЕРЕГТИ]: Середній бал — нормалізація до єдиної шкали.
    # Ігри мають різні шкали (17 vs 28 vs 70 бал/раунд). Кожну гру нормалізуємо:
    # game_avg = середнє(бал/раунд), scale = 100/game_avg, agent_norm = (бал/раунд)*scale.
    # Усереднюємо agent_norm за кількістю ігор. 100 = середній по грі.
    agent_avg_per_round: dict[str, float] = {}
    for name in agent_totals:
        per_game_sum = 0.0
        games_played = 0
        for g in games:
            if name not in g["scores"]:
                continue
            scores = g["scores"]
            rounds = g.get("rounds") or 0
            if rounds <= 0:
                continue
            # Середнє бал/раунд по всіх агентах у цій грі
            game_per_round = [s / rounds for s in scores.values()]
            game_avg = sum(game_per_round) / len(game_per_round) if game_per_round else 1.0
            scale = 100.0 / game_avg if game_avg > 0 else 1.0
            agent_per_round = scores[name] / rounds
            agent_norm = agent_per_round * scale
            per_game_sum += agent_norm
            games_played += 1
        agent_avg_per_round[name] = round(per_game_sum / games_played, 2) if games_played > 0 else 0.0
    return {
        "games": games,
        "runs": runs_order,
        "agentTotals": agent_totals,
        "agentNames": agent_names_order,
        "agentGamesPlayed": agent_games,
        "agentRoundsPlayed": agent_rounds,
        "agentAvgPerRound": agent_avg_per_round,
    }


# ---------------------------------------------------------------------------
# Analytics endpoint — агрегована статистика поведінки агентів по всіх іграх
# ---------------------------------------------------------------------------

@app.get("/api/analytics/island")
async def analytics_island() -> dict[str, Any]:
    """Обчислює поведінкову аналітику агентів: зради, кооперації, win rate, ефективність."""
    roster_names: dict[str, str] = {}
    roster_path = _PROJECT_ROOT / "agents" / "roster.json"
    if roster_path.exists():
        try:
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
            for a in roster.get("agents", []):
                if a.get("id") and a.get("name"):
                    roster_names[a["id"]] = a["name"]
        except Exception:
            pass

    # Агрегатори: agent_id → лічильники
    stats: dict[str, dict[str, int | float]] = {}

    def _get_stats(name: str) -> dict[str, int | float]:
        if name not in stats:
            stats[name] = {
                "games_played": 0,
                "games_won": 0,
                "betrayals_committed": 0,   # exploit_i або exploit_j — ця людина зрадила
                "betrayals_received": 0,    # ця людина була зрадженою
                "mutual_coops": 0,          # обидва кооперували
                "mutual_defects": 0,        # обидва зрадили
            }
        return stats[name]

    if not LOGS_DIR.exists():
        return {"agents": [], "totals": {"games": 0, "betrayals": 0, "mutual_coops": 0}}

    paths = [f for f in LOGS_DIR.glob("game_*.json") if _match_island_game(f)]

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        agent_ids: list[str] = data.get("agents", [])
        agent_names: dict[str, str] = data.get("agent_names") or {}
        # Використовуємо відображені імена з roster або з гри
        def display(aid: str) -> str:
            return roster_names.get(aid) or agent_names.get(aid) or aid

        winner_id = data.get("winner") or ""
        winner_name = display(winner_id) if winner_id else ""

        # Облікуємо участь у грі
        for aid in agent_ids:
            s = _get_stats(display(aid))
            s["games_played"] += 1
            if display(aid) == winner_name:
                s["games_won"] += 1

        # Обробляємо pair_outcomes в кожному раунді
        for rnd in data.get("rounds", []):
            payoffs = rnd.get("payoffs") or {}
            pair_outcomes = payoffs.get("pair_outcomes") or []
            for po in pair_outcomes:
                outcome = po.get("outcome", "")
                pair_str = po.get("pair", "")
                # Формат: "AgentA→AgentB"
                if "→" in pair_str:
                    parts = pair_str.split("→", 1)
                elif "\u0432\u2020\u2019" in pair_str:
                    parts = pair_str.split("\u0432\u2020\u2019", 1)
                else:
                    continue
                if len(parts) != 2:
                    continue
                name_i, name_j = parts[0].strip(), parts[1].strip()
                # Конвертуємо agent_id → display name якщо потрібно
                name_i = roster_names.get(name_i) or agent_names.get(name_i) or name_i
                name_j = roster_names.get(name_j) or agent_names.get(name_j) or name_j

                si, sj = _get_stats(name_i), _get_stats(name_j)
                if outcome == "mutual_coop":
                    si["mutual_coops"] += 1
                    sj["mutual_coops"] += 1
                elif outcome == "mutual_defect":
                    si["mutual_defects"] += 1
                    sj["mutual_defects"] += 1
                elif outcome == "exploit_i":  # i зрадив j
                    si["betrayals_committed"] += 1
                    sj["betrayals_received"] += 1
                elif outcome == "exploit_j":  # j зрадив i
                    sj["betrayals_committed"] += 1
                    si["betrayals_received"] += 1

    # Обчислюємо похідні метрики
    agent_list = []
    total_betrayals = 0
    total_mutual_coops = 0
    for name, s in stats.items():
        gp = s["games_played"]
        total_interactions = s["betrayals_committed"] + s["mutual_coops"] + s["mutual_defects"] + s["betrayals_received"]
        # Відсоток кооперативних дій від усіх парних взаємодій (з боку цього агента)
        actions_as_actor = s["betrayals_committed"] + s["mutual_coops"] + s["mutual_defects"]
        coop_rate = round(
            (s["mutual_coops"]) / actions_as_actor * 100, 1
        ) if actions_as_actor > 0 else 0.0
        betrayal_rate = round(
            s["betrayals_committed"] / actions_as_actor * 100, 1
        ) if actions_as_actor > 0 else 0.0
        win_rate = round(s["games_won"] / gp * 100, 1) if gp > 0 else 0.0
        agent_list.append({
            "name": name,
            "games_played": gp,
            "games_won": int(s["games_won"]),
            "win_rate": win_rate,
            "betrayals_committed": int(s["betrayals_committed"]),
            "betrayals_received": int(s["betrayals_received"]),
            "mutual_coops": int(s["mutual_coops"]),
            "mutual_defects": int(s["mutual_defects"]),
            "coop_rate": coop_rate,
            "betrayal_rate": betrayal_rate,
        })
        total_betrayals += int(s["betrayals_committed"])
        total_mutual_coops += int(s["mutual_coops"])

    # Сортуємо: спочатку ті хто грав більше
    agent_list.sort(key=lambda x: (-x["games_played"], -x["win_rate"]))
    total_games = len(paths)

    return {
        "agents": agent_list,
        "totals": {
            "games": total_games,
            "betrayals": total_betrayals,
            "mutual_coops": total_mutual_coops // 2,  # кожна пара рахується двічі
        },
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Static files (UI) — mount /logs and /assets BEFORE catch-all so they take precedence
# ---------------------------------------------------------------------------

_assets_dir = DIST_DIR / "assets"
_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
if LOGS_DIR.exists():
    app.mount("/logs", StaticFiles(directory=str(LOGS_DIR)), name="logs")

_docs_dir = Path(__file__).parent.parent / "docs"
if _docs_dir.exists():
    app.mount("/docs", StaticFiles(directory=str(_docs_dir)), name="docs")

_root_dir = Path(__file__).parent.parent
_ROOT_HTML_FILES = {
    f.name for f in _root_dir.glob("*.html")
}


def _index_path() -> Path:
    return DIST_DIR / "index.html"


@app.get("/")
async def serve_index():
    """Root → Hub (navigation). Init pipeline moved to /init."""
    hub = _root_dir / "hub.html"
    if hub.exists():
        return FileResponse(str(hub), media_type="text/html")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/hub")


@app.get("/init")
async def serve_init():
    """Agent initialization React SPA (was at /)."""
    idx = _index_path()
    if idx.exists():
        return FileResponse(idx)
    return PlainTextResponse("Init app not built — run: cd frontend && npm run build", status_code=404)


# ---------------------------------------------------------------------------
# Island Launcher routes
# ---------------------------------------------------------------------------

from server.island_routes import router as _island_router
app.include_router(_island_router)


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React SPA; also serves root-level .html files and falls back to hub."""
    # Root-level HTML files (arch_*.html, hub.html, island_launcher.html, etc.)
    if full_path in _ROOT_HTML_FILES:
        return FileResponse(str(_root_dir / full_path), media_type="text/html")
    # React SPA dist files
    file_path = DIST_DIR / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    idx = _index_path()
    if idx.exists():
        return FileResponse(idx)
    return PlainTextResponse("Not found", status_code=404)
