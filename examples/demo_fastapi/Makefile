# Reproducible before/after demo (protocol §3 of the project plan).
# Numbers go under runs/ and optimization_log.md — never invent them.

PYTHON ?= python3
N ?= 30
WARMUP ?= 5
PG_URL ?= postgresql://dbro:dbro@127.0.0.1:5432/dbro
SQLITE_URL ?= sqlite:///$(CURDIR)/demo.db

.PHONY: help install up down seed-sqlite seed-postgres reproduce-sqlite reproduce reproduce-postgres clean

help:
	@echo "Targets: install | up | down | reproduce-sqlite | reproduce | clean"
	@echo "Env: N=$(N) WARMUP=$(WARMUP)"

install:
	$(PYTHON) -m pip install -e '$(CURDIR)/../..[dev]'

up:
	docker compose up -d
	@echo "Waiting for Postgres..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
	  docker compose exec -T postgres pg_isready -U dbro -d dbro && break; \
	  sleep 2; \
	done

down:
	docker compose down

seed-sqlite:
	DATABASE_URL=$(SQLITE_URL) $(PYTHON) seed.py --seed 42 --database-url $(SQLITE_URL) --drop-index

seed-postgres:
	DATABASE_URL=$(PG_URL) $(PYTHON) seed.py --seed 42 --database-url $(PG_URL) --drop-index

reproduce-sqlite: install
	DATABASE_URL=$(SQLITE_URL) $(PYTHON) reproduce.py --backend sqlite --n $(N) --warmup $(WARMUP) --database-url $(SQLITE_URL)

reproduce-postgres: up install
	DATABASE_URL=$(PG_URL) $(PYTHON) reproduce.py --backend postgres --n $(N) --warmup $(WARMUP) --database-url $(PG_URL)

# Full DoD path: Postgres (docker) + SQLite
reproduce: reproduce-postgres reproduce-sqlite
	@echo "Done. See optimization_log.md and runs/"

clean:
	rm -f demo.db
	rm -rf runs/*/run-*.json
