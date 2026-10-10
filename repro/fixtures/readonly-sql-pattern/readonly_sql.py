#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A read-only SQL wrapper that reproduces a gap found in a third-party system.

This file is NOT anyone's code. It is a small, self-written example of a pattern
observed while auditing a third-party open-source system:

    the wrapper enforces "read-only" by rejecting statements that *write*, but
    it never restricts *which tables may be read*.

That is an incomplete guard rather than a missing one, which is exactly why it
passes review. The consequence is that any caller can run
``SELECT name FROM sqlite_master`` and enumerate the whole schema, including
tables the caller was never meant to see.

The original measured record is kept in a private report. What is reproduced
here is the pattern, so that the claim in this archive has something runnable
behind it that needs no network access and no third-party code.
"""
from __future__ import annotations

import re

# Statements that must never reach the database through a read-only path.
WRITE_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "replace", "attach", "detach", "pragma", "vacuum", "reindex",
)

_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


class ReadOnlyViolation(ValueError):
    """Raised when a statement is refused."""


def _strip_comments(sql: str) -> str:
    return _COMMENTS.sub(" ", sql).strip().rstrip(";").strip()


def run_readonly_sql(conn, sql, params=()):
    """Run *sql* if it looks read-only, and return ``(columns, rows)``.

    Writes are refused. Reads are **not** restricted by table name -- that is
    the gap this fixture exists to demonstrate.
    """
    text = _strip_comments(sql)
    if not text:
        raise ReadOnlyViolation("empty statement")
    if ";" in text:
        raise ReadOnlyViolation("multiple statements are not allowed")

    lowered = text.lower()
    if not lowered.startswith(("select", "with")):
        raise ReadOnlyViolation("only SELECT is allowed, got: %r" % text[:40])
    for keyword in WRITE_KEYWORDS:
        if re.search(r"\b%s\b" % keyword, lowered):
            raise ReadOnlyViolation("keyword %r is not allowed" % keyword)

    cur = conn.execute(text, params)
    columns = [d[0] for d in (cur.description or ())]
    return columns, cur.fetchall()
