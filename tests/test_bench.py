"""Tests for bench stats and --compare (including divide-by-zero)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from db_route_optimizer.bench import _stats, main

ROOT = Path(__file__).resolve().parents[1]


def test_stats_fixed_samples():
    st = _stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert st["n"] == 5
    assert st["min_ms"] == 10.0
    assert st["max_ms"] == 50.0
    assert st["median_ms"] == 30.0
    assert st["mean_ms"] == 30.0


def test_stats_single_sample():
    st = _stats([7.5])
    assert st["n"] == 1
    assert st["p95_ms"] == 7.5
    assert st["stdev_ms"] == 0.0


def test_compare_divide_by_zero(tmp_path, capsys):
    base = {
        "label": "base",
        "target": "t",
        "stats": {"median_ms": 10.0, "p95_ms": 12.0, "mean_ms": 10.0, "min_ms": 9.0},
    }
    cand = {
        "label": "cand",
        "target": "t",
        "stats": {"median_ms": 0.0, "p95_ms": 0.0, "mean_ms": 0.0, "min_ms": 0.0},
    }
    bp = tmp_path / "base.json"
    cp = tmp_path / "cand.json"
    bp.write_text(json.dumps(base))
    cp.write_text(json.dumps(cand))
    with pytest.raises(SystemExit) as ei:
        main(["--compare", str(bp), str(cp), "--name", "zero"])
    assert ei.value.code == 1


def test_compare_improvement(tmp_path, capsys):
    base = {
        "label": "base",
        "target": "t",
        "stats": {"median_ms": 100.0, "p95_ms": 120.0, "mean_ms": 100.0, "min_ms": 90.0},
    }
    cand = {
        "label": "cand",
        "target": "t",
        "stats": {"median_ms": 50.0, "p95_ms": 60.0, "mean_ms": 50.0, "min_ms": 45.0},
    }
    bp = tmp_path / "base.json"
    cp = tmp_path / "cand.json"
    log = tmp_path / "log.md"
    bp.write_text(json.dumps(base))
    cp.write_text(json.dumps(cand))
    main(["--compare", str(bp), str(cp), "--name", "half", "--log", str(log)])
    out = capsys.readouterr().out
    assert "faster" in out
    assert "2.00x" in out
    assert log.exists()
    assert "half" in log.read_text()


def test_cli_measure_cmd(tmp_path):
    out = tmp_path / "run.json"
    main(
        [
            "--cmd",
            f"{sys.executable} -c \"pass\"",
            "--n",
            "3",
            "--warmup",
            "1",
            "--label",
            "noop",
            "--out",
            str(out),
        ]
    )
    data = json.loads(out.read_text())
    assert data["stats"]["n"] == 3
