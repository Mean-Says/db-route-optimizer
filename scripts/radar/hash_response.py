#!/usr/bin/env python3
"""Hash an HTTP JSON response for before/after equality (volatile keys ignored).

Stdlib only.

Usage:
  python scripts/radar/hash_response.py --url http://127.0.0.1:8000/api/foo
  python scripts/radar/hash_response.py --file body.json --ignore updated_at,request_id
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request

DEFAULT_IGNORE = {
    "request_id",
    "trace_id",
    "timestamp",
    "generated_at",
    "server_time",
    "updated_at",
    "created_at",
}


def strip_volatile(obj, ignore: set[str]):
    if isinstance(obj, dict):
        return {
            k: strip_volatile(v, ignore)
            for k, v in sorted(obj.items())
            if k not in ignore
        }
    if isinstance(obj, list):
        return [strip_volatile(x, ignore) for x in obj]
    return obj


def stable_hash(obj, ignore: set[str]) -> str:
    cleaned = strip_volatile(obj, ignore)
    raw = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="GET JSON from this URL")
    p.add_argument("--file", help="read JSON from file (- for stdin)")
    p.add_argument(
        "--ignore",
        default=",".join(sorted(DEFAULT_IGNORE)),
        help="comma-separated keys to drop before hashing",
    )
    args = p.parse_args(argv)
    ignore = {k.strip() for k in args.ignore.split(",") if k.strip()}

    if args.url:
        with urllib.request.urlopen(args.url, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
    elif args.file:
        if args.file == "-":
            data = json.load(sys.stdin)
        else:
            with open(args.file) as f:
                data = json.load(f)
    else:
        p.error("provide --url or --file")

    h = stable_hash(data, ignore)
    print(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
