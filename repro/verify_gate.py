#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证明「门禁能说不」。

这是本档案里最容易说得漂亮、最难证明的一条原则：

    不能输出否定的判据，不算判据。

所以这里不去展示"校验器跑通了"，而是**故意喂给它一份违规的输入**，然后
检查它是否真的报错、真的以非零码退出。跑不出 ERROR 的门禁，不叫门禁。

同时统计【命中了多少类规则】—— 只报一两条规则的校验器，覆盖面是假的。

用法：
    python repro/verify_gate.py
退出码：
    0 = 门禁确实能说不（且规则覆盖面达标）
    1 = 门禁没能说不，或覆盖不足 —— 这个仓库的原则是假的
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(HERE, "validate_meta_model.py")
BROKEN = os.path.join(HERE, "fixtures", "broken-meta-model")
BROKEN_SRC = os.path.join(HERE, "fixtures", "broken-source")

# 这份 fixture 是照着 25 类规则【逐条设计成违规】的。
# 低于这个数说明校验器漏了规则类别，不是 fixture 不够坏。
MIN_RULE_KINDS = 19


def main() -> int:
    for p in (VALIDATOR, BROKEN, BROKEN_SRC):
        if not os.path.exists(p):
            print(f"[错误] 缺少 {p}")
            return 1

    print("[1/3] 用【故意违规】的输入跑校验器")
    print(f"      输入: {os.path.relpath(BROKEN, os.path.dirname(HERE))}")
    print(f"      源码: {os.path.relpath(BROKEN_SRC, os.path.dirname(HERE))}")
    r = subprocess.run(
        [sys.executable, VALIDATOR, BROKEN, "--source", BROKEN_SRC, "--allow-missing-optional"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(f"      退出码 = {r.returncode}（非零 = 门禁说了不）")

    print("\n[2/3] 检查它到底报了什么")
    m = re.search(r"ERROR:\s*(\d+)", out)
    warn = re.search(r"WARNING:\s*(\d+)", out)
    errors = int(m.group(1)) if m else 0
    warnings = int(warn.group(1)) if warn else 0
    kinds = sorted(set(re.findall(r"\|\s*ERROR\s*\|\s*([a-z0-9-]+)\s*\|", out)))
    print(f"      ERROR={errors}  WARNING={warnings}  命中的规则类别={len(kinds)}")

    print("\n      命中的规则类别：")
    for k in kinds:
        print(f"        - {k}")

    print("\n[3/3] 判定")
    ok_exit = r.returncode != 0
    ok_errors = errors > 0
    ok_kinds = len(kinds) >= MIN_RULE_KINDS

    print(f"      {'✅' if ok_exit else '❌'} 门禁以非零码退出")
    print(f"      {'✅' if ok_errors else '❌'} 报出 ERROR > 0")
    print(f"      {'✅' if ok_kinds else '❌'} 规则覆盖 ≥ {MIN_RULE_KINDS} 类（实得 {len(kinds)}）")

    good = ok_exit and ok_errors and ok_kinds
    print("\n" + "=" * 62)
    if good:
        print("门禁能说不 —— 这条原则有机器托底，不是文案。")
    else:
        print("门禁没能说不 —— 本仓库关于验证的主张不成立。")
    print("=" * 62)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
