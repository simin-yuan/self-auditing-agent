#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证明门禁**两个方向都能动**。

一个只会说"是"的门禁没有用。
一个只会说"不"的门禁**同样**没有用 —— 你无法区分
「严格的校验器」和「坏掉的校验器」，两者都拒绝一切输入。

所以本脚本做两条对称断言：

    ① 故意违规的输入  → 门禁必须以非零码退出，且报出 ERROR，且覆盖 ≥19 类规则
    ② 合法的最小输入  → 门禁必须以 0 退出，且 ERROR/WARNING 均为 0

任何一条不成立，本仓库关于"可验证"的主张即不成立，退出码非零。

用法：
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

# 这份 fixture 是照着规则逐条设计成违规的。
# 低于这个数说明校验器漏了规则类别，不是 fixture 不够坏。
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
    print("门禁体检：它必须既能说不，也能说是")
    print("=" * 64)

    ok = True

    # ── 方向 ①：该拒绝的必须拒绝
    print("\n[1/2] 故意违规的输入 —— 门禁必须说不")
    rc, out = run(BROKEN, BROKEN_SRC)
    err, warn = counts(out)
    kinds = sorted({m.group(1) for m in re.finditer(r"^\|\s*ERROR\s*\|\s*([a-z][a-z0-9-]+)\s*\|", out, re.M)})
    print(f"      退出码={rc}  ERROR={err}  WARNING={warn}  命中规则类别={len(kinds)}")

    if rc == 0:
        print("      ❌ 门禁对违规输入返回 0 —— 它不会说不")
        ok = False
    else:
        print("      ✅ 以非零码退出")
    if err <= 0:
        print("      ❌ 没有报出任何 ERROR")
        ok = False
    else:
        print("      ✅ 报出 ERROR")
    if len(kinds) < MIN_RULE_KINDS:
        print(f"      ❌ 规则覆盖不足：{len(kinds)} < {MIN_RULE_KINDS}")
        ok = False
    else:
        print(f"      ✅ 规则覆盖 ≥{MIN_RULE_KINDS} 类")

    # ── 方向 ②：该通过的必须通过
    print("\n[2/2] 合法的最小输入 —— 门禁必须说是（不误杀）")
    rc2, out2 = run(VALID, VALID_SRC)
    err2, warn2 = counts(out2)
    print(f"      退出码={rc2}  ERROR={err2}  WARNING={warn2}")

    if rc2 != 0 or err2 != 0 or warn2 != 0:
        print("      ❌ 门禁拒绝了合法输入 —— 它只会说不，等于坏掉（或 fixture 不再合法）")
        for line in out2.splitlines():
            if "| ERROR" in line or "| WARNING" in line:
                print("        ", line[:150])
        print("      提示：可跑 `python repro/fixtures/make_valid.py` 重建合法基线。")
        ok = False
    else:
        print("      ✅ 合法输入 0 ERROR / 0 WARNING 通过")

    print("\n" + "=" * 64)
    if ok:
        print("门禁能说不、也能说是 —— 两条对称证据都在，主张成立。")
        print("（注意：这仍不等于'门禁正确'。它只等于'在这两组输入下行为正确'。）")
        return 0
    print("门禁体检未通过 —— 本仓库关于验证的主张不成立。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
