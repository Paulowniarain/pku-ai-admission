#!/usr/bin/env python3
"""Run deterministic local/official Top-K and risk-guard evaluations."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from source_lib import DEFAULT_CASES_PATH, DEFAULT_SOURCES_PATH, load_sources, search


def evaluate_case(case, sources):
    failures = []
    top_k = case.get("top_k", 5)
    filters = case.get("filters") or {}
    result = search(
        case["query"],
        scopes=filters.get("scope"),
        stages=filters.get("stage"),
        limit=top_k,
        sources=sources,
    )
    result_ids = [item["id"] for item in result["results"]]
    local_result_ids = [item["id"] for item in result.get("local_results", [])]
    for group in case.get("expected_any_id_groups", []):
        if not set(group) & set(result_ids):
            failures.append(f"Top-{top_k} 缺少任一来源: {group}; 实际={result_ids}")
    for guard in case.get("required_guards", []):
        if guard not in result["guards"]:
            failures.append(f"缺少守卫 {guard}; 实际={result['guards']}")
    for guard in case.get("forbidden_guards", []):
        if guard in result["guards"]:
            failures.append(f"出现禁止守卫 {guard}")
    for scope in case.get("expected_inferred_scopes", []):
        if scope not in result["inferred_scopes"]:
            failures.append(f"未推断 scope {scope}; 实际={result['inferred_scopes']}")
    for stage in case.get("expected_inferred_stages", []):
        if stage not in result["inferred_stages"]:
            failures.append(f"未推断 stage {stage}; 实际={result['inferred_stages']}")
    allowed_top1 = case.get("expected_top1_ids")
    if allowed_top1 and (not result_ids or result_ids[0] not in allowed_top1):
        failures.append(f"Top-1 应属于 {allowed_top1}; 实际={result_ids[:1]}")
    if result_ids and result_ids[0] in case.get("forbidden_top1_ids", []):
        failures.append(f"Top-1 不应为 {result_ids[0]}")
    forbidden_results = sorted(set(result_ids) & set(case.get("forbidden_result_ids", [])))
    if forbidden_results:
        failures.append(f"Top-{top_k} 出现禁止来源: {forbidden_results}")
    if case.get("expect_no_official_results") and result_ids:
        failures.append(f"预期无官方结果；实际={result_ids}")
    for group in case.get("expected_local_any_id_groups", []):
        if not set(group) & set(local_result_ids):
            failures.append(f"本地 Top-{top_k} 缺少任一片段: {group}; 实际={local_result_ids}")
    allowed_local_top1 = case.get("expected_local_top1_ids")
    if allowed_local_top1 and (
        not local_result_ids or local_result_ids[0] not in allowed_local_top1
    ):
        failures.append(
            f"本地 Top-1 应属于 {allowed_local_top1}; 实际={local_result_ids[:1]}"
        )
    forbidden_local = sorted(
        set(local_result_ids) & set(case.get("forbidden_local_result_ids", []))
    )
    if forbidden_local:
        failures.append(f"本地 Top-{top_k} 出现禁止片段: {forbidden_local}")
    if case.get("expect_no_local_results") and local_result_ids:
        failures.append(f"预期无本地结果；实际={local_result_ids}")
    return result, failures


def build_parser():
    parser = argparse.ArgumentParser(description="评测官方来源检索与高风险问法守卫。")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--case", action="append", help="只运行指定 case id；可重复")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cases_data = json.loads(args.cases.read_text(encoding="utf-8"))
        _, sources = load_sources(args.sources)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    cases = cases_data.get("cases") if isinstance(cases_data, dict) else None
    if not isinstance(cases, list) or len(cases) < 30:
        parser.error("eval-cases.json 必须至少包含 30 个 cases")
    selected = set(args.case or [])
    known_ids = {case.get("id") for case in cases}
    unknown = sorted(selected - known_ids)
    if unknown:
        parser.error("未知 case: " + ", ".join(unknown))

    details = []
    failed = 0
    for case in cases:
        if selected and case.get("id") not in selected:
            continue
        result, failures = evaluate_case(case, sources)
        failed += bool(failures)
        details.append({
            "id": case.get("id"),
            "ok": not failures,
            "failures": failures,
            "result_ids": [item["id"] for item in result["results"]],
            "local_result_ids": [item["id"] for item in result.get("local_results", [])],
            "guards": result["guards"],
        })
    payload = {
        "ok": failed == 0,
        "total": len(details),
        "passed": len(details) - failed,
        "failed": failed,
        "details": details,
    }
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        for detail in details:
            marker = "PASS" if detail["ok"] else "FAIL"
            print(
                f"{marker} {detail['id']}: local={detail['local_result_ids']} "
                f"official={detail['result_ids']} guards={detail['guards']}"
            )
            for failure in detail["failures"]:
                print(f"  - {failure}")
        print(f"\n{payload['passed']}/{payload['total']} passed")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
