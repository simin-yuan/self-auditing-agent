#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce the pattern behind this archive's hardest finding.

The audit found this gap in a third-party open-source system: a read-only SQL
wrapper that refuses writes but keeps no table allowlist, so a caller can read
any table -- ``SELECT name FROM sqlite_master`` enumerates the entire schema.

The vulnerable pattern is reproduced here with a minimal self-written example
(`repro/fixtures/readonly-sql-pattern/readonly_sql.py`). The original measured
record is kept in a private report, so what this script proves is that the
pattern is real -- not that any particular project still carries it.

No network access, no service, no dependencies, and nothing written outside a
temporary directory.

Usage:
    python repro/verify_sql_gap.py

Exit codes:
    0 = the pattern reproduces (writes refused, an arbitrary table read allowed)
    1 = it does not (the example has been fixed, or the fixture is broken)
    2 = the fixture file is missing
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(HERE, "fixtures", "readonly-sql-pattern")
FIXTURE_FILE = os.path.join(FIXTURE_DIR, "readonly_sql.py")

PROBE = "SELECT name FROM sqlite_master"   # reads the whole schema
WRITE_PROBE = "DELETE FROM demo"           # control: a write


def make_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE demo (id TEXT PRIMARY KEY, secret TEXT)")
    conn.execute("CREATE TABLE hidden_audit_log (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO demo VALUES ('1', 'not-meant-to-be-readable')")
    conn.commit()
    return conn


def main():
    if not os.path.exists(FIXTURE_FILE):
        print("fixture not found: %s" % FIXTURE_FILE)
        return 2
    sys.path.insert(0, FIXTURE_DIR)
    import readonly_sql

    print("[1/3] self-written pattern fixture, offline, no third-party code")
    print("      %s" % os.path.relpath(FIXTURE_FILE).replace("\\", "/"))

    workdir = tempfile.mkdtemp(prefix="readonly_sql_pattern_")
    try:
        conn = make_db(os.path.join(workdir, "probe.db"))
        print("      temporary database holds 2 tables: demo, hidden_audit_log")

        print("[2/3] control: a write must be refused")
        try:
            readonly_sql.run_readonly_sql(conn, WRITE_PROBE)
            print("      FAIL the write went through")
            write_blocked = False
        except readonly_sql.ReadOnlyViolation as exc:
            print("      ok   refused: %s" % exc)
            write_blocked = True

        print("[3/3] probe: reading an arbitrary table")
        try:
            _cols, rows = readonly_sql.run_readonly_sql(conn, PROBE)
            print("      ALLOWED, %d tables readable:" % len(rows))
            for row in rows:
                print("          - %s" % dict(row))
            leaked = True
        except readonly_sql.ReadOnlyViolation as exc:
            print("      refused: %s" % exc)
            leaked = False

        print()
        print("=" * 62)
        if leaked and write_blocked:
            print("Pattern reproduces. The guard stops writes but not arbitrary reads: a")
            print("read-only SQL path with no table allowlist lets the caller enumerate")
            print("the schema. (Fix direction: derive the allowlist from the model layer")
            print("and apply it to plain reads, joins and comma-joins alike.)")
            code = 0
        elif not leaked:
            print("Pattern does not reproduce: the example now refuses arbitrary reads.")
            print("Treat the finding as fixed and update the archive.")
            code = 1
        else:
            print("Unexpected: the write control was not refused, so this run proves nothing.")
            code = 1
        print("=" * 62)

        conn.close()
        return code
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
