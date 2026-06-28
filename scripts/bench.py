#!/usr/bin/env python3
"""Benchmark harness: measure a target's latency, then compare baseline vs candidate.

Stdlib only (no pip install). Two things it does:

1. MEASURE a target N times and save stats to JSON:
   - HTTP GET:   bench.py --url https://radardeempregos.com/api/insights/panorama --n 50 --label baseline --out base.json
   - any command: bench.py --cmd "python scripts/run_query.py" --n 20 --label baseline --out base.json

2. COMPARE two JSON runs -> % faster + speedup, appended to a markdown log:
   bench.py --compare base.json cand.json --name "GET /api/mobile/vagas" --log docs/perf/optimization_log.md

Typical flow for an optimization:
   1) bench.py --url <U> --label baseline --out base.json   # before any change
   2) <apply the optimization>
   3) bench.py --url <U> --label candidate --out cand.json   # after
   4) bench.py --compare base.json cand.json --name "<route/query>" --log docs/perf/optimization_log.md

Rules for THIS project: never hit localhost or trigger writes. Benchmark read-only
GET endpoints against the dev server or production, or wrap a read-only query.
"""
import argparse
import json
import os
import ssl
import statistics
import subprocess
import sys
import time
import urllib.request
import urllib.error


def _ssl_context(insecure):
    """macOS Python ships without the system CA store; fall back to certifi, then --insecure."""
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _stats(samples_ms):
    s = sorted(samples_ms)
    n = len(s)

    def pct(p):
        if n == 1:
            return s[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        return s[f] + (s[c] - s[f]) * (k - f)

    return {
        "n": n,
        "min_ms": round(s[0], 2),
        "mean_ms": round(statistics.fmean(s), 2),
        "median_ms": round(statistics.median(s), 2),
        "p95_ms": round(pct(0.95), 2),
        "max_ms": round(s[-1], 2),
        "stdev_ms": round(statistics.pstdev(s), 2) if n > 1 else 0.0,
    }


def _time_http(url, method, timeout, ctx):
    req = urllib.request.Request(url, method=method)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        resp.read()
        code = resp.status
    dt = (time.perf_counter() - t0) * 1000
    return dt, code


def _time_cmd(cmd):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, shell=True, capture_output=True)
    dt = (time.perf_counter() - t0) * 1000
    return dt, r.returncode


def measure(args):
    warmup = args.warmup
    n = args.n
    samples = []
    label = args.label or ("http" if args.url else "cmd")

    target_desc = args.url or args.cmd
    print(f"[{label}] warmup={warmup} n={n} -> {target_desc}", file=sys.stderr)

    ctx = _ssl_context(args.insecure) if args.url else None
    i = 0
    total = warmup + n
    while i < total:
        try:
            if args.url:
                dt, status = _time_http(args.url, args.method, args.timeout, ctx)
            else:
                dt, status = _time_cmd(args.cmd)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited: back off and retry this iteration (not counted)
                wait = max(args.sleep * 4, 2.0)
                print(f"  429 rate limited, backing off {wait:.1f}s (raise --sleep)", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"request failed: {e}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"request failed: {e}", file=sys.stderr)
            sys.exit(1)
        if i >= warmup:
            samples.append(dt)
            if status not in (0, 200, 201, 204):
                print(f"  warn: non-OK status {status} on iter {i}", file=sys.stderr)
        i += 1
        if args.sleep and i < total:
            time.sleep(args.sleep)

    st = _stats(samples)
    out = {
        "label": label,
        "target": target_desc,
        "method": args.method if args.url else "cmd",
        "stats": st,
        "samples_ms": [round(x, 2) for x in samples],
    }
    print(json.dumps(st, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(out, f, indent=2)
        print(f"saved -> {args.out}", file=sys.stderr)
    return out


def compare(args):
    base_path, cand_path = args.compare
    with open(base_path) as f:
        base = json.load(f)
    with open(cand_path) as f:
        cand = json.load(f)

    metric = args.metric  # median_ms / mean_ms / p95_ms
    b = base["stats"][metric]
    c = cand["stats"][metric]

    if c <= 0:
        print("candidate metric is 0, cannot compute speedup", file=sys.stderr)
        sys.exit(1)

    improvement_pct = (b - c) / b * 100 if b else 0.0
    speedup = b / c
    faster = improvement_pct >= 0
    verb = "mais rapido" if faster else "MAIS LENTO"

    name = args.name or cand.get("target", "target")
    print(f"\n=== {name} ===")
    print(f"baseline  {metric}: {b:.2f} ms   (p95 {base['stats']['p95_ms']} ms)")
    print(f"candidate {metric}: {c:.2f} ms   (p95 {cand['stats']['p95_ms']} ms)")
    print(f"-> {abs(improvement_pct):.1f}% {verb}  |  {speedup:.2f}x")

    if args.log:
        _append_log(args.log, name, metric, base, cand, improvement_pct, speedup)
        print(f"logged -> {args.log}", file=sys.stderr)


def _append_log(path, name, metric, base, cand, improvement_pct, speedup):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    header = (
        "# Optimization log\n\n"
        "Antes/depois por rota ou query. Gerado por `bench.py --compare`.\n\n"
        "| Alvo | Metrica | Antes (ms) | Depois (ms) | Melhoria | Speedup |\n"
        "|------|---------|-----------:|------------:|:--------:|:-------:|\n"
    )
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(header)
    row = (
        f"| {name} | {metric} | {base['stats'][metric]:.1f} | {cand['stats'][metric]:.1f} "
        f"| {improvement_pct:.1f}% | {speedup:.2f}x |\n"
    )
    with open(path, "a") as f:
        f.write(row)


def main():
    p = argparse.ArgumentParser(description="Latency benchmark + before/after comparison.")
    p.add_argument("--url", help="HTTP target (read-only GET preferred)")
    p.add_argument("--method", default="GET")
    p.add_argument("--cmd", help="shell command to time instead of an HTTP call")
    p.add_argument("--n", type=int, default=50, help="measured iterations")
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--insecure", action="store_true", help="skip TLS verification (last resort)")
    p.add_argument("--sleep", type=float, default=0.0,
                   help="seconds between requests; use >0 against rate-limited prod (e.g. 0.3)")
    p.add_argument("--label", help="baseline | candidate | ...")
    p.add_argument("--out", help="write run JSON here")
    p.add_argument("--compare", nargs=2, metavar=("BASE", "CAND"), help="compare two run JSONs")
    p.add_argument("--metric", default="median_ms", choices=["median_ms", "mean_ms", "p95_ms", "min_ms"])
    p.add_argument("--name", help="label for the compare report / log row")
    p.add_argument("--log", help="append the comparison to this markdown log")
    args = p.parse_args()

    if args.compare:
        compare(args)
    elif args.url or args.cmd:
        measure(args)
    else:
        p.error("provide --url, --cmd, or --compare")


if __name__ == "__main__":
    main()
