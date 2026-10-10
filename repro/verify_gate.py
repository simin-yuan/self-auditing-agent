#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prove the gate moves in **both** directions.

A gate that only ever says "yes" is useless.
A gate that only ever says "no" is **equally** useless -- you cannot tell a
strict validator from a broken one, because both reject everything.

So this script makes two symmetric assertions:

    (1) a deliberately violating input -> the gate must exit non-zero, report
        ERRORs, and fire at least 19 rule families
    (2) a minimal legal input          -> the gate must exit 0, with 0 ERROR
        and 0 WARNING

If either one fails, this repository's claim about verifiability fails, and the
exit code is non-zero.

Usage:
    python repro/verify_gate.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(HERE, "validate_meta_model.py")
FIX = os.path.join(HERE, "fixtures")
BROKEN = os.path.join(FIX, "broken-meta-model")
BROKEN_SRC = os.path.join(FIX, "broken-source")
VALID = os.path.join(FIX, "valid-meta-model")
VALID_SRC = os.path.join(FIX, "valid-source")

# This fixture is designed rule by rule to violate the spec.
# Below this number the validator is missing rule families -- it is not that the
# fixture is insufficiently broken.
MIN_RULE_KINDS = 19


def run(target: str, source: str) -> tuple[int, str]:
    cmd = [sys.executable, VALIDATOR, target, "--source", source]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def counts(out: str) -> tuple[int, int]:
    def grab(sev: str) -> int:
        m = re.search(rf"^- {sev}: (\d+)", out, re.M)
        return int(m.group(1)) if m else -1
    return grab("ERROR"), grab("WARNING")


def main() -> int:
    print("=" * 64)
    print("gate health check: it must be able to say no, and to say yes")
    print("=" * 64)

    ok = True

    # -- direction (1): what should be rejected must be rejected
    print("\n[1/2] a deliberately violating input -- the gate must say no")
    rc, out = run(BROKEN, BROKEN_SRC)
    err, warn = counts(out)
    kinds = sorted({m.group(1) for m in re.finditer(r"^\|\s*ERROR\s*\|\s*([a-z][a-z0-9-]+)\s*\|", out, re.M)})
    print(f"      exit code={rc}  ERROR={err}  WARNING={warn}  rule families fired={len(kinds)}")

    if rc == 0:
        print("      FAIL the gate returned 0 on a violating input -- it will not say no")
        ok = False
    else:
        print("      ok   exited non-zero")
    if err <= 0:
        print("      FAIL no ERROR was reported")
        ok = False
    else:
        print("      ok   reported ERROR")
    if len(kinds) < MIN_RULE_KINDS:
        print(f"      FAIL insufficient rule coverage: {len(kinds)} < {MIN_RULE_KINDS}")
        ok = False
    else:
        print(f"      ok   coverage of at least {MIN_RULE_KINDS} rule families")

    # -- direction (2): what should pass must pass
    print("\n[2/2] a minimal legal input -- the gate must say yes (no false positives)")
    rc2, out2 = run(VALID, VALID_SRC)
    err2, warn2 = counts(out2)
    print(f"      exit code={rc2}  ERROR={err2}  WARNING={warn2}")

    if rc2 != 0 or err2 != 0 or warn2 != 0:
        print("      FAIL the gate rejected a legal input -- it only says no, which means it is broken (or the fixture is no longer legal)")
        for line in out2.splitlines():
            if "| ERROR" in line or "| WARNING" in line:
                print("        ", line[:150])
        print("      hint: run `python repro/fixtures/make_valid.py` to rebuild the legal baseline.")
        ok = False
    else:
        print("      ok   legal input passes with 0 ERROR / 0 WARNING")

    print("\n" + "=" * 64)
    if ok:
        print("The gate can say no and can say yes -- both symmetric pieces of evidence are present, so the claim holds.")
        print('(Note: that is still not "the gate is correct". It only means "it behaves correctly on these two inputs".)')
        return 0
    print("The gate health check failed -- this repository's claim about verification does not hold.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
