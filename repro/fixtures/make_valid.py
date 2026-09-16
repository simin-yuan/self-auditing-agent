#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成用于 gatecheck 的**合法基线**元模型。

存在理由：一个门禁如果只会说"不"，它和一个永远说"是"的门禁一样无用。
所以本档案必须同时提供两条对称证据：
    ① repro/fixtures/broken-meta-model  —— 证明它敢拒绝
    ② repro/fixtures/valid-meta-model    —— 证明它也能通过（不误杀）
少了 ②，你无法区分"严格的校验器"和"坏掉的校验器"。

用法：
    python repro/fixtures/make_valid.py            # 生成 valid-meta-model/
    python repro/fixtures/make_valid.py --empty    # 生成 valid-empty/（只有标题）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 25 个必需文件 → 标题
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
    """一条完整的、最小但真实的链路：两个功能（交互+非交互）、一次菜单入口、一张表。

    格式依据校验器源码，不是猜的：
      · 定义   = `- ID: <ID>`（正则 ^\\s*-\\s*ID:\\s*(...)，行 186）
      · 归属   = 每个前缀有自己的主文件（PRIMARY_FILES_BY_PREFIX，行 76）
      · 面板   = `## FUNC-x` 段内 12 个 `- 字段: 值`（行 266）
      · 实现链 = `## FUNC-x` 段内 8 个 `### 小节`（行 272）
      · 非菜单 = 段内出现触发类型词 + 引用 JOB/EVENT/API/ENTRY（行 282 / 289）
      · 字段表 = schema 段内含 `| 物理字段 |` 或 `| Physical Column |`（行 314）
    """
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    def w(name: str, body: str) -> None:
        (out / name).write_text(f"# {FILES[name]}\n\n{body}", encoding="utf-8")

    for name in FILES:
        w(name, "")

    # 业务架构：菜单与入口
    w("business-architecture.md",
      "- ID: MENU-M1 订单管理\n- ID: ENTRY-E1 订单维护界面\n")

    # 功能清单：定义（- ID:）+ 交互类型
    w("functional-inventory.md",
      "## FUNC-1 创建订单\n- ID: FUNC-1\n- 交互类型: interactive\n\n"
      "## FUNC-2 对账批处理\n- ID: FUNC-2\n- 交互类型: non-interactive\n")

    # 需求面板：每个 FUNC 都要有，且 12 个字段一个不能少
    panels = "".join(
        f"## FUNC-{n} {t}\n" + "".join(f"- {f}: 略\n" for f in REQ_FIELDS) + "\n"
        for n, t in ((1, "创建订单"), (2, "对账批处理")))
    w("business-function-requirements.md", panels)

    # 实现链：每个 FUNC 都要有，8 个小节一个不能少
    chains = "".join(
        f"## FUNC-{n} {t}\n" + "".join(f"### {s}\n- 略\n" for s in CHAIN_SECTIONS) + "\n"
        for n, t in ((1, "创建订单"), (2, "对账批处理")))
    w("function-chain-index.md", chains)

    # 非菜单功能：FUNC-2 要登记 + 声明触发类型 + 引用触发入口
    w("non-menu-function-index.md",
      "## FUNC-2 对账批处理\n- 触发类型: scheduled\n- 入口: JOB-1\n")

    # 各前缀的定义（主文件不能错）
    w("domain-model.md", "- ID: OBJ-1 订单\n")
    w("interface-index.md", "- ID: JOB-1 对账任务\n")
    w("database-model.md", "## TBL-1 订单表\n- ID: TBL-1\n")
    w("database-schema.md",
      "## TBL-1 订单表\n\n"
      "| 物理字段 | 类型 | 说明 |\n|---|---|---|\n| id | INTEGER | 主键 |\n| amount | DECIMAL | 金额 |\n")

    # 源码资产台账：留表头，配合一个"扫不出任何资产"的源码替身
    w("source-asset-inventory.md",
      "| 资产 | 类型 | 说明 |\n|---|---|---|\n")


def write_source(out: Path) -> None:
    """一个扫不出任何路由/任务/DDL 的源码替身。

    它存在的意义：让 --source 有合法指向，同时不引入任何待登记资产。
    注意这是**刻意构造**的，所以 valid-meta-model 只能证明
    「门禁不误杀最小合法输入」，不能证明「门禁能验收真实项目」。
    """
    if out.exists():
        shutil.rmtree(out)
    (out / "com" / "demo").mkdir(parents=True)
    (out / "com" / "demo" / "Order.java").write_text(
        "package com.demo;\n\npublic class Order {\n    private int id;\n}\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--empty", action="store_true", help="只生成标题（用于探测空壳是否被放行）")
    a = ap.parse_args()
    out = HERE / ("valid-empty" if a.empty else "valid-meta-model")
    (write_empties if a.empty else write_full)(out)
    if not a.empty:
        write_source(HERE / "valid-source")
    n = len(list(out.glob("*.md")))
    print(f"已生成 {out}（{n} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
