"""
Entry point for Railpack/Railway: they auto-run main.py or app.py in project root.
This starts the FastAPI server (same as run.py).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent
# override=False so Railway Variables take precedence over .env file
load_dotenv(_project_root / ".env", override=False)

if __name__ == "__main__":
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY is not set. Set it in Railway Variables.")
    else:
        print("OPENROUTER_API_KEY found.")
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting on http://0.0.0.0:{port}")
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
