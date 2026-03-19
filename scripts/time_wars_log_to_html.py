"""
Convert TIME WARS JSONL log to HTML with full event visualization and unified state (time + mana).
Usage: python scripts/time_wars_log_to_html.py [path_to.jsonl]
Default: latest time_wars_*.jsonl in logs/
Output: same path with .html extension.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_modes.time_wars.log_to_html import generate_time_wars_html


def main() -> int:
    if len(sys.argv) >= 2:
        jsonl_path = Path(sys.argv[1])
    else:
        logs_dir = ROOT / "logs"
        if not logs_dir.exists():
            print("No logs/ directory and no path given.", file=sys.stderr)
            return 1
        candidates = sorted(logs_dir.glob("time_wars_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("No time_wars_*.jsonl in logs/.", file=sys.stderr)
            return 1
        jsonl_path = candidates[0]
    if not jsonl_path.exists():
        print(f"File not found: {jsonl_path}", file=sys.stderr)
        return 1
    out_path = generate_time_wars_html(jsonl_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
