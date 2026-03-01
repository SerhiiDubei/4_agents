"""
run.py — Start the Island Agent Init server.

Usage:
    python run.py

Then open http://localhost:8000 in your browser.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (resolve to absolute path so it works from any cwd)
_project_root = Path(__file__).resolve().parent
_env_path = _project_root / ".env"
load_dotenv(_env_path)
if not _env_path.exists():
    print(f"Note: .env not found at {_env_path}")

import uvicorn

if __name__ == "__main__":
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print(f"  Looked for .env at: {_env_path}")
        print("  Copy .env.example to .env and fill in your API key.")
        raise SystemExit(1)

    print("Starting Island Agent Init on http://localhost:8000")
    # reload=False so the worker process inherits OPENROUTER_API_KEY from this process
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
