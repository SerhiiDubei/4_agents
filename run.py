"""
run.py — Start the Island Agent Init server.

Usage:
    python run.py

Then open http://localhost:8000 in your browser.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

import uvicorn

if __name__ == "__main__":
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("Copy .env.example to .env and fill in your API key.")
        raise SystemExit(1)

    print("Starting Island Agent Init on http://localhost:8000")
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["pipeline", "server", "schemas", "static"],
    )
