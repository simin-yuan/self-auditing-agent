#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gatecheck —— 你的门禁真的会拦吗？

第一性原理：
    一个校验器/门禁/linter/测试套件，最常见的失败不是"有 bug"，
    而是 **它从来没拦过任何东西，却让所有人以为有它兜底**。
    你以为 CI 绿是因为代码干净；也可能是因为那条检查根本没生效。

    要证明一个门禁有效，唯一的方法不是看它通过，
    而是 **给它一份必须被拒绝的输入，看它敢不敢说不**。

    gatecheck 把这件事自动化：它对你的输入做 N 种变异，
    每个变异单独跑一次你的门禁，如实报告哪些变异被拦住了、哪些漏了。

    它不替你判断"漏掉的是不是真盲区"——它只把你从
    "我以为我的门禁很严" 变成 "我知道它漏了这 8 种情况"。

用法：
    gatecheck --gate "python validate.py {target}" --target ./data
    gatecheck --gate "pytest -q {target}" --target ./fixtures --workdir . --workers 4

退出码：
    0 = 所有变异都被拦住（门禁无可见盲区）
    1 = 存在未被拦住的变异（全部写入 --report 供人复查）
    2 = 用法/环境错误
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

# 只对文本文件做变异；这些扩展名之外的跳过。
TEXT_EXT = {
    ".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".sql", ".py", ".js", ".ts", ".java", ".kt", ".go", ".rs",
    ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sh", ".xml", ".html", ".properties",
}

# 二进制/体积护栏
MAX_FILE_BYTES = 512 * 1024


# --------------------------------------------------------------------------
# 变异算子：每个算子接收"一份文件列表 -> {相对路径: 文本}"，产出一批变异体。
# 每个变异体是一个 {相对路径: 新文本} 的完整快照（相对 base 的覆盖）。
# 算子的设计原则：**它产出的输入应当是"明显有问题"的**——
# 如果门禁对此毫无反应，那就值得人看一眼。
# --------------------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _join(lines) -> str:
    return "".join(lines)


def op_drop_file(files: dict[str, str]):
    """删掉整个文件。绝大多数门禁应当立刻报错。"""
    for rel in sorted(files):
        yield (f"drop-file:{rel}", {rel: None})  # None = 删除


def op_empty_file(files: dict[str, str]):
    """把文件清空。"""
    for rel, txt in sorted(files.items()):
        if txt.strip():
            yield (f"empty-file:{rel}", {rel: ""})


def op_drop_section(files: dict[str, str]):
    """删掉一个 markdown '## ' 段 / YAML-INI 的一个顶层键块。"""
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
            if j - i >= 2:  # 至少有个键+值才算一个块
                yield (f"drop-section:{rel}#{_snippet(lines[i])}",
                       {rel: _join(lines[:i] + lines[j:])})


def op_drop_line(files: dict[str, str]):
    """逐行删除（只删非空行，避免全是无意义的删空行）。"""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            if l.strip() and not l.lstrip().startswith("#") and not l.lstrip().startswith("//"):
                yield (f"drop-line:{rel}:{i+1}:{_snippet(l)}",
                       {rel: _join(lines[:i] + lines[i + 1:])})


def op_blank_value(files: dict[str, str]):
    """把 `key: value` 的值清空，制造"字段在但没填"。"""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            m = re.match(r"^(\s*[A-Za-z_][\w.\-]*\s*[:=]\s*)(\S.*?)(\s*)$", l)
            if m and m.group(2).strip():
                yield (f"blank-value:{rel}:{i+1}:{m.group(1).strip()}",
                       {rel: _join(lines[:i] + [m.group(1) + "\n"] + lines[i + 1:])})


def op_break_reference(files: dict[str, str]):
    """把标识符改掉一个字符，制造悬空引用/未定义 id。
    这是最容易漏的一类：引用关系断了但语法完全合法。"""
    for rel, txt in sorted(files.items()):
        for m in re.finditer(r"\b([A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+)\b", txt):
            tok = m.group(1)
            broken = tok[:-1] + ("Z" if tok[-1] != "Z" else "Y")
            if broken == tok:
                continue
            yield (f"break-ref:{rel}:{tok}->{broken}",
                   {rel: txt.replace(tok, broken, 1)})


def op_dup_id(files: dict[str, str]):
    """把第一个 id 复制一份，制造重复定义。"""
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
    """把 baseline 复制到 work，再套上 patch。patch 里值为 None 表示删除文件。"""
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
        return -9, f"[gatecheck] 门禁超时（{timeout}s）"
    except OSError as e:
        return -1, f"[gatecheck] 门禁无法启动：{e}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gatecheck",
        description="你的门禁真的会拦吗？自动变异输入，逐条撞门禁，报告它漏在哪。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  gatecheck --gate \"python validate.py {target}\" --target ./data\n"
               "  gatecheck --gate \"pytest -q {target}\" --target ./fixtures --timeout 60\n")
    ap.add_argument("--gate", required=True,
                    help="你的门禁命令。用 {target} 占位变异后的输入路径。")
    ap.add_argument("--target", required=True, help="基线输入目录（必须是通过门禁的）。")
    ap.add_argument("--workdir", default=".", help="跑门禁时的工作目录（默认当前目录）。")
    ap.add_argument("--timeout", type=int, default=120, help="每次门禁运行的超时秒数。")
    ap.add_argument("--workers", type=int, default=4, help="并行度（默认 4）。")
    ap.add_argument("--limit", type=int, default=None, help="最多生成多少个变异（调试用）。")
    ap.add_argument("--report", default="gatecheck-report.json", help="报告输出路径。")
    ap.add_argument("--keep", action="store_true", help="保留未被拦住的变异体供人工复查。")
    ap.add_argument("--version", action="version", version=f"gatecheck {__version__}")
    a = ap.parse_args(argv)

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"[错误] --target 不是目录：{target}", file=sys.stderr)
        return 2

    base = collect(target)
    if not base:
        print(f"[错误] {target} 下没有可变异文本文件", file=sys.stderr)
        return 2

    print("=" * 70)
    print("gatecheck —— 你的门禁真的会拦吗？")
    print("=" * 70)
    print(f"基线输入 : {target}  ({len(base)} 个文件)")

    # 步骤 0：先确认基线本身是"通过"的。基线都过不了的检查没有意义。
    with tempfile.TemporaryDirectory(prefix="gatecheck-") as tmp:
        tmpd = Path(tmp)
        dummy = tmpd / "baseline-input"
        apply_mutant(target, dummy, {})
        rc0, out0 = run_gate(a.gate, dummy, Path(a.workdir).resolve(), a.timeout)
    print(f"基线判定 : 退出码 {rc0}  "
          f"{'✅ 通过（基线干净，可以开始变异）' if rc0 == 0 else '⚠️ 基线就没过 —— 下面的结果不可信'}")
    if rc0 != 0:
        print("\n  基线输出前 400 字：")
        for l in out0.splitlines()[:12]:
            print("   ", l[:160])
        print("\n  提示：一个连干净输入都拒绝的门禁，测不出东西。先把它调到基线通过。")

    mutants = build_mutants(base, a.limit)
    if not mutants:
        print("[错误] 没有生成任何变异 —— 输入结构可能太简单。", file=sys.stderr)
        return 2
    print(f"变异总数 : {len(mutants)}")
    print(f"门禁命令 : {a.gate}\n")
    print("-" * 70)

    caught, missed, errors = [], [], []

    def one(item):
        name, patch = item
        wd = tmp_root / f"m{abs(hash(name)) % 10**9}"
        try:
            apply_mutant(target, wd, patch)
            rc, out = run_gate(a.gate, wd, Path(a.workdir).resolve(), a.timeout)
            return (name, rc, out, patch)
        except Exception as e:  # 变异体自身构造失败不该让整轮挂掉
            return (name, None, str(e), patch)

    with tempfile.TemporaryDirectory(prefix="gatecheck-mut-") as tmpm:
        tmp_root = Path(tmpm)
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for name, rc, out, patch in ex.map(one, mutants):
                if rc is None:
                    errors.append((name, out))
                    tag = "构建失败"
                elif rc != 0:
                    caught.append((name, rc, out))
                    tag = "拦住 ✔"
                else:
                    missed.append((name, out))
                    tag = "★ 漏过"
                print(f"  {tag:>8}  {name}")

    total = len(caught) + len(missed)
    print("-" * 70)
    print(f"拦住 {len(caught)} / {total}"
          + (f"   构建失败 {len(errors)}" if errors else ""))

    if missed:
        print(f"\n未被拦住的变异（{len(missed)} 个）—— 这些就是你门禁的可见盲区：")
        for name, _ in missed:
            print(f"  ★  {name}")
        print("\n  注意：并非每个漏过都等于缺陷 —— 有些变异在语义上是合法的。")
        print("  但每一行都值得你回答一句：这种情况发生了，我的门禁为什么不管？")

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
    print(f"\n报告已写入：{a.report}")

    if a.keep and missed:
        keepdir = Path("gatecheck-missed")
        keepdir.mkdir(exist_ok=True)
        by_name = dict(mutants)
        for n, _ in missed:
            d = keepdir / re.sub(r"[^A-Za-z0-9_.-]+", "_", n)[:80]
            apply_mutant(target, d, by_name[n])
        print(f"漏过的变异体已保留在：{keepdir}/")

    print("=" * 70)
    if rc0 != 0:
        print("结论：基线没过，本轮结果不能作为门禁有效性的证据。")
        return 1
    if missed:
        print(f"结论：门禁对 {len(missed)}/{total} 个变异无反应 —— 它有可见盲区。")
        return 1
    print(f"结论：{total} 个变异全部被拦住 —— 这轮没找到盲区。")
    print("      （这仍不等于'门禁正确'，只等于'在这组变异下它都说不'。）")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
