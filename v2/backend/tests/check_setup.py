#!/usr/bin/env python3
"""Print the readiness report. Run before wiring up Gmail for the first time.

    ./.venv/bin/python tests/check_setup.py [--port 8010]
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.diagnostics import report  # noqa: E402

GLYPH = {"ok": "ok  ", "warning": "warn", "error": "FAIL"}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    result = await report(args.port)
    print()
    for check in result["checks"]:
        print(f"  [{GLYPH[check['status']]}] {check['name']:<18} {check['detail']}")
        if check["fix"]:
            print(f"         → {check['fix']}")
    print(f"\n  overall: {result['status']}\n")
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
