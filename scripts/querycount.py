#!/usr/bin/env python3
"""Thin wrapper — prefer `dbro-querycount` after install. Keeps `python scripts/querycount.py` working."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db_route_optimizer.querycount import main

if __name__ == "__main__":
    main()
