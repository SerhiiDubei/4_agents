"""Test OpenRouter API key from command line. Run: python scripts/test_openrouter.py"""
import os
import sys
from pathlib import Path

# load .env from project root
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
except ImportError:
    pass

key = (os.environ.get("OPENROUTER_API_KEY") or "").replace("\ufeff", "").strip().strip("\r\n\t ")
if not key:
    print("ERROR: OPENROUTER_API_KEY not set in .env")
    sys.exit(1)

print(f"Key length: {len(key)} chars, starts with: {key[:15]}...")
print("Sending minimal request to OpenRouter (model=openai/gpt-4o-mini)...")

import httpx
r = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5,
    },
    timeout=30,
)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
if r.status_code != 200:
    sys.exit(1)
print("OK — key works.")
