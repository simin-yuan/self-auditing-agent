#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate runner for the guardrails-ai repro.

Lives OUTSIDE the mutated directory on purpose: the gate must stay fixed while
the guard definition next to it changes.

    python runner.py <target-dir>

exit 0 -> every rule in rail.xml accepted the answer in output_valid.txt
exit 1 -> a rule fired, or the RAIL spec / registry could not be built
"""
from __future__ import annotations

import importlib.util
import logging
import pathlib
import sys

sys.dont_write_bytecode = True  # a .pyc from one mutant must not stand in for another
logging.disable(logging.CRITICAL)  # guardrails-ai is chatty


def load_registry(target: pathlib.Path):
    spec = importlib.util.spec_from_file_location(
        "target_guards", str(target / "validators.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["target_guards"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: runner.py <target-dir>", file=sys.stderr)
        return 2
    target = pathlib.Path(sys.argv[1])

    try:
        load_registry(target)
        from guardrails import Guard

        rail = (target / "rail.xml").read_text(encoding="utf-8")
        answer = (target / "output_valid.txt").read_text(encoding="utf-8")
    except Exception as exc:  # an unbuildable guard counts as a rejection
        print("REJECT (guard could not be built): %s: %s" % (type(exc).__name__, exc))
        return 1

    try:
        guard = Guard.for_rail_string(rail)
    except Exception as exc:
        print("REJECT (rail.xml is not a usable RAIL spec): %s: %s"
              % (type(exc).__name__, exc))
        return 1

    try:
        outcome = guard.validate(answer)
    except Exception as exc:
        print("REJECT (validator fired): %s: %s" % (type(exc).__name__, exc))
        return 1

    if not outcome.validation_passed:
        print("REJECT (validation_passed=False): %s" % (outcome.error,))
        return 1

    print("PASS (every rule in rail.xml accepted this answer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
