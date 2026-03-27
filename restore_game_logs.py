"""
restore_game_logs.py — Reconstruct game_*.json files from .log terminal output.

Reads logs/tests/*.log files, parses FINAL RESULTS blocks,
and creates minimal game_*.json in logs/island/ matching server's expected schema:
  agent_names: {agent_id: display_name}
  final_scores: {agent_id: score}
  winner: agent_id

Run once: python restore_game_logs.py
Re-running is safe — existing files are skipped.
Use --force to re-parse and overwrite (useful after fixing parser bugs).
"""
import json
import re
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
TESTS_DIR = ROOT / "logs" / "tests"
ISLAND_DIR = ROOT / "logs" / "island"
ISLAND_DIR.mkdir(parents=True, exist_ok=True)

ANSI = re.compile(r"\x1b\[[0-9;]*m|\r")

# Match score rows. Terminal format:
#   🥇  Вова      gent_synth_j   +182.47  ████ ...  ← WINNER
#   4  Роман Романюк  gent_synth_d   +62.15  ██...
SCORE_ROW = re.compile(
    r"(?:🥇|🥈|🥉|\s{2,4}\d{1,2})\s{2,}"  # rank prefix
    r"(.+?)\s{2,}"                            # display name (non-greedy, >= 2 spaces after)
    r"([\w]+)\s+"                             # agent_id fragment (word chars only)
    r"([+-]?\d+\.?\d*)"                       # score
)


def read_log(path: pathlib.Path) -> str:
    """Read log file — UTF-8 first (correct), then fallback encodings."""
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def load_roster() -> dict[str, str]:
    """Returns {display_name: agent_id} from roster.json."""
    roster_path = ROOT / "agents" / "roster.json"
    if not roster_path.exists():
        return {}
    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        return {a["name"]: a["id"] for a in roster.get("agents", []) if a.get("id") and a.get("name")}
    except Exception:
        return {}


def fix_agent_id(fragment: str, name_to_id: dict[str, str], display_name: str) -> str:
    """Reconstruct full agent_id from terminal display fragment + roster lookup."""
    # Primary: match by display_name via roster
    if display_name in name_to_id:
        return name_to_id[display_name]
    # Terminal sometimes strips leading 'a': "gent_synth_j" → "agent_synth_j"
    if fragment.startswith("gent_synth_"):
        return "a" + fragment
    # Terminal shows short hex IDs like "65c37face813" → "agent_65c37face813"
    if re.match(r"^[0-9a-f]{8,}", fragment):
        return f"agent_{fragment}"
    # Roster suffix match
    for aid in name_to_id.values():
        if aid.endswith(fragment) or aid == fragment:
            return aid
    return fragment


def parse_log(path: pathlib.Path, name_to_id: dict[str, str]) -> dict | None:
    raw = read_log(path)
    clean = ANSI.sub("", raw)

    # Canonical filename from embedded JSON log path
    jmatch = re.search(r"JSON log:\s*(.+\.json)", clean)
    if not jmatch:
        return None
    json_name = pathlib.Path(jmatch.group(1).strip()).name

    # Winner display name
    wmatch = re.search(r"\n\s*Winner:\s*(.+)", clean)
    winner_display = wmatch.group(1).strip() if wmatch else ""

    # Rounds count
    rmatch = re.search(r"Score context \((\d+) rounds", clean)
    rounds = int(rmatch.group(1)) if rmatch else 0

    # Score table — find the FINAL RESULTS block
    fr_match = re.search(r"FINAL RESULTS.*?\n(.*?)(?:\n\s*Winner:)", clean, re.DOTALL)
    if not fr_match:
        return None

    block = fr_match.group(1)
    agent_names: dict[str, str] = {}   # agent_id → display_name
    final_scores: dict[str, float] = {}  # agent_id → score

    for row in SCORE_ROW.finditer(block):
        display = row.group(1).strip()
        fragment = row.group(2).strip()
        score_val = float(row.group(3))
        agent_id = fix_agent_id(fragment, name_to_id, display)
        agent_names[agent_id] = display
        final_scores[agent_id] = score_val

    if not final_scores:
        return None

    winner_id = fix_agent_id("", name_to_id, winner_display) if winner_display else ""

    return {
        "simulation_id": json_name.replace(".json", ""),
        "agent_names": agent_names,
        "total_rounds": rounds,
        "final_scores": final_scores,
        "winner": winner_id,
        "rounds": [],  # per-round data not available in terminal log
        "_restored_from": path.name,
    }


def get_json_name_from_log(path: pathlib.Path) -> str | None:
    """Quick scan for the JSON log filename without full parse."""
    raw = read_log(path)
    m = re.search(r"JSON log:\s*(.+\.json)", raw)
    return pathlib.Path(m.group(1).strip()).name if m else None


def main() -> None:
    force = "--force" in sys.argv
    name_to_id = load_roster()
    print(f"Roster: {len(name_to_id)} agents")

    log_files = sorted(TESTS_DIR.glob("*.log"))
    restored = skipped = failed = 0

    for lf in log_files:
        json_name = get_json_name_from_log(lf)
        if not json_name:
            print(f"  SKIP    {lf.name} — no JSON log path found")
            failed += 1
            continue

        out_path = ISLAND_DIR / json_name

        if out_path.exists() and not force:
            print(f"  EXISTS  {out_path.name}")
            skipped += 1
            continue

        data = parse_log(lf, name_to_id)
        if not data:
            print(f"  FAIL    {lf.name} — parse failed")
            failed += 1
            continue

        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        winner_name = data["agent_names"].get(data["winner"], data["winner"])
        print(f"  OK      {out_path.name}  winner={winner_name}  rounds={data['total_rounds']}  agents={len(data['final_scores'])}")
        restored += 1

    print(f"\nDone: {restored} restored, {skipped} skipped, {failed} failed")
    print(f"Total game_*.json in logs/island/: {len(list(ISLAND_DIR.glob('game_*.json')))}")


if __name__ == "__main__":
    main()
