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
# override=False so Railway Variables (and existing env) are not overwritten by .env file
load_dotenv(_env_path, override=False)

import uvicorn

if __name__ == "__main__":
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY is not set. API calls will fail.")
        print("  Railway: Project -> Your service -> Variables -> Add OPENROUTER_API_KEY (exact name).")
        print("  Locally: copy .env.example to .env and set your API key.")
        # Don't exit — start server so container stays up and user can fix Variables
    else:
        print("OPENROUTER_API_KEY found.")

    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Island Agent Init on http://0.0.0.0:{port}")
    # reload=False so the worker process inherits OPENROUTER_API_KEY from this process
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
