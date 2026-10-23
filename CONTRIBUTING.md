# Contributing

Thanks for helping improve db-route-optimizer. This project is open source (MIT), for public
benefit — not sold.

## Ground rules

- **Measure, don't invent.** Performance numbers in docs/PRs must come from a log produced by
  `make reproduce` (or `dbro-bench --compare`). Use `[MEDIR: ...]` until you have a log.
- **One change per comparison.** Keep commits small and focused.
- **No third-party advisor integrations** (HypoPG, Dexter, external MCP servers) in core.
- **Never** run writes, DDL, or `EXPLAIN ANALYZE` against non-local databases.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
ruff check db_route_optimizer scripts tests examples
pytest -v
```

## Pull requests

1. Branch from `main`.
2. Add/adjust tests for behavior changes.
3. Ensure CI is green (ruff + pytest matrix + Postgres job).
4. If you touch demo numbers, paste / link the `make reproduce` log in the PR.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
