#!/usr/bin/env python3
"""Bench a Radar (or any) HTTP endpoint and print median/p95 + optional body hash.

Wraps scripts/bench.py logic via subprocess so it works on main before the
db-route-optimizer package lands. Prefer `dbro-bench` once Phase 0 is installed.

Usage:
  python scripts/radar/measure_endpoint.py --url http://127.0.0.1:8000/api/x \\
      --label baseline --out /tmp/radar_base.json --hash
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--label", default="run")
    p.add_argument("--out", required=True, help="JSON run path (private disk)")
    p.add_argument("--hash", action="store_true", help="also print body hash (volatile keys stripped)")
    p.add_argument("--sleep", type=float, default=0.0)
    args = p.parse_args(argv)

    bench = ROOT / "scripts" / "bench.py"
    cmd = [
        sys.executable,
        str(bench),
        "--url",
        args.url,
        "--n",
        str(args.n),
        "--warmup",
        str(args.warmup),
        "--label",
        args.label,
        "--out",
        args.out,
    ]
    if args.sleep:
        cmd.extend(["--sleep", str(args.sleep)])

    env = os.environ.copy()
    # Allow running after Phase 0 package exists
    r = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if r.returncode != 0:
        return r.returncode

    if args.hash:
        hash_script = ROOT / "scripts" / "radar" / "hash_response.py"
        h = subprocess.check_output(
            [sys.executable, str(hash_script), "--url", args.url],
            text=True,
        ).strip()
        meta_path = Path(args.out)
        data = json.loads(meta_path.read_text())
        data["response_hash"] = h
        meta_path.write_text(json.dumps(data, indent=2))
        print(f"response_hash={h}", file=sys.stderr)

    print(
        "Remember: keep this JSON and any optimization_log on a private path "
        "(see examples/radar_private/).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
