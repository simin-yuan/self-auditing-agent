#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gatecheck -- does your gate actually reject anything?

First principles:
    The most common way a validator, a gate, a linter or a test suite fails is
    not "it has a bug". It is that **it never rejected anything, while everyone
    assumed it was covering them**. CI is green because your code is clean -- or
    because that check never ran at all.

    The only way to show a gate works is not to watch it pass, but to **hand it
    an input that must be rejected and see whether it dares say no.**

    gatecheck automates that: it produces N mutations of your input, runs your
    gate once per mutation, and reports honestly which mutations were caught and
    which slipped through.

    It does not decide for you whether a survivor is a real blind spot. It only
    moves you from "I think my gate is strict" to "I know it missed these 8
    cases".

Usage:
    gatecheck --gate "python validate.py {target}" --target ./data
    gatecheck --gate "pytest -q {target}" --target ./fixtures --workdir . --workers 4

Exit codes:
    0 = every mutation was caught (no visible blind spot in the gate)
    1 = some mutations were not caught (all of them written to --report for review)
    2 = usage or environment error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

__version__ = "1.0.0"

# Only text files are mutated; anything with another extension is skipped.
TEXT_EXT = {
    ".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".sql", ".py", ".js", ".ts", ".java", ".kt", ".go", ".rs",
    ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sh", ".xml", ".html", ".properties",
}

# Binary / size guard
MAX_FILE_BYTES = 512 * 1024


# --------------------------------------------------------------------------
# Mutation operators: each takes "a file list -> {relpath: text}" and yields
# mutants. A mutant is a complete snapshot (a {relpath: new text} overlay on the
# baseline). The design rule for an operator: **the input it produces should be
# obviously wrong** -- if the gate has no reaction to it, that is worth a look.
# --------------------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _join(lines) -> str:
    return "".join(lines)


def op_drop_file(files: dict[str, str]):
    """Delete a whole file. Almost every gate should error out immediately."""
    for rel in sorted(files):
        yield (f"drop-file:{rel}", {rel: None})  # None = delete


def op_empty_file(files: dict[str, str]):
    """Empty a file."""
    for rel, txt in sorted(files.items()):
        if txt.strip():
            yield (f"empty-file:{rel}", {rel: ""})


def op_drop_section(files: dict[str, str]):
    """Delete one markdown '## ' section / one top-level YAML-INI key block."""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        heads = [i for i, l in enumerate(lines)
                 if re.match(r"^#{1,3}\s+\S", l) or re.match(r"^[A-Za-z_][\w.\-]*\s*:", l)]
        for i in heads:
            j = i + 1
            while j < len(lines) and not (
                re.match(r"^#{1,3}\s+\S", lines[j]) or re.match(r"^[A-Za-z_][\w.\-]*\s*:", lines[j])
            ):
                j += 1
            if j - i >= 2:  # a key plus a value is the minimum for a block
                yield (f"drop-section:{rel}#{_snippet(lines[i])}",
                       {rel: _join(lines[:i] + lines[j:])})


def op_drop_line(files: dict[str, str]):
    """Delete one line at a time (non-blank lines only, to avoid meaningless hits)."""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            if l.strip() and not l.lstrip().startswith("#") and not l.lstrip().startswith("//"):
                yield (f"drop-line:{rel}:{i+1}:{_snippet(l)}",
                       {rel: _join(lines[:i] + lines[i + 1:])})


def op_blank_value(files: dict[str, str]):
    """Blank out a `key: value` value, producing "the field is there but empty"."""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            m = re.match(r"^(\s*[A-Za-z_][\w.\-]*\s*[:=]\s*)(\S.*?)(\s*)$", l)
            if m and m.group(2).strip():
                yield (f"blank-value:{rel}:{i+1}:{m.group(1).strip()}",
                       {rel: _join(lines[:i] + [m.group(1) + "\n"] + lines[i + 1:])})


def op_break_reference(files: dict[str, str]):
    """Change one character of an identifier, producing a dangling reference or
    an undefined id. This is the easiest kind to miss: the relationship is gone
    but the syntax is perfectly legal."""
    for rel, txt in sorted(files.items()):
        for m in re.finditer(r"\b([A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+)\b", txt):
            tok = m.group(1)
            broken = tok[:-1] + ("Z" if tok[-1] != "Z" else "Y")
            if broken == tok:
                continue
            yield (f"break-ref:{rel}:{tok}->{broken}",
                   {rel: txt.replace(tok, broken, 1)})


def op_dup_id(files: dict[str, str]):
    """Copy the first id, producing a duplicate definition."""
    for rel, txt in sorted(files.items()):
        m = re.search(r"^#{1,3}\s+(\S+)", txt, re.M)
        if m:
            tok = m.group(1)
            yield (f"dup-id:{rel}:{tok}", {rel: txt + f"\n## {tok}\n"})


OPERATORS = [
    op_drop_file,
    op_empty_file,
    op_drop_section,
    op_drop_line,
    op_blank_value,
    op_break_reference,
    op_dup_id,
]


def _snippet(s: str, n: int = 28) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n] + "…"


# --------------------------------------------------------------------------
def collect(target: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            out[str(p.relative_to(target)).replace("\\", "/")] = p.read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def build_mutants(base: dict[str, str], limit: int | None) -> list[tuple[str, dict]]:
    mutants: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for op in OPERATORS:
        for name, patch in op(base):
            h = hashlib.sha1(repr(sorted(patch.items())).encode()).hexdigest()[:12]
            if h in seen:
                continue
            seen.add(h)
            mutants.append((name, patch))
            if limit and len(mutants) >= limit:
                return mutants
    return mutants


def apply_mutant(base_dir: Path, work: Path, patch: dict) -> None:
    """Copy the baseline into work, then apply the patch. A value of None deletes."""
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(base_dir, work)
    for rel, content in patch.items():
        fp = work / rel
        if content is None:
            if fp.exists():
                fp.unlink()
        else:
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")


def run_gate(gate: str, target: Path, workdir: Path, timeout: int):
    cmd = gate.replace("{target}", str(target))
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(workdir), timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, f"[gatecheck] gate timed out ({timeout}s)"
    except OSError as e:
        return -1, f"[gatecheck] the gate could not start: {e}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gatecheck",
        description="Does your gate actually reject anything? Mutates the input, drives every variant at the gate, reports what it misses.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  gatecheck --gate \"python validate.py {target}\" --target ./data\n"
               "  gatecheck --gate \"pytest -q {target}\" --target ./fixtures --timeout 60\n")
    ap.add_argument("--gate", required=True,
                    help="your gate command; use {target} as the placeholder for the mutated input path")
    ap.add_argument("--target", required=True, help="baseline input directory (must already pass the gate)")
    ap.add_argument("--workdir", default=".", help="working directory the gate runs in (default: current)")
    ap.add_argument("--timeout", type=int, default=120, help="timeout in seconds for each gate run")
    ap.add_argument("--workers", type=int, default=4, help="parallelism (default 4)")
    ap.add_argument("--limit", type=int, default=None, help="maximum number of mutants to build (for debugging)")
    ap.add_argument("--report", default="gatecheck-report.json", help="where to write the report")
    ap.add_argument("--keep", action="store_true", help="keep the surviving mutants on disk for manual review")
    ap.add_argument("--version", action="version", version=f"gatecheck {__version__}")
    a = ap.parse_args(argv)

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"[error] --target is not a directory: {target}", file=sys.stderr)
        return 2

    base = collect(target)
    if not base:
        print(f"[error] no mutable text files under {target}", file=sys.stderr)
        return 2

    print("=" * 70)
    print("gatecheck -- does your gate actually reject anything?")
    print("=" * 70)
    print(f"baseline input : {target}  ({len(base)} files)")

    # Step 0: confirm the baseline itself passes. A check that cannot pass a clean
    # input cannot measure anything.
    with tempfile.TemporaryDirectory(prefix="gatecheck-") as tmp:
        tmpd = Path(tmp)
        dummy = tmpd / "baseline-input"
        apply_mutant(target, dummy, {})
        rc0, out0 = run_gate(a.gate, dummy, Path(a.workdir).resolve(), a.timeout)
    print(f"baseline       : exit code {rc0}  "
          f"{'PASS (baseline is clean, starting the run)' if rc0 == 0 else 'WARN the baseline did not pass -- the results below are not trustworthy'}")
    if rc0 != 0:
        print("\n  first 400 characters of baseline output:")
        for l in out0.splitlines()[:12]:
            print("   ", l[:160])
        print("\n  Note: a gate that refuses even a clean input measures nothing. Get it passing first.")

    mutants = build_mutants(base, a.limit)
    if not mutants:
        print("[error] no mutants were generated -- the input structure is probably too simple.", file=sys.stderr)
        return 2
    print(f"mutants        : {len(mutants)}")
    print(f"gate command   : {a.gate}\n")
    print("-" * 70)

    caught, missed, errors = [], [], []

    def one(item):
        name, patch = item
        wd = tmp_root / f"m{abs(hash(name)) % 10**9}"
        try:
            apply_mutant(target, wd, patch)
            rc, out = run_gate(a.gate, wd, Path(a.workdir).resolve(), a.timeout)
            return (name, rc, out, patch)
        except Exception as e:  # a broken mutant must not take down the whole run
            return (name, None, str(e), patch)

    with tempfile.TemporaryDirectory(prefix="gatecheck-mut-") as tmpm:
        tmp_root = Path(tmpm)
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for name, rc, out, patch in ex.map(one, mutants):
                if rc is None:
                    errors.append((name, out))
                    tag = "build error"
                elif rc != 0:
                    caught.append((name, rc, out))
                    tag = "caught OK"
                else:
                    missed.append((name, out))
                    tag = "★ MISSED"
                print(f"  {tag:>11}  {name}")

    total = len(caught) + len(missed)
    print("-" * 70)
    print(f"caught {len(caught)} / {total}"
          + (f"   build errors {len(errors)}" if errors else ""))

    if missed:
        print(f"\nMutations that were not caught ({len(missed)}) -- these are the gate's visible blind spots:")
        for name, _ in missed:
            print(f"  ★  {name}")
        print("\n  Note: not every survivor is a defect -- some mutations are semantically legal.")
        print("  But every line deserves an answer: when this happened, why did my gate do nothing?")

    report = {
        "gatecheck_version": __version__,
        "gate": a.gate,
        "target": str(target),
        "baseline_exit_code": rc0,
        "baseline_ok": rc0 == 0,
        "files": len(base),
        "mutants_total": len(mutants),
        "caught": [n for n, _, _ in caught],
        "missed": [n for n, _ in missed],
        "build_errors": [n for n, _ in errors],
        "missed_detail": [{"mutant": n, "gate_output_head": o[:600]} for n, o in missed],
    }
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport written to: {a.report}")

    if a.keep and missed:
        keepdir = Path("gatecheck-missed")
        keepdir.mkdir(exist_ok=True)
        by_name = dict(mutants)
        for n, _ in missed:
            d = keepdir / re.sub(r"[^A-Za-z0-9_.-]+", "_", n)[:80]
            apply_mutant(target, d, by_name[n])
        print(f"surviving mutants kept in: {keepdir}/")

    print("=" * 70)
    if rc0 != 0:
        print("Verdict: the baseline did not pass, so this run is not evidence about the gate.")
        return 1
    if missed:
        print(f"Verdict: the gate had no reaction to {len(missed)}/{total} mutations -- it has visible blind spots.")
        return 1
    print(f"Verdict: all {total} mutations were caught -- no blind spot found in this run.")
    print("         (Still not the same as 'the gate is correct' -- only that it said no to all of these.)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
