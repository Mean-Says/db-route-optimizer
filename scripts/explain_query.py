#!/usr/bin/env python3
"""Thin wrapper — prefer `dbro-explain` after install. Keeps `python scripts/explain_query.py` working."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db_route_optimizer.explain_query import main

if __name__ == "__main__":
    main()
