"""
run_all_tests.py  --  TEST GENERAL

Master test runner. Runs all test suites in sequence and prints a unified report.

Usage:
    python run_all_tests.py          # all suites
    python run_all_tests.py --tw     # Time Wars only (fast)
    python run_all_tests.py --full   # include Island smoke + stress (slower)

Exit code:
    0 = all suites passed
    1 = one or more suites failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"
PY = sys.executable

# Ensure UTF-8 output from child processes (Windows cp1251 fix)
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], label: str) -> dict:
    """Run a command, capture output, return result dict."""
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            env=CHILD_ENV,
        )
        elapsed = round((time.time() - start) * 1000)
        return {
            "label": label,
            "cmd": " ".join(cmd),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_ms": elapsed,
        }
    except Exception as e:
        elapsed = round((time.time() - start) * 1000)
        return {
            "label": label,
            "cmd": " ".join(cmd),
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "elapsed_ms": elapsed,
        }


def _parse_custom_runner(stdout: str) -> tuple[int, int]:
    """
    Parse output from custom test runner (test_time_wars.py, test_pipeline.py).
    Looks for lines like:  '21 passed, 0 failed'
    or TOTAL lines like:  'TOTAL: 21 | PASS: 21 | FAIL: 0 | SKIP: 5 | 200ms'
    Returns (passed, failed).
    """
    # Pattern: "N passed, M failed"
    m = re.search(r"(\d+)\s+passed,\s*(\d+)\s+failed", stdout)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern: "TOTAL: X | PASS: Y | FAIL: Z"
    m = re.search(r"PASS:\s*(\d+).*?FAIL:\s*(\d+)", stdout)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern from stress_rounds: "N/M passed"
    m = re.search(r"(\d+)/(\d+)\s+passed", stdout)
    if m:
        passed = int(m.group(1))
        total = int(m.group(2))
        return passed, total - passed
    return 0, 0


def _parse_pytest(stdout: str) -> tuple[int, int]:
    """
    Parse pytest -v output.
    Looks for final line:  '18 passed in 0.08s'  or  '15 passed, 3 failed in 0.3s'
    Returns (passed, failed).
    """
    m = re.search(r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?", stdout)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2)) if m.group(2) else 0
        return passed, failed
    m = re.search(r"(\d+)\s+failed", stdout)
    if m:
        return 0, int(m.group(1))
    return 0, 0


# ---------------------------------------------------------------------------
# Suite definitions
# ---------------------------------------------------------------------------

def suite_tw_unit() -> dict:
    r = _run([PY, "tests/test_time_wars.py"], "Time Wars unit tests")
    passed, failed = _parse_custom_runner(r["stdout"])
    r.update({"passed": passed, "failed": failed, "total": passed + failed})
    return r


def suite_tw_integration() -> dict:
    r = _run(
        [PY, "-m", "pytest", "tests/test_tw_integration.py", "-v", "--tb=short"],
        "Time Wars integration tests (pytest)",
    )
    passed, failed = _parse_pytest(r["stdout"])
    r.update({"passed": passed, "failed": failed, "total": passed + failed})
    return r


def suite_pipeline() -> dict:
    r = _run([PY, "tests/test_pipeline.py"], "Pipeline / Island offline tests")
    passed, failed = _parse_custom_runner(r["stdout"])
    r.update({"passed": passed, "failed": failed, "total": passed + failed})
    return r


def suite_stress() -> dict:
    r = _run([PY, "tests/stress_rounds.py"], "Island stress rounds")
    passed, failed = _parse_custom_runner(r["stdout"])
    r.update({"passed": passed, "failed": failed, "total": passed + failed})
    return r


def suite_smoke(name: str) -> dict:
    r = _run([PY, f"tests/smoke_{name}.py"], f"Island smoke {name.upper()}")
    # smoke scripts exit 0 = pass, 1 = fail; parse counts if possible
    passed, failed = _parse_custom_runner(r["stdout"] + r["stderr"])
    if passed == 0 and failed == 0:
        # Fallback: use exit code
        passed = 1 if r["exit_code"] == 0 else 0
        failed = 0 if r["exit_code"] == 0 else 1
    r.update({"passed": passed, "failed": failed, "total": passed + failed})
    return r


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

_WIDTH = 52

def _bar(passed: int, total: int) -> str:
    if total == 0:
        return "[  no tests  ]"
    width = 20
    filled = round(passed / total * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _print_report(suites: list[dict]) -> bool:
    total_passed = sum(s["passed"] for s in suites)
    total_failed = sum(s["failed"] for s in suites)
    total_tests  = sum(s["total"]  for s in suites)
    total_ms     = sum(s["elapsed_ms"] for s in suites)
    all_ok       = total_failed == 0 and all(s["exit_code"] == 0 for s in suites)

    sep = "=" * _WIDTH
    thin = "-" * _WIDTH
    print()
    print(sep)
    print("  TEST GENERAL REPORT")
    print(sep)

    for s in suites:
        ok = s["exit_code"] == 0 and s["failed"] == 0
        tag = "OK  " if ok else "FAIL"
        bar = _bar(s["passed"], s["total"])
        label = s["label"][:36]
        counts = f"{s['passed']}/{s['total']}"
        print(f"  [{tag}] {label:<36s} {counts:>6s}  {s['elapsed_ms']}ms")

        # Print failures inline
        if not ok:
            for line in (s["stdout"] + s["stderr"]).splitlines():
                line = line.strip()
                if any(kw in line for kw in ("FAILED", "FAIL]", "Error", "assert", "Exception")):
                    print(f"         > {line[:72]}")

    print(thin)
    status_str = "ALL GREEN" if all_ok else "FAILURES DETECTED"
    print(f"  TOTAL : {total_tests} tests  |  PASS {total_passed}  FAIL {total_failed}")
    print(f"  TIME  : {total_ms}ms  ({total_ms/1000:.1f}s)")
    print(f"  STATUS: {status_str}")
    print(sep)
    print()
    return all_ok


def _save_report(suites: list[dict], all_ok: bool) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOGS_DIR / f"test_report_{ts}.json"
    data = {
        "run_at": datetime.now().isoformat(),
        "all_ok": all_ok,
        "summary": {
            "total":  sum(s["total"]  for s in suites),
            "passed": sum(s["passed"] for s in suites),
            "failed": sum(s["failed"] for s in suites),
            "elapsed_ms": sum(s["elapsed_ms"] for s in suites),
        },
        "suites": [
            {
                "label":      s["label"],
                "passed":     s["passed"],
                "failed":     s["failed"],
                "total":      s["total"],
                "exit_code":  s["exit_code"],
                "elapsed_ms": s["elapsed_ms"],
            }
            for s in suites
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Report -> {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Test General — runs all test suites")
    parser.add_argument("--tw",   action="store_true", help="Time Wars suites only (fast)")
    parser.add_argument("--full", action="store_true", help="Include Island smoke + stress")
    args = parser.parse_args()

    run_tw_only  = args.tw
    run_full     = args.full

    print()
    print("=" * _WIDTH)
    print("  TEST GENERAL - starting...")
    print("=" * _WIDTH)

    suites: list[dict] = []

    # Always run Time Wars suites
    print("  [1/2] Time Wars unit tests...")
    suites.append(suite_tw_unit())

    print("  [2/2] Time Wars integration tests...")
    suites.append(suite_tw_integration())

    if not run_tw_only:
        # Pipeline (offline only — OPENROUTER not required)
        print("  [3/?] Pipeline / Island offline tests...")
        suites.append(suite_pipeline())

    if run_full:
        # Island stress + smoke (slower, optional)
        print("  [4/?] Island stress rounds...")
        suites.append(suite_stress())

        for name in ("a", "b", "c", "d"):
            print(f"  [5/?] Island smoke {name.upper()}...")
            suites.append(suite_smoke(name))

    all_ok = _print_report(suites)
    _save_report(suites, all_ok)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
