#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元模型文档集对账校验（PowerShell 版的 Python 完整移植）

## 出处
逐行移植自 `codebase-reverse/scripts/validate_meta_model.ps1`（416 行，原文全读）。
无需 PowerShell，跨平台可跑；规则**一条不减**。

## 移植的规则清单（与原脚本的 issue type 一一对应）

| 原 issue type                   | 严重级 | 说明 |
|--------------------------------|--------|------|
| missing-file                   | ERROR  | 25 份必需文档缺一即错（`--allow-missing-optional` 时 consistency-report.md 降为 WARNING） |
| missing-source-path            | ERROR  | 未提供 `--source` 时无法校验完整性（`--allow-missing-optional` 降 WARNING） |
| invalid-source-path            | ERROR  | source 目录不存在 |
| definition-in-wrong-file       | ERROR  | ID 主定义必须落在该类 ID 的指定文件里（23 类前缀映射） |
| duplicate-definition           | ERROR  | 同一 ID 有多个主定义 |
| undefined-id                   | ERROR  | 被引用但从未定义 |
| dead-link                      | ERROR  | Markdown 链接目标不存在 |
| dead-anchor                    | ERROR  | 链接锚点在目标文件中不存在 |
| missing-requirement-panel      | ERROR  | 功能无需求面板 |
| missing-function-chain         | ERROR  | 功能无实现链 |
| orphan-requirement-panel       | ERROR  | 需求面板无对应功能定义 |
| orphan-function-chain          | ERROR  | 实现链无对应功能定义 |
| incomplete-requirement-panel   | ERROR  | 需求面板缺 12 个必填字段之一 |
| incomplete-function-chain      | ERROR  | 实现链缺 8 个必备 ### 小节之一 |
| missing-non-menu-index         | ERROR  | 非交互功能未登记进 non-menu-function-index.md |
| orphan-non-menu-function       | ERROR  | 非菜单功能未在 functional-inventory.md 定义 |
| missing-trigger-type           | ERROR  | 非菜单功能未声明可识别的触发类型 |
| missing-trigger-entry          | ERROR  | 非菜单功能未引用 JOB/EVENT/API/ENTRY 触发入口 |
| missing-table-schema           | ERROR  | 物理表无 schema 章节 |
| orphan-table-schema            | ERROR  | schema 章节无 database-model 定义 |
| missing-field-table            | ERROR  | schema 章节缺字段表（`| Physical Column |` 或 `| 物理字段 |`） |
| unregistered-source-asset      | ERROR  | 入口/DAO/模型类源文件未登记进台账 |
| unregistered-source-entry      | ERROR  | 请求路由字面量未登记进台账 |
| unregistered-source-trigger    | ERROR  | Job/事件监听字面量未登记进台账 |
| unregistered-database-object   | ERROR  | DDL 对象名未登记进台账 |

**⚠️ 极限（原脚本作者自己也承认）**：这是**字符串存在性检查，不是语义校验**。
它挡不住「台账里编条目」，也不校验语义正确性。**不要对客户宣称「完整逆向」。**

用法：
    python validators/validate_meta_model.py <meta-model目录> [--source <源码目录>] \\
           [--report out/consistency-report.md] [--allow-missing-optional] [--json]
退出码：ERROR>0 → 1，否则 0
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

# ── 原脚本 $requiredFiles ──
REQUIRED_FILES = [
    "meta-index.md", "PROGRESS.md", "source-asset-inventory.md",
    "source-coverage-report.md", "technical-architecture.md",
    "technical-component-index.md", "business-architecture.md", "module-index.md",
    "functional-inventory.md", "business-function-requirements.md",
    "non-menu-function-index.md", "function-chain-index.md", "domain-model.md",
    "interface-index.md", "database-inventory.md", "database-model.md",
    "database-schema.md", "database-relations.md", "database-access-matrix.md",
    "data-ownership.md", "common-capability-index.md", "flow-index.md",
    "config-index.md", "change-hotspots.md", "consistency-report.md",
]

# ── 原脚本 $idPattern ──
ID_PATTERN = (r"(?:SYS|MOD|SVC|DOM|CAP|SCN|MENU|ENTRY|FUNC|OBJ|API|EVENT|JOB|COMP|TCAP|"
              r"COMMON|CAPI|TBL|STORE|TOPIC|CFG|RULE|Q)-[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
ID_RE = re.compile(ID_PATTERN)

# ── 原脚本 $primaryFilesByPrefix ──
PRIMARY_FILES_BY_PREFIX = {
    "SYS": ["technical-architecture.md"],
    "MOD": ["module-index.md"], "SVC": ["module-index.md"],
    "DOM": ["business-architecture.md"], "CAP": ["business-architecture.md"],
    "SCN": ["business-architecture.md"], "MENU": ["business-architecture.md"],
    "ENTRY": ["business-architecture.md"],
    "FUNC": ["functional-inventory.md"],
    "OBJ": ["domain-model.md"], "RULE": ["domain-model.md"],
    "API": ["interface-index.md"], "EVENT": ["interface-index.md"], "JOB": ["interface-index.md"],
    "COMP": ["technical-component-index.md"], "TCAP": ["technical-component-index.md"],
    "COMMON": ["common-capability-index.md"], "CAPI": ["common-capability-index.md"],
    "TBL": ["database-model.md"], "STORE": ["database-model.md"], "TOPIC": ["database-model.md"],
    "CFG": ["config-index.md"],
    "Q": ["PROGRESS.md"],
}

REQUIRED_REQUIREMENT_FIELDS = [
    "Business Goal", "Actors", "Trigger Entries", "Preconditions", "Main Steps",
    "Business Rules", "Outputs And Results", "State Changes", "Failure Outcomes",
    "Manual Intervention", "Permission And Data Scope", "Implementation Chain",
]
REQUIRED_CHAIN_SECTIONS = [
    "Requirement Link", "Identity And Entry", "Implementation Chain", "Object Roles",
    "Technical And Common Dependencies", "Physical Data Operations", "Rules And State", "Closure",
]
NON_MENU_TRIGGER_TYPES = [
    "scheduled", "event-consumer", "webhook-callback", "api-only", "batch-file",
    "startup-lifecycle", "polling", "cdc-data-change", "retry-compensation", "cli-ops",
]

SOURCE_EXTENSIONS = {".java", ".kt", ".cs", ".js", ".jsx", ".ts", ".tsx", ".py", ".go",
                     ".php", ".rb", ".xml", ".sql", ".yml", ".yaml", ".properties", ".gradle"}
EXCLUDED_PATH_RE = re.compile(r"(?i)(^|/)(node_modules|vendor|build|dist|target|bin|obj|\.git|coverage)(/|$)")

ISSUES: list[dict[str, str]] = []


def add(severity: str, itype: str, target: str, message: str) -> None:
    ISSUES.append({"severity": severity, "type": itype, "target": target, "message": message})


# ── 原脚本 Get-MarkdownAnchors ──
def md_anchors(content: str) -> set[str]:
    anchors: set[str] = set()
    for m in re.finditer(r'(?i)<a\s+(?:name|id)=["\']([^"\']+)["\']', content):
        anchors.add(m.group(1))
    for m in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", content):
        h = m.group(1)
        h = re.sub(r"`([^`]*)`", r"\1", h)
        h = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", h)
        h = "".join(ch for ch in h if ch.isalnum() or ch in " _-")
        h = re.sub(r"\s+", "-", h.strip())
        if h:
            anchors.add(h.lower())
    return anchors


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def sections_of(content: str, id_pattern: str) -> list[tuple[str, str]]:
    """把文档按 `## ID-xxx` 切成 (id, body)。等价于原脚本的正则捕获。"""
    rx = re.compile(rf"(?ms)^#{{2,6}}\s+({id_pattern})[^\r\n]*\r?\n(.*?)(?=^#{{2,6}}\s+{id_pattern}|\Z)")
    return [(m.group(1), m.group(2)) for m in rx.finditer(content)]


def headings_of(content: str, id_pattern: str) -> list[str]:
    rx = re.compile(rf"(?m)^#{{2,6}}\s+({id_pattern})")
    return sorted({m.group(1) for m in rx.finditer(content)})


def check_structure(root: str, allow_missing_optional: bool, source_root: str | None,
                    source_path_given: bool) -> None:
    # requiredFiles
    for f in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(root, f)):
            sev = "WARNING" if (allow_missing_optional and f == "consistency-report.md") else "ERROR"
            add(sev, "missing-file", f, "Required meta-model file does not exist.")

    # missing-source-path
    if not source_path_given:
        sev = "WARNING" if allow_missing_optional else "ERROR"
        add(sev, "missing-source-path", "-SourcePath",
            "Source completeness cannot be validated without the source project path.")
    elif source_root and not os.path.isdir(source_root):
        add("ERROR", "invalid-source-path", source_root, "Source project directory does not exist.")


def check_ids_and_links(root: str) -> tuple[dict[str, list[str]], int]:
    md_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if fn.endswith(".md"):
                md_files.append(os.path.join(dirpath, fn))
    md_files.sort()

    definitions: dict[str, list[str]] = defaultdict(list)
    all_refs: list[tuple[str, str]] = []

    for path in md_files:
        content = read(path)
        rel = os.path.relpath(path, root).replace("\\", "/")

        # definition-in-wrong-file
        for m in re.finditer(rf"(?m)^\s*-\s*ID:\s*({ID_PATTERN})(?:\s|$)", content):
            ident = m.group(1)
            prefix = ident.split("-", 1)[0]
            allowed = PRIMARY_FILES_BY_PREFIX.get(prefix)
            basename = rel.split("/")[-1]
            if not allowed or basename not in allowed:
                add("ERROR", "definition-in-wrong-file", ident,
                    f"Primary definition is in {rel}; expected one of: {', '.join(allowed or ['<未知前缀>'])}.")
                continue
            definitions[ident].append(rel)

        # references
        for m in ID_RE.finditer(content):
            rid = m.group(0)
            if rid.lower().endswith(".md"):
                rid = rid[:-3]
            all_refs.append((rid, rel))

        # dead-link / dead-anchor
        for m in re.finditer(r"(?m)\[[^\]]+\]\(([^)]+)\)", content):
            raw = m.group(1).strip()
            if re.match(r"^(?:https?://|mailto:|#)", raw):
                continue
            target_no_title = re.split(r'\s+"', raw, 1)[0].strip("<>")
            parts = target_no_title.split("#", 1)
            target_file = parts[0]
            anchor = parts[1] if len(parts) > 1 else None
            if not target_file.strip():
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target_file))
            if not os.path.exists(resolved):
                add("ERROR", "dead-link", f"{rel} -> {raw}", "Markdown link target does not exist.")
            elif anchor and resolved.lower().endswith(".md"):
                if anchor not in md_anchors(read(resolved)):
                    add("ERROR", "dead-anchor", f"{rel} -> {raw}",
                        "Markdown anchor does not exist in the target file.")

    for ident, files in definitions.items():
        if len(files) > 1:
            add("ERROR", "duplicate-definition", ident,
                "ID has multiple primary definitions: " + ", ".join(sorted(set(files))))

    for ident, _ in all_refs:
        if ident not in definitions:
            files = sorted({f for r, f in all_refs if r == ident})
            add("ERROR", "undefined-id", ident,
                "Referenced without a primary definition in: " + ", ".join(files))

    return definitions, len(md_files)


def check_functions(root: str) -> tuple[list[str], int]:
    fp = os.path.join(root, "functional-inventory.md")
    rp = os.path.join(root, "business-function-requirements.md")
    nm = os.path.join(root, "non-menu-function-index.md")
    cp = os.path.join(root, "function-chain-index.md")
    if not (os.path.isfile(fp) and os.path.isfile(rp) and os.path.isfile(cp)):
        return [], 0

    f_content, r_content, c_content = read(fp), read(rp), read(cp)
    func_ids = headings_of(f_content, ID_PATTERN.replace("FUNC|", "").replace("|FUNC", "") if False else ID_PATTERN)
    funct = headings_of(f_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*")
    req = headings_of(r_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*")
    chain = headings_of(c_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*")
    _ = func_ids

    for i in funct:
        if i not in req:
            add("ERROR", "missing-requirement-panel", i, "Function has no requirement panel.")
        if i not in chain:
            add("ERROR", "missing-function-chain", i, "Function has no implementation chain.")
    for i in req:
        if i not in funct:
            add("ERROR", "orphan-requirement-panel", i,
                "Requirement panel has no functional inventory definition.")
    for i in chain:
        if i not in funct:
            add("ERROR", "orphan-function-chain", i,
                "Function chain has no functional inventory definition.")

    for ident, body in sections_of(r_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*"):
        for field in REQUIRED_REQUIREMENT_FIELDS:
            if not re.search(rf"(?im)^\s*-\s*{re.escape(field)}:\s*\S*", body):
                add("ERROR", "incomplete-requirement-panel", ident,
                    f"Missing required requirement field: {field}.")

    for ident, body in sections_of(c_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*"):
        for heading in REQUIRED_CHAIN_SECTIONS:
            if not re.search(rf"(?im)^###\s+{re.escape(heading)}\s*$", body):
                add("ERROR", "incomplete-function-chain", ident,
                    f"Missing required chain section: {heading}.")

    if os.path.isfile(nm):
        nm_content = read(nm)
        nm_ids = headings_of(nm_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*")
        for ident, body in sections_of(f_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*"):
            if re.search(r"(?im)^\s*-\s*[^:\r\n]+:\s*(?:non-interactive|hybrid)\s*$", body) \
                    and ident not in nm_ids:
                add("ERROR", "missing-non-menu-index", ident,
                    "Non-interactive or hybrid function is not present in non-menu-function-index.md.")
        for ident, body in sections_of(nm_content, "FUNC-[A-Za-z0-9][A-Za-z0-9._-]*"):
            if ident not in funct:
                add("ERROR", "orphan-non-menu-function", ident,
                    "Non-menu function is not defined in functional-inventory.md.")
            if not re.search(r"(?i)\b(?:" + "|".join(NON_MENU_TRIGGER_TYPES) + r")\b", body):
                add("ERROR", "missing-trigger-type", ident,
                    "Non-menu function does not declare a recognized trigger type.")
            if not re.search(r"(?i)\b(?:JOB|EVENT|API|ENTRY)-[A-Za-z0-9][A-Za-z0-9._-]*", body):
                add("ERROR", "missing-trigger-entry", ident,
                    "Non-menu function does not reference a JOB/EVENT/API/ENTRY trigger.")
    return funct, len(funct)


def check_database(root: str) -> None:
    mp = os.path.join(root, "database-model.md")
    sp = os.path.join(root, "database-schema.md")
    if not (os.path.isfile(mp) and os.path.isfile(sp)):
        return
    m_content, s_content = read(mp), read(sp)
    tbl = headings_of(m_content, "TBL-[A-Za-z0-9][A-Za-z0-9._-]*")
    schema = headings_of(s_content, "TBL-[A-Za-z0-9][A-Za-z0-9._-]*")
    for i in tbl:
        if i not in schema:
            add("ERROR", "missing-table-schema", i, "Physical table/view has no schema section.")
    for i in schema:
        if i not in tbl:
            add("ERROR", "orphan-table-schema", i, "Schema section has no database-model definition.")
    for ident, body in sections_of(s_content, "TBL-[A-Za-z0-9][A-Za-z0-9._-]*"):
        if not re.search(r"(?im)^\|\s*(?:Physical Column|物理字段)\s*\|", body):
            add("ERROR", "missing-field-table", ident,
                "Schema section does not contain the required field table.")


def check_source(root: str, source_root: str | None, source_path_given: bool) -> int:
    inventory_path = os.path.join(root, "source-asset-inventory.md")
    if not (source_root and os.path.isdir(source_root) and os.path.isfile(inventory_path)):
        return 0
    inv = read(inventory_path).replace("\\", "/")
    discovered = 0

    route_re = re.compile(
        r"(?s)@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\s*\((.*?)\)")
    literal_re = re.compile(r'["\']([^"\']+)["\']')
    trigger_re = re.compile(r'@(?:XxlJob|KafkaListener|RabbitListener|JmsListener)\s*\(\s*["\']([^"\']+)["\']')
    ddl_re = re.compile(
        r"(?im)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW)\s+([A-Za-z0-9_.\"`\[\]]+)")
    dao_re = re.compile(r"(?i)(Dao|Mapper|Repository)\.(java|kt|cs|ts)$")
    model_re = re.compile(r"(?i)(Entity|Model|DTO|VO|Command|Query|Event|Enum|Config)\.(java|kt|cs|ts)$")
    entry_re = re.compile(
        r"@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|XxlJob|"
        r"Scheduled|KafkaListener|RabbitListener|JmsListener|RestController|Controller)"
        r"|\b(?:app|router)\.(?:get|post|put|delete|patch)\s*\(")

    for dirpath, dirnames, filenames in os.walk(source_root):
        dirnames[:] = [d for d in dirnames if d not in
                       {"node_modules", "vendor", "build", "dist", "target", "bin", "obj", ".git", "coverage"}]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, source_root).replace("\\", "/")
            if EXCLUDED_PATH_RE.search("/" + rel):
                continue
            if os.path.splitext(fn)[1].lower() not in SOURCE_EXTENSIONS:
                continue
            content = read(path)
            if not content:
                continue
            if dao_re.search(fn) or model_re.search(fn) or entry_re.search(content):
                discovered += 1
                if rel not in inv:
                    add("ERROR", "unregistered-source-asset", rel,
                        "Entry/DAO/model source file is absent from source-asset-inventory.md.")
            for m in route_re.finditer(content):
                for lit in literal_re.finditer(m.group(1)):
                    token = lit.group(1)
                    if re.match(r"^(?:/|[A-Za-z0-9_.-]+/)", token):
                        discovered += 1
                        if not re.search(rf"(?im)\|\s*{re.escape(token)}\s*\|", inv):
                            add("ERROR", "unregistered-source-entry", f"{rel}::{token}",
                                "Request route is absent from source-asset-inventory.md.")
            for m in trigger_re.finditer(content):
                token = m.group(1)
                discovered += 1
                if not re.search(rf"(?im)\|\s*{re.escape(token)}\s*\|", inv):
                    add("ERROR", "unregistered-source-trigger", f"{rel}::{token}",
                        "Job/event trigger is absent from source-asset-inventory.md.")
            for m in ddl_re.finditer(content):
                token = m.group(1).strip('"`[]')
                discovered += 1
                if not re.search(rf"(?im)\|\s*{re.escape(token)}\s*\|", inv):
                    add("ERROR", "unregistered-database-object", f"{rel}::{token}",
                        "DDL object is absent from source-asset-inventory.md.")
    _ = source_path_given
    return discovered


def render(root: str, source_root: str | None, md_files: int, defined: int,
           funcs: int, discovered: int) -> str:
    errors = [i for i in ISSUES if i["severity"] == "ERROR"]
    warnings = [i for i in ISSUES if i["severity"] == "WARNING"]
    infos = [i for i in ISSUES if i["severity"] == "INFO"]
    result = "PASS" if not errors else "FAIL"
    lines = [
        "# Automated Meta-Model Validation", "",
        f"- Root: `{root}`",
    ]
    if source_root:
        lines.append(f"- Source Root: `{source_root}`")
    lines += [
        f"- Result: **{result}**", f"- ERROR: {len(errors)}", f"- WARNING: {len(warnings)}",
        f"- INFO: {len(infos)}", f"- Markdown files: {md_files}", f"- Defined IDs: {defined}",
        f"- Function definitions: {funcs}", f"- Source assets/tokens checked: {discovered}",
        "", "## Issues", "",
    ]
    if not ISSUES:
        lines.append("No automated structural issues found.")
    else:
        lines += ["| Severity | Type | Target | Message |", "|---|---|---|---|"]
        order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        for i in sorted(ISSUES, key=lambda x: (order.get(x["severity"], 9), x["type"], x["target"])):
            t = str(i["target"]).replace("|", "\\|")
            msg = str(i["message"]).replace("|", "\\|")
            lines.append(f"| {i['severity']} | {i['type']} | {t} | {msg} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("meta_model", nargs="?", default="docs/meta-model")
    ap.add_argument("--source", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--allow-missing-optional", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.meta_model)
    if not os.path.isdir(root):
        print(f"[错误] 元模型目录不存在: {root}")
        return 2
    source_root = os.path.abspath(args.source) if args.source else None
    given = args.source is not None

    check_structure(root, args.allow_missing_optional, source_root, given)
    definitions, md_count = check_ids_and_links(root)
    funct, func_count = check_functions(root)
    check_database(root)
    discovered = check_source(root, source_root, given)

    report = render(root, source_root if given else None, md_count, len(definitions),
                    func_count, discovered)
    if args.json:
        print(json.dumps({"report": report, "issues": ISSUES}, ensure_ascii=False, indent=2))
    else:
        print(report)
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(report)
    _ = funct
    return 1 if any(i["severity"] == "ERROR" for i in ISSUES) else 0


if __name__ == "__main__":
    sys.exit(main())
