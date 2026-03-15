"""
Test each OpenRouter key from a keys file with a minimal API request.
Usage: python scripts/test_openrouter_keys.py [--keys-file openrouter_keys.txt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def load_keys_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def test_key(key: str, index: int) -> bool:
    api_key = key.replace("\ufeff", "").strip()
    if not api_key:
        return False
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 5,
            },
            timeout=30,
        )
        if r.status_code == 200:
            return True
        print(f"  Key {index}: HTTP {r.status_code} — {r.text[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  Key {index}: error — {e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Test each OpenRouter key from file with a minimal request.")
    parser.add_argument(
        "--keys-file",
        type=Path,
        default=ROOT / "openrouter_keys.txt",
        help="Path to file with one key per line (default: openrouter_keys.txt in project root).",
    )
    args = parser.parse_args()

    if not args.keys_file.exists():
        print(f"Keys file not found: {args.keys_file}", file=sys.stderr)
        return 1

    keys = load_keys_from_file(args.keys_file)
    if not keys:
        print("No keys found in file (empty or only comments).", file=sys.stderr)
        return 1

    print(f"Testing {len(keys)} key(s) from {args.keys_file}...")
    ok = 0
    for i, key in enumerate(keys, 1):
        if test_key(key, i):
            print(f"  Key {i}: OK")
            ok += 1
        else:
            print(f"  Key {i}: FAIL")
    print(f"Result: {ok}/{len(keys)} keys work.")
    return 0 if ok == len(keys) else 1


if __name__ == "__main__":
    sys.exit(main())
