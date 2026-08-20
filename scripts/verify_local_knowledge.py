#!/usr/bin/env python3
"""Validate the curated non-official local knowledge base."""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_KNOWLEDGE_PATH = SKILL_ROOT / "references" / "local-knowledge.json"

SCOPES = {
    "pku-general", "yuanpei", "tongban", "ai-discipline",
    "thu-general", "thu-ai-cs", "cross-school-comparison",
}
STAGES = {"general", "undergraduate", "master", "doctoral", "summer-camp"}
FORMATS = {"pdf", "docx", "markdown"}
EVIDENCE_TYPES = {
    "presentation", "personal-analysis", "internal-talking-points",
    "anecdote", "curated-supplement",
}
CLAIM_CLASSES = {
    "stable-background", "dated-snapshot", "dynamic-unverified", "opinion",
}
CONFIDENCES = {"low", "medium", "high"}
REQUIRED_SOURCE_IDS = {
    "tongban-supplement", "wuqiong-college", "thu-cs-guide",
    "wuqiong-guide-v2", "wuqiong-guide-v1", "pku-thu-csai-map",
    "xinya-guide", "misc-document", "yaoclass-guide",
}


def parse_date(value, field, errors, nullable=True):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        errors.append(f"{field}: 必须是 YYYY-MM-DD" + (" 或 null" if nullable else ""))
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field}: 非法日期 {value!r}")
        return None


def nonempty_strings(value):
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def validate(data, as_of, path):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"], warnings
    if data.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    built_at = parse_date(data.get("built_at"), "built_at", errors, nullable=False)
    if built_at and built_at > as_of:
        errors.append(f"built_at {built_at} 晚于核验基准日 {as_of}")
    if not isinstance(data.get("description"), str) or not data["description"].strip():
        errors.append("description 必须是非空字符串")
    if not nonempty_strings(data.get("retrieval_policy")):
        errors.append("retrieval_policy 必须是非空字符串数组")

    sources = data.get("sources")
    chunks = data.get("chunks")
    if not isinstance(sources, list):
        return errors + ["sources 必须是数组"], warnings
    if not isinstance(chunks, list):
        return errors + ["chunks 必须是数组"], warnings
    if len(sources) < 9:
        errors.append(f"来源数不足：{len(sources)}，至少需要 9")
    if len(chunks) < 30:
        errors.append(f"知识片段数不足：{len(chunks)}，至少需要 30")

    source_by_id = {}
    source_ids = []
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label}: 必须是对象")
            continue
        required = {
            "id", "filename", "format", "sha256", "extent", "as_of",
            "ingested_at", "evidence_type", "stance", "confidence",
            "searchable", "duplicate_of", "usage_limit",
        }
        missing = sorted(required - set(source))
        if missing:
            errors.append(f"{label}: 缺少字段 {', '.join(missing)}")
            continue
        source_id = source["id"]
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9-]+", source_id):
            errors.append(f"{label}.id: 必须是小写字母、数字或连字符")
            continue
        source_ids.append(source_id)
        source_by_id[source_id] = source
        if not isinstance(source["filename"], str) or not source["filename"].strip():
            errors.append(f"{label}.filename: 必须是非空字符串")
        if source["format"] not in FORMATS:
            errors.append(f"{label}.format: 未知值 {source['format']!r}")
        if not isinstance(source["sha256"], str) or not re.fullmatch(r"[0-9A-F]{64}", source["sha256"]):
            errors.append(f"{label}.sha256: 必须是 64 位大写十六进制")
        extent = source["extent"]
        if not isinstance(extent, dict) or not extent or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in extent.values()
        ):
            errors.append(f"{label}.extent: 必须是含正整数值的对象")
        parse_date(source["as_of"], f"{label}.as_of", errors)
        parse_date(source["ingested_at"], f"{label}.ingested_at", errors, nullable=False)
        if source["evidence_type"] not in EVIDENCE_TYPES:
            errors.append(f"{label}.evidence_type: 未知值 {source['evidence_type']!r}")
        if source["confidence"] not in CONFIDENCES:
            errors.append(f"{label}.confidence: 未知值 {source['confidence']!r}")
        if not isinstance(source["stance"], str) or not source["stance"].strip():
            errors.append(f"{label}.stance: 必须是非空字符串")
        if not isinstance(source["searchable"], bool):
            errors.append(f"{label}.searchable: 必须是布尔值")
        duplicate_of = source["duplicate_of"]
        if duplicate_of is not None and not isinstance(duplicate_of, str):
            errors.append(f"{label}.duplicate_of: 必须是来源 id 或 null")
        if duplicate_of and source["searchable"]:
            warnings.append(f"{label}: 重复来源仍标为 searchable")
        if not isinstance(source["usage_limit"], str) or not source["usage_limit"].strip():
            errors.append(f"{label}.usage_limit: 必须是非空字符串")

        # Curated repository sources can be hash-checked directly. Original
        # user binaries are intentionally not copied into the skill repo.
        repo_candidate = SKILL_ROOT / source["filename"]
        if repo_candidate.is_file():
            actual = hashlib.sha256(repo_candidate.read_bytes()).hexdigest().upper()
            if actual != source["sha256"]:
                errors.append(f"{label}.sha256: 与仓库文件不一致")

    duplicates = sorted(item for item, count in Counter(source_ids).items() if count > 1)
    if duplicates:
        errors.append("重复 source id: " + ", ".join(duplicates))
    missing_sources = sorted(REQUIRED_SOURCE_IDS - set(source_ids))
    if missing_sources:
        errors.append("缺少预期来源: " + ", ".join(missing_sources))
    for source_id, source in source_by_id.items():
        duplicate_of = source.get("duplicate_of")
        if duplicate_of and duplicate_of not in source_by_id:
            errors.append(f"来源 {source_id} 的 duplicate_of 不存在: {duplicate_of}")

    chunk_ids = []
    source_chunk_counts = Counter()
    for index, chunk in enumerate(chunks):
        label = f"chunks[{index}]"
        if not isinstance(chunk, dict):
            errors.append(f"{label}: 必须是对象")
            continue
        required = {
            "id", "source_id", "locator", "scope", "stage", "entities",
            "topics", "summary", "keywords", "claims", "evidence_type",
            "claim_class", "as_of", "confidence", "stance",
            "requires_live_check", "usage_limit",
        }
        missing = sorted(required - set(chunk))
        if missing:
            errors.append(f"{label}: 缺少字段 {', '.join(missing)}")
            continue
        chunk_id = chunk["id"]
        if not isinstance(chunk_id, str) or not re.fullmatch(r"[a-z0-9-]+", chunk_id):
            errors.append(f"{label}.id: 必须是小写字母、数字或连字符")
        else:
            chunk_ids.append(chunk_id)
        source_id = chunk["source_id"]
        if source_id not in source_by_id:
            errors.append(f"{label}.source_id: 未知来源 {source_id!r}")
        else:
            source_chunk_counts[source_id] += 1
            if not source_by_id[source_id].get("searchable"):
                errors.append(f"{label}: 非检索来源 {source_id} 不应含知识片段")
        locator = chunk["locator"]
        if not isinstance(locator, dict) or not locator:
            errors.append(f"{label}.locator: 必须是非空对象")
        else:
            for key, values in locator.items():
                if key not in {"pages", "paragraphs", "headings"}:
                    errors.append(f"{label}.locator: 未知定位字段 {key!r}")
                if not isinstance(values, list) or not values:
                    errors.append(f"{label}.locator.{key}: 必须是非空数组")
                elif key in {"pages", "paragraphs"} and not all(
                    isinstance(value, int) and not isinstance(value, bool) and value > 0
                    for value in values
                ):
                    errors.append(f"{label}.locator.{key}: 必须全为正整数")
                elif key == "headings" and not all(isinstance(value, str) and value for value in values):
                    errors.append(f"{label}.locator.headings: 必须全为非空字符串")
        for field in ("scope", "stage", "entities", "topics", "keywords", "claims"):
            if not nonempty_strings(chunk[field]):
                errors.append(f"{label}.{field}: 必须是非空字符串数组")
        unknown_scopes = sorted(set(chunk.get("scope", [])) - SCOPES)
        unknown_stages = sorted(set(chunk.get("stage", [])) - STAGES)
        if unknown_scopes:
            errors.append(f"{label}.scope: 未知值 {', '.join(unknown_scopes)}")
        if unknown_stages:
            errors.append(f"{label}.stage: 未知值 {', '.join(unknown_stages)}")
        if not isinstance(chunk["summary"], str) or not chunk["summary"].strip():
            errors.append(f"{label}.summary: 必须是非空字符串")
        if chunk["evidence_type"] not in EVIDENCE_TYPES:
            errors.append(f"{label}.evidence_type: 未知值 {chunk['evidence_type']!r}")
        if chunk["claim_class"] not in CLAIM_CLASSES:
            errors.append(f"{label}.claim_class: 未知值 {chunk['claim_class']!r}")
        parse_date(chunk["as_of"], f"{label}.as_of", errors)
        if chunk["confidence"] not in CONFIDENCES:
            errors.append(f"{label}.confidence: 未知值 {chunk['confidence']!r}")
        if not isinstance(chunk["stance"], str) or not chunk["stance"].strip():
            errors.append(f"{label}.stance: 必须是非空字符串")
        if not isinstance(chunk["requires_live_check"], bool):
            errors.append(f"{label}.requires_live_check: 必须是布尔值")
        if chunk["claim_class"] == "dynamic-unverified" and chunk["requires_live_check"] is not True:
            errors.append(f"{label}: dynamic-unverified 必须 requires_live_check=true")
        if chunk["evidence_type"] in {"internal-talking-points", "anecdote"} and chunk["confidence"] == "high":
            errors.append(f"{label}: 内部话术或个案不得标为 high confidence")
        if not isinstance(chunk["usage_limit"], str) or not chunk["usage_limit"].strip():
            errors.append(f"{label}.usage_limit: 必须是非空字符串")

    duplicate_chunks = sorted(item for item, count in Counter(chunk_ids).items() if count > 1)
    if duplicate_chunks:
        errors.append("重复 chunk id: " + ", ".join(duplicate_chunks))
    for source_id, source in source_by_id.items():
        if source.get("searchable") and not source_chunk_counts[source_id]:
            errors.append(f"可检索来源缺少知识片段: {source_id}")
    return errors, warnings


def build_parser():
    parser = argparse.ArgumentParser(description="核验本地补充知识库的结构、来源和风险标签。")
    parser.add_argument("--knowledge", type=Path, default=DEFAULT_KNOWLEDGE_PATH)
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        as_of = dt.date.fromisoformat(args.as_of)
        data = json.loads(args.knowledge.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    errors, warnings = validate(data, as_of, args.knowledge)
    payload = {
        "ok": not errors,
        "source_count": len(data.get("sources", [])) if isinstance(data, dict) else 0,
        "chunk_count": len(data.get("chunks", [])) if isinstance(data, dict) else 0,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(
            f"local sources: {payload['source_count']}  chunks: {payload['chunk_count']}  "
            f"errors: {len(errors)}  warnings: {len(warnings)}"
        )
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARN: {item}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
