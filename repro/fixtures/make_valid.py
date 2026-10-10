#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the **legal baseline** meta-model used by gatecheck.

Why it exists: a gate that only knows how to say "no" is as useless as a gate that
always says "yes". So this archive has to supply two symmetric pieces of evidence:
    (1) repro/fixtures/broken-meta-model  -- proves it dares to reject
    (2) repro/fixtures/valid-meta-model   -- proves it can also pass (no false positives)
Without (2) you cannot tell a strict validator from a broken one.

The corpus written into the files below stays in Chinese on purpose: the meta-model
under test is a Chinese enterprise model and the validator accepts a Chinese column
header, so translating the corpus would change what the fixture is testing.

Usage:
    python repro/fixtures/make_valid.py            # writes valid-meta-model/
    python repro/fixtures/make_valid.py --empty    # writes valid-empty/ (headings only)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# the 25 required files -> their headings
FILES = {
    "meta-index.md": "元模型索引",
    "PROGRESS.md": "进度",
    "source-asset-inventory.md": "源码资产台账",
    "source-coverage-report.md": "源码覆盖报告",
    "technical-architecture.md": "技术架构",
    "technical-component-index.md": "技术组件索引",
    "business-architecture.md": "业务架构",
    "module-index.md": "模块索引",
    "functional-inventory.md": "功能清单",
    "business-function-requirements.md": "需求面板",
    "non-menu-function-index.md": "非菜单功能",
    "function-chain-index.md": "实现链",
    "domain-model.md": "领域模型",
    "interface-index.md": "接口索引",
    "database-inventory.md": "数据库清单",
    "database-model.md": "数据库模型",
    "database-schema.md": "数据库 schema",
    "database-relations.md": "数据库关系",
    "database-access-matrix.md": "数据库访问矩阵",
    "data-ownership.md": "数据归属",
    "common-capability-index.md": "公共能力索引",
    "flow-index.md": "流程索引",
    "config-index.md": "配置索引",
    "change-hotspots.md": "变更热点",
    "consistency-report.md": "一致性报告",
}

REQ_FIELDS = [
    "Business Goal", "Actors", "Trigger Entries", "Preconditions", "Main Steps",
    "Business Rules", "Outputs And Results", "State Changes", "Failure Outcomes",
    "Manual Intervention", "Permission And Data Scope", "Implementation Chain",
]
CHAIN_SECTIONS = [
    "Requirement Link", "Identity And Entry", "Implementation Chain", "Object Roles",
    "Technical And Common Dependencies", "Physical Data Operations", "Rules And State", "Closure",
]


def write_empties(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, title in FILES.items():
        (out / name).write_text(f"# {title}\n", encoding="utf-8")


def write_full(out: Path) -> None:
    """One complete, minimal but real chain: two functions (interactive and
    non-interactive), one menu entry, one table.

    The formats follow the validator source, not guesswork:
      - definition = `- ID: <ID>` (regex in the validator, line ~186)
      - ownership  = each prefix has its own primary file (PRIMARY_FILES_BY_PREFIX)
      - panel      = 12 `- field: value` lines inside a `## FUNC-x` section
      - chain      = 8 `### section` headings inside a `## FUNC-x` section
      - non-menu   = a trigger-type word plus a JOB/EVENT/API/ENTRY reference
      - field table= a `| Physical Column |` or Chinese-header table in the schema section
    """
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    def w(name: str, body: str) -> None:
        (out / name).write_text(f"# {FILES[name]}\n\n{body}", encoding="utf-8")

    for name in FILES:
        w(name, "")

    # business architecture: menus and entries
    w("business-architecture.md",
      "- ID: MENU-M1 订单管理\n- ID: ENTRY-E1 订单维护界面\n")

    # functional inventory: definitions (- ID:) plus interaction type
    w("functional-inventory.md",
      "## FUNC-1 创建订单\n- ID: FUNC-1\n- 交互类型: interactive\n\n"
      "## FUNC-2 对账批处理\n- ID: FUNC-2\n- 交互类型: non-interactive\n")

    # requirement panels: every FUNC needs one, and all 12 fields are required
    panels = "".join(
        f"## FUNC-{n} {t}\n" + "".join(f"- {f}: 略\n" for f in REQ_FIELDS) + "\n"
        for n, t in ((1, "创建订单"), (2, "对账批处理")))
    w("business-function-requirements.md", panels)

    # implementation chains: every FUNC needs one, and all 8 sections are required
    chains = "".join(
        f"## FUNC-{n} {t}\n" + "".join(f"### {s}\n- 略\n" for s in CHAIN_SECTIONS) + "\n"
        for n, t in ((1, "创建订单"), (2, "对账批处理")))
    w("function-chain-index.md", chains)

    # non-menu function: FUNC-2 must be registered, declare a trigger type, and reference a trigger entry
    w("non-menu-function-index.md",
      "## FUNC-2 对账批处理\n- 触发类型: scheduled\n- 入口: JOB-1\n")

    # the definition for each prefix (the primary file has to be the right one)
    w("domain-model.md", "- ID: OBJ-1 订单\n")
    w("interface-index.md", "- ID: JOB-1 对账任务\n")
    w("database-model.md", "## TBL-1 订单表\n- ID: TBL-1\n")
    w("database-schema.md",
      "## TBL-1 订单表\n\n"
      "| 物理字段 | 类型 | 说明 |\n|---|---|---|\n| id | INTEGER | 主键 |\n| amount | DECIMAL | 金额 |\n")

    # source asset inventory: header row only, paired with a source stand-in that yields no assets
    w("source-asset-inventory.md",
      "| 资产 | 类型 | 说明 |\n|---|---|---|\n")


def write_source(out: Path) -> None:
    """A source stand-in that yields no routes, jobs or DDL.
    It exists so --source has a legal target while introducing no assets to register.
    Note this is **deliberately constructed**, so valid-meta-model only proves that
    "the gate does not false-positive on a minimal legal input" -- never that "the
    gate can accept a real project".
    """
    if out.exists():
        shutil.rmtree(out)
    (out / "com" / "demo").mkdir(parents=True)
    (out / "com" / "demo" / "Order.java").write_text(
        "package com.demo;\n\npublic class Order {\n    private int id;\n}\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--empty", action="store_true", help="write headings only (to probe whether an empty shell is let through)")
    a = ap.parse_args()
    out = HERE / ("valid-empty" if a.empty else "valid-meta-model")
    (write_empties if a.empty else write_full)(out)
    if not a.empty:
        write_source(HERE / "valid-source")
    n = len(list(out.glob("*.md")))
    print(f"wrote {out} ({n} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
