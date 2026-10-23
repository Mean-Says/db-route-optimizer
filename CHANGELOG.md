# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Installable package `db-route-optimizer` (`pyproject.toml`) with extras
  `[sqlalchemy]`, `[postgres]`, `[dev]`.
- CLI entry points: `dbro-bench`, `dbro-querycount`, `dbro-explain`.
- English output by default; `--lang pt-BR` on all CLIs (`i18n.py`).
- `querycount`: duplicate (SQL+params) reporting; raise/fail mode for budgets and duplicates;
  friendly non-zero exit when SQLAlchemy is missing.
- `explain_query`: dialect from URL; `--plain` default on non-local hosts; refuse ANALYZE on
  non-SELECT; password redaction; `--json`; read-only + `statement_timeout` (Postgres) /
  `PRAGMA query_only` (SQLite); `--suggest-index` with `--verify` on local/demo only.
- pytest suite + ruff + GitHub Actions (Python 3.10–3.13 + Postgres 16 job).
- `examples/demo_fastapi/`: FastAPI + SQLAlchemy 2.x demo with N+1, missing-index, and batch-insert
  scenarios; `make reproduce` / `make reproduce-sqlite`.
- CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1), SECURITY.

### Changed
- Removed non-reproducible `92.3% | 13.07x` claim from README; numbers must come from
  `make reproduce` logs.

### Fixed
- Mixed PT/EN CLI strings unified behind i18n.

## [0.1.0] — TBD

Release notes will be finalized when Rafael merges `feat/phase0-python-mvp` and tags `v0.1.0`.
