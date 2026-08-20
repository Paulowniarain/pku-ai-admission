"""Shared library for the pku-ai-admissions skill.

Loads the provenance-labelled local knowledge base and references/sources.json,
normalizes Chinese queries, expands synonyms, infers risk guards, then scores
local material before official sources. Used by search_sources.py and
eval_retrieval.py so both share one ranking implementation.

Standard library only. All data paths derive from this file's location, never
from the caller's cwd.
"""

import json
import re
import unicodedata
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCES_PATH = SKILL_ROOT / "references" / "sources.json"
DEFAULT_LOCAL_KNOWLEDGE_PATH = SKILL_ROOT / "references" / "local-knowledge.json"
DEFAULT_CASES_PATH = SKILL_ROOT / "references" / "eval-cases.json"

OFFICIAL_SCOPES = ("pku-general", "yuanpei", "tongban", "ai-discipline")
LOCAL_ONLY_SCOPES = ("thu-general", "thu-ai-cs", "cross-school-comparison")
SCOPES = OFFICIAL_SCOPES + LOCAL_ONLY_SCOPES
STAGES = ("general", "undergraduate", "master", "doctoral", "summer-camp")
AUTHORITIES = ("central-admissions", "school-or-institute", "academic-unit")
SOURCE_TYPES = ("portal", "index", "overview", "annual-notice", "training-plan", "contact", "news")
TEMPORALS = ("stable", "live-index", "current-cycle", "historical")

REQUIRED_FIELDS = (
    "id", "title", "url", "scope", "stage", "authority", "source_type",
    "published_at", "temporal", "valid_for", "summary", "keywords", "claims",
)

# Synonym groups: members are mutually interchangeable surface forms.
# 通班 and 智班 deliberately live in different groups; the ambiguous bare
# “人工智能实验班” is not mapped to either side.
SYNONYM_GROUPS = [
    ("北京大学", "北大"),
    ("清华大学", "清华"),
    ("北京大学和清华大学", "北清", "清北"),
    ("本科", "本招", "高考", "本科生", "普通高考"),
    ("研究生", "研招"),
    ("硕士", "硕招", "硕士研究生"),
    ("博士", "博招", "博士研究生"),
    ("夏令营", "暑期学校"),
    ("推免", "保研", "推荐免试"),
    ("通班", "通用人工智能实验班"),
    ("智班", "智能科学与技术专业实验班"),
    ("智能科学与技术",),
    ("智能学院",),
    ("人工智能研究院", "AI研究院", "北大AI研究院"),
    ("元培学院", "元培"),
    ("无穹书院", "无穹"),
    ("新雅书院", "新雅"),
    ("姚班", "清华姚班", "计算机科学实验班"),
    ("清华计算机系", "贵系", "清华CS", "清华计科"),
    ("清华通班", "自动化系通班", "自动化系因材施教培养计划通用人工智能方向"),
    ("清华书院", "清华书院制", "书院制"),
    ("图灵班", "图班"),
    ("信班", "电子信息科学类实验班"),
    ("信息科学技术学院", "信科"),
    ("强基计划", "强基"),
    ("培养方案", "培养计划"),
    ("学位", "学士学位", "人工智能学士学位"),
    ("报名", "报考"),
    ("招生简章", "简章"),
    ("专业目录", "招生目录"),
]

LIVE_CHECK_WORDS = (
    "名额", "人数", "截止", "deadline", "分数", "分数线", "条件", "报名", "报考",
    "录取", "目录", "导师", "费用", "学费", "校区", "联系", "电话", "邮箱",
    "咨询", "时间", "日期", "日程", "安排", "计划", "要求", "资格", "招生",
    "申请", "推免", "夏令营", "入营", "选拔", "多少人", "多少名", "怎么报", "如何报",
    "一招", "二招", "直招", "高考直招", "校内选拔", "培养方案", "课程",
    "选课", "转专业", "论文", "科研成果", "多少",
)

CURRENT_WORDS = (
    "今年", "现在", "当前", "最新", "还能", "还招", "明年", "下一届", "这届",
    "这一届", "新一轮", "现行",
)

CAMP_WORDS = ("夏令营", "暑期学校", "入营", "优秀营员", "优营")
CAMP_ADMISSION_WORDS = ("录取", "等于", "算是", "保研", "上岸", "offer", "拟录取", "稳")
CAMP_EFFECT_WORDS = CAMP_ADMISSION_WORDS + ("效力", "意味着", "代表", "后续", "资格", "作用")

GUARD_DESCRIPTIONS = {
    "requires_live_check": "涉及名额/截止/分数/条件/目录/导师/费用/校区/联系方式等动态事实，必须回查当前官方页面",
    "needs_clarification": "叫法无法唯一对应通班或智班，回答前需先澄清",
    "historical_only_risk": "库内仅有通班历史规则（2021），不得当作当前规则外推",
    "summer_camp_not_admission": "夏令营/入营/优秀营员不等于录取，需区分状态",
    "entity_confusion": "问题涉及多个易混实体，需分别界定、不得混为一谈",
    "multi_unit_doctoral_route": "人工智能研究院博士招生可能依托多个院系，须查当年研招网与对应院系细则",
}


def normalize(text):
    """NFKC + lowercase + strip whitespace/punctuation (keep CJK/alnum)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).lower()
    return "".join(ch for ch in text if ch.isalnum() or "一" <= ch <= "鿿")


def load_sources(path=None):
    """Return (meta, sources). Light shape check only; full validation lives
    in verify_sources.py."""
    path = Path(path) if path else DEFAULT_SOURCES_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "sources" not in data:
        raise ValueError("sources.json 顶层必须是含 sources 数组的对象")
    sources = data["sources"]
    if not isinstance(sources, list):
        raise ValueError("sources 必须是数组")
    meta = {k: v for k, v in data.items() if k != "sources"}
    return meta, sources


def load_local_knowledge(path=None):
    """Return (meta, sources_by_id, chunks) for the curated local database."""
    path = Path(path) if path else DEFAULT_LOCAL_KNOWLEDGE_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ValueError("local-knowledge.json 顶层必须是含 sources 数组的对象")
    if not isinstance(data.get("chunks"), list):
        raise ValueError("local-knowledge.json 顶层必须含 chunks 数组")
    sources_by_id = {
        source.get("id"): source
        for source in data["sources"]
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    }
    meta = {k: v for k, v in data.items() if k not in ("sources", "chunks")}
    return meta, sources_by_id, data["chunks"]


def _mentions(query_norm):
    """Detect well-defined entity mentions in a normalized query."""
    thu_tongban = (
        "清华通班" in query_norm
        or "自动化系通班" in query_norm
        or "自动化系因材施教培养计划通用人工智能方向" in query_norm
    )
    thu_zhiban = "清华智班" in query_norm
    return {
        "tongban": ("通班" in query_norm or "通用人工智能实验班" in query_norm)
                   and not thu_tongban,
        "zhiban": (
            "智班" in query_norm
            or "智能科学与技术专业实验班" in query_norm
            or ("智能科学与技术" in query_norm and "实验班" in query_norm)
        ) and not thu_zhiban,
        "sai": "智能学院" in query_norm,
        "air": "人工智能研究院" in query_norm or "ai研究院" in query_norm,
        "yuanpei": "元培" in query_norm,
        "eecs": "信息科学技术学院" in query_norm or "信科" in query_norm,
        "wuqiong": "无穹书院" in query_norm or "无穹" in query_norm,
        "xinya": "新雅书院" in query_norm or "新雅" in query_norm,
        "yaoclass": "姚班" in query_norm or "清华姚班" in query_norm or thu_zhiban,
        "thu_cs": "清华计算机系" in query_norm or "贵系" in query_norm
                  or "清华cs" in query_norm or "清华计科" in query_norm,
        "thu_tongban": thu_tongban,
        "thu_college": "清华书院" in query_norm or "清华书院制" in query_norm,
        "thu": "清华" in query_norm,
        "cross_school": "北清" in query_norm or "清北" in query_norm
                        or ("北京大学" in query_norm and "清华大学" in query_norm)
                        or ("北大" in query_norm and "清华" in query_norm),
    }


def analyze_query(query):
    """Return normalized query, synonym groups, inferred scope/stage and guards."""
    q = normalize(query)
    phrases = set()
    phrase_groups = []
    free_phrases = set()
    for group in SYNONYM_GROUPS:
        if any(normalize(m) in q for m in group if normalize(m)):
            active = sorted({m for m in group if normalize(m)})
            phrase_groups.append(active)
            phrases.update(active)
    # Raw whitespace-split tokens (useful for latin/digits like 2025级, AI).
    for tok in re.split(r"\s+", str(query).strip()):
        tok_n = normalize(tok)
        known_member_in_token = any(
            normalize(member) in tok_n
            for group in phrase_groups
            for member in group
        )
        if len(tok_n) >= 2 and not known_member_in_token:
            free_token = re.sub(r"20\d{2}年?级?", "", tok_n)
            if len(free_token) >= 2:
                phrases.add(free_token)
                phrase_groups.append([free_token])
                free_phrases.add(free_token)
        elif known_member_in_token:
            residual = tok_n
            for group in phrase_groups:
                matches = sorted(
                    (normalize(member) for member in group if normalize(member) in residual),
                    key=len,
                    reverse=True,
                )
                if matches:
                    residual = residual.replace(matches[0], "")
            # Years are scored through valid_for cycles. Keeping them embedded
            # in a long residual lets an unrelated source win merely because
            # it has a "2026" keyword.
            residual = re.sub(r"20\d{2}年?级?", "", residual)
            if len(residual) >= 2:
                phrases.add(residual)
                phrase_groups.append([residual])
                free_phrases.add(residual)

    years = re.findall(r"(20\d{2})\s*级?", str(query))
    current = any(w in q for w in (normalize(w) for w in CURRENT_WORDS))
    live = any(normalize(w) in q for w in LIVE_CHECK_WORDS)
    m = _mentions(q)

    guards = []
    if live or current:
        guards.append("requires_live_check")

    ambiguous = False
    if "人工智能实验班" in q and "通用人工智能实验班" not in q:
        ambiguous = True
    if "智能班" in q or normalize("AI班") in q:
        ambiguous = True
    if "实验班" in q and not (m["tongban"] or m["zhiban"]) and (
        "人工智能" in q or "智能" in q or normalize("AI") in q
    ):
        ambiguous = True
    if ambiguous:
        guards.append("needs_clarification")
        # Retrieve both definitions so the caller can clarify with evidence
        # instead of merely warning that the phrase is ambiguous.
        phrases.update((
            "通班", "通用人工智能实验班",
            "智班", "智能科学与技术专业实验班",
        ))
        phrase_groups.extend([
            ["通班", "通用人工智能实验班"],
            ["智班", "智能科学与技术专业实验班"],
        ])

    if any(normalize(w) in q for w in CAMP_WORDS) and any(
        normalize(w) in q for w in CAMP_EFFECT_WORDS
    ):
        guards.append("summer_camp_not_admission")

    entity_hits = sum(1 for k in ("tongban", "zhiban", "sai", "air") if m[k])
    if entity_hits >= 2:
        guards.append("entity_confusion")

    thu_entity_hits = any(
        m[key] for key in ("wuqiong", "xinya", "yaoclass", "thu_cs", "thu_tongban", "thu_college", "thu")
    )
    pku_entity_hits = any(
        m[key] for key in ("tongban", "zhiban", "sai", "air", "yuanpei", "eecs")
    )

    air_doctoral_intent = any(normalize(w) in q for w in ("博士", "博招", "申请考核")) or (
        "导师" in q and "硕士" not in q and "硕招" not in q
    )
    if m["air"] and air_doctoral_intent:
        guards.append("multi_unit_doctoral_route")

    inferred_scopes = set()
    if m["tongban"]:
        inferred_scopes.update(("tongban", "yuanpei"))
    if m["yuanpei"]:
        inferred_scopes.add("yuanpei")
    if m["zhiban"] or m["sai"] or m["air"] or m["eecs"]:
        inferred_scopes.add("ai-discipline")
    if ambiguous:
        inferred_scopes.update(("tongban", "yuanpei", "ai-discipline"))
    if any(g[0] in ("本科",) and any(normalize(x) in q for x in g) for g in SYNONYM_GROUPS):
        inferred_scopes.add("pku-general")
    if any(w in q for w in ("研究生", "硕士", "博士", "研招", "推免", "保研")):
        inferred_scopes.add("pku-general")
    if m["xinya"] or m["thu_college"]:
        inferred_scopes.add("thu-general")
    if m["wuqiong"] or m["yaoclass"] or m["thu_cs"] or m["thu_tongban"]:
        inferred_scopes.add("thu-ai-cs")
    if m["cross_school"] or (thu_entity_hits and pku_entity_hits) or any(
        word in q for word in ("对比", "比较", "怎么选", "选哪个", "区别")
    ) and m["thu"] and ("北大" in q or "北京大学" in q):
        inferred_scopes.add("cross-school-comparison")

    inferred_stages = set()
    if ambiguous or any(w in q for w in ("本科", "本招", "高考", "强基", "通班", "智班", "元培")):
        inferred_stages.add("undergraduate")
    if thu_entity_hits:
        inferred_stages.add("undergraduate")
    if any(w in q for w in ("硕士", "硕招")):
        inferred_stages.add("master")
    if any(w in q for w in ("博士", "博招", "申请考核")):
        inferred_stages.add("doctoral")
    if any(w in q for w in ("研究生", "研招")) and not inferred_stages:
        inferred_stages.update(("master", "doctoral"))
    if any(normalize(w) in q for w in CAMP_WORDS):
        inferred_stages.add("summer-camp")
    if not inferred_stages:
        inferred_stages.add("general")

    return {
        "query": query,
        "normalized_query": q,
        "phrases": sorted(phrases),
        "phrase_groups": phrase_groups,
        "free_phrases": sorted(free_phrases),
        "years": years,
        "current_words": current,
        "definition_intent": any(w in q for w in ("是什么", "简介", "介绍", "沿革", "研究方向", "全称", "区别")),
        "notice_intent": any(w in q for w in ("通知", "简章", "指南", "选拔", "遴选", "结果", "公示")),
        "portal_intent": any(w in q for w in ("官网", "入口", "哪里查", "在哪查", "去哪查")),
        "guards": guards,
        "inferred_scopes": sorted(inferred_scopes),
        "inferred_stages": sorted(inferred_stages),
        "mentions": {k: v for k, v in m.items() if v},
        "air_doctoral_intent": air_doctoral_intent,
        "thu_only": thu_entity_hits and not pku_entity_hits and not m["cross_school"],
    }


def _cycle_matches(cycles, years):
    """Check whether any explicit year in the query matches source cycles."""
    nums = [c for c in cycles if re.search(r"20\d{2}", str(c))]
    for y in years:
        for c in nums:
            if y in str(c):
                return True
    return False


def _has_numeric_cycle(cycles):
    return any(re.search(r"20\d{2}", str(c)) for c in cycles)


def score_source(info, source):
    """Return (score, reasons). Deterministic, explainable field weights."""
    # The official registry is intentionally PKU-only. A clearly Tsinghua-only
    # query should not surface a PKU page merely because both use labels such
    # as “通班” or “智班”.
    if info.get("thu_only"):
        return 0, []
    score = 0
    reasons = []
    evidence_match = False
    title_n = normalize(source.get("title"))
    summary_n = normalize(source.get("summary"))
    kws = [normalize(k) for k in source.get("keywords", [])]
    claims_n = [normalize(c.get("text")) for c in source.get("claims", [])]

    q_full = info["normalized_query"]
    if len(q_full) >= 4 and q_full in title_n:
        score += 12
        evidence_match = True
        reasons.append("完整查询命中标题 +12")

    # Score a synonym concept once. Otherwise a query containing “北大” would
    # accidentally score both “北大” and “北京大学” against the same source.
    for group in info["phrase_groups"]:
        group_best = 0
        group_where = ""
        group_phrase = ""
        for phrase in group:
            p = normalize(phrase)
            if not p or len(p) < 2:
                continue
            best = 0
            where = ""
            reverse_keyword_match = p in set(info["free_phrases"])
            if p in title_n:
                best, where = 10, "标题"
            elif any(
                p in k or (reverse_keyword_match and len(k) >= 4 and not k.isdigit() and k in p)
                for k in kws
            ):
                best, where = 6, "关键词"
            elif any(p in c for c in claims_n):
                best, where = 3, "事实"
            elif p in summary_n:
                best, where = 2, "摘要"
            if best > group_best:
                group_best, group_where, group_phrase = best, where, phrase
        if group_best:
            score += group_best
            evidence_match = True
            reasons.append(f"{group_where}~'{group_phrase}' +{group_best}")

    scopes = set(source.get("scope", []))
    if scopes & set(info["inferred_scopes"]):
        score += 5
        reasons.append("scope 命中 +5")

    stages = set(source.get("stage", []))
    if stages & set(info["inferred_stages"]):
        score += 4
        reasons.append("stage 命中 +4")

    source_type = source.get("source_type")
    # News may establish project history or existence, but is not evidence for
    # current quotas, deadlines, eligibility, application or admission rules.
    if "requires_live_check" in info["guards"] and source_type == "news":
        return 0, []
    if evidence_match and info["definition_intent"] and source_type == "overview":
        score += 6
        reasons.append("释义意图命中概览 +6")
    if evidence_match and info["definition_intent"] and "简介" in source.get("title", ""):
        score += 5
        reasons.append("释义意图命中简介 +5")
    if evidence_match and info["definition_intent"] and any("全称" in claim for claim in claims_n):
        score += 7
        reasons.append("释义意图命中全称事实 +7")
    if evidence_match and info["notice_intent"] and source_type == "annual-notice":
        score += 6
        reasons.append("文件意图命中年度通知 +6")
    if evidence_match and info["portal_intent"] and source_type in ("portal", "index"):
        score += 6
        reasons.append("入口意图命中门户/索引 +6")

    valid_for = source.get("valid_for") or {}
    cycles = valid_for.get("cycles") or []
    if info["years"]:
        if _cycle_matches(cycles, info["years"]):
            cycle_delta = 8
            if "requires_live_check" in info["guards"] and source_type == "overview":
                cycle_delta = 0
            score += cycle_delta
            if cycle_delta:
                reasons.append(f"适用周期命中 +{cycle_delta}")
        elif _has_numeric_cycle(cycles):
            score -= 4
            reasons.append("适用周期不符 -4")

    # Freshness is a ranking modifier, never evidence that an unrelated source
    # matches the query. Without this gate, every stable source scored +2 for
    # arbitrary text and search returned plausible-looking irrelevant results.
    if not evidence_match:
        return 0, []

    temporal = source.get("temporal")
    wants_current = (info["current_words"] or "requires_live_check" in info["guards"]) and not info["years"]
    if wants_current:
        temporal_boost = {"live-index": 8, "current-cycle": 0, "stable": 0, "historical": -6}
        if temporal == "current-cycle" and source_type == "annual-notice":
            temporal_boost["current-cycle"] = 7
    else:
        temporal_boost = {"stable": 2, "current-cycle": 2, "live-index": 1, "historical": 0}
    delta = temporal_boost.get(temporal, 0)
    if delta:
        score += delta
        reasons.append(f"时效({temporal}) {'+' if delta > 0 else ''}{delta}")

    return score, reasons


GENERIC_LOCAL_PHRASES = {
    normalize(item) for item in (
        "北京大学", "北大", "清华大学", "清华", "本科", "本科生",
        "高考", "招生", "报名", "报考", "培养方案", "培养计划",
    )
}
GENERIC_LOCAL_ANCHORS = {
    normalize(item) for item in (
        "招生", "报名", "报考", "申请", "咨询", "联系", "电话", "邮箱",
        "时间", "日期", "要求", "条件", "计划",
    )
}


def score_local_chunk(info, chunk):
    """Return (score, reasons) for a provenance-labelled local chunk."""
    inferred_stages = set(info["inferred_stages"])
    if inferred_stages & {"master", "doctoral", "summer-camp"} and "undergraduate" not in inferred_stages:
        if set(chunk.get("stage", [])) == {"undergraduate"}:
            return 0, []
    score = 0
    reasons = []
    evidence_match = False
    specific_match = False
    entities = [normalize(item) for item in chunk.get("entities", [])]
    topics = [normalize(item) for item in chunk.get("topics", [])]
    keywords = [normalize(item) for item in chunk.get("keywords", [])]
    claims = [normalize(item) for item in chunk.get("claims", [])]
    summary = normalize(chunk.get("summary"))
    query = info["normalized_query"]

    if len(query) >= 5 and query in summary:
        score += 12
        evidence_match = True
        specific_match = True
        reasons.append("完整查询命中摘要 +12")

    for group in info["phrase_groups"]:
        best = 0
        where = ""
        matched_phrase = ""
        matched_norm = ""
        for phrase in group:
            term = normalize(phrase)
            if not term or len(term) < 2:
                continue
            candidate = 0
            candidate_where = ""
            if any(term in value or value in term for value in entities if len(value) >= 2):
                candidate, candidate_where = 12, "实体"
            elif any(term in value or value in term for value in topics if len(value) >= 2):
                candidate, candidate_where = 9, "主题"
            elif any(term in value or value in term for value in keywords if len(value) >= 2):
                candidate, candidate_where = 7, "关键词"
            elif any(term in value for value in claims):
                candidate, candidate_where = 4, "事实/限制"
            elif term in summary:
                candidate, candidate_where = 3, "摘要"
            if candidate > best:
                best = candidate
                where = candidate_where
                matched_phrase = phrase
                matched_norm = term
        if best:
            score += best
            evidence_match = True
            if matched_norm not in GENERIC_LOCAL_PHRASES:
                specific_match = True
            reasons.append(f"{where}~'{matched_phrase}' +{best}")

    anchors = {
        normalize(item) for item in (
            *LIVE_CHECK_WORDS,
            "资源", "竞争", "成熟度", "导师指导", "校友网络", "行政归属",
            "教学归属", "通识教育", "自由度", "风险", "课程衔接",
        )
        if len(normalize(item)) >= 2 and normalize(item) in query
    }
    for anchor in sorted(anchors):
        if any(anchor in value for value in topics):
            score += 8
            evidence_match = True
            if anchor not in GENERIC_LOCAL_ANCHORS:
                specific_match = True
            reasons.append(f"查询锚点~'{anchor}' 命中主题 +8")
        elif any(anchor in value for value in keywords):
            score += 6
            evidence_match = True
            if anchor not in GENERIC_LOCAL_ANCHORS:
                specific_match = True
            reasons.append(f"查询锚点~'{anchor}' 命中关键词 +6")
        elif any(anchor in value for value in claims) or anchor in summary:
            score += 3
            evidence_match = True
            if anchor not in GENERIC_LOCAL_ANCHORS:
                specific_match = True
            reasons.append(f"查询锚点~'{anchor}' 命中摘要/限制 +3")

    chunk_scopes = set(chunk.get("scope", []))
    inferred_scopes = set(info["inferred_scopes"])
    if chunk_scopes & inferred_scopes:
        score += 5
        reasons.append("scope 命中 +5")
    chunk_stages = set(chunk.get("stage", []))
    if chunk_stages & set(info["inferred_stages"]):
        score += 4
        reasons.append("stage 命中 +4")

    if info["years"] and chunk.get("as_of"):
        if any(year in chunk["as_of"] for year in info["years"]):
            score += 6
            reasons.append("材料时间命中 +6")
        else:
            score -= 3
            reasons.append("材料时间不符 -3")

    if info["definition_intent"]:
        if chunk.get("claim_class") == "stable-background":
            score += 10
            reasons.append("释义意图命中稳定背景 +10")
        elif chunk.get("claim_class") == "dynamic-unverified":
            score -= 5
            reasons.append("释义意图降权动态说法 -5")

    evidence_boost = {
        "curated-supplement": 3,
        "presentation": 2,
        "personal-analysis": 1,
        "internal-talking-points": 0,
        "anecdote": -2,
    }.get(chunk.get("evidence_type"), 0)
    if evidence_boost:
        score += evidence_boost
        reasons.append(f"证据类型 {'+' if evidence_boost > 0 else ''}{evidence_boost}")
    if chunk.get("confidence") == "medium":
        score += 2
        reasons.append("可信度 medium +2")

    # School names and generic admissions words alone are not enough to make
    # a non-official local chunk relevant.
    if not evidence_match or not specific_match:
        return 0, []
    return score, reasons


def search_local(info, scopes=None, stages=None, limit=5, local_sources=None, local_chunks=None):
    """Search curated local chunks and attach source-level provenance."""
    if local_sources is None or local_chunks is None:
        _, local_sources, local_chunks = load_local_knowledge()
    scopes = tuple(scopes or ())
    stages = tuple(stages or ())
    results = []
    for chunk in local_chunks:
        if not isinstance(chunk, dict):
            continue
        source = local_sources.get(chunk.get("source_id"))
        if not source or not source.get("searchable", False):
            continue
        if scopes and not (set(chunk.get("scope", [])) & set(scopes)):
            continue
        if stages and not (set(chunk.get("stage", [])) & set(stages)):
            continue
        score, reasons = score_local_chunk(info, chunk)
        if score <= 0:
            continue
        results.append({
            "id": chunk.get("id"),
            "source_id": chunk.get("source_id"),
            "source_filename": source.get("filename"),
            "source_sha256": source.get("sha256"),
            "locator": chunk.get("locator", {}),
            "score": score,
            "reasons": reasons,
            "scope": chunk.get("scope", []),
            "stage": chunk.get("stage", []),
            "entities": chunk.get("entities", []),
            "topics": chunk.get("topics", []),
            "summary": chunk.get("summary"),
            "claims": chunk.get("claims", []),
            "evidence_type": chunk.get("evidence_type"),
            "claim_class": chunk.get("claim_class"),
            "as_of": chunk.get("as_of"),
            "confidence": chunk.get("confidence"),
            "stance": chunk.get("stance"),
            "requires_live_check": chunk.get("requires_live_check", False),
            "usage_limit": chunk.get("usage_limit"),
            "source_usage_limit": source.get("usage_limit"),
        })
    results.sort(key=lambda item: (-item["score"], item["id"]))
    return results[:limit]


def search(
    query, scopes=None, stages=None, limit=5, sources=None,
    local_sources=None, local_chunks=None,
):
    """Search sources. scopes/stages are hard filters (intersection match).
    Returns a JSON-serializable dict."""
    if not normalize(query):
        raise ValueError("query 不能为空")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit 必须是正整数")
    if isinstance(scopes, str):
        scopes = (scopes,)
    else:
        scopes = tuple(scopes or ())
    if isinstance(stages, str):
        stages = (stages,)
    else:
        stages = tuple(stages or ())
    unknown_scopes = sorted(set(scopes) - set(SCOPES))
    unknown_stages = sorted(set(stages) - set(STAGES))
    if unknown_scopes:
        raise ValueError(f"未知 scope: {', '.join(unknown_scopes)}")
    if unknown_stages:
        raise ValueError(f"未知 stage: {', '.join(unknown_stages)}")

    if sources is None:
        _, sources = load_sources()
    info = analyze_query(query)
    local_results = search_local(
        info,
        scopes=scopes,
        stages=stages,
        limit=limit,
        local_sources=local_sources,
        local_chunks=local_chunks,
    )

    def keep(src):
        if scopes and not (set(src.get("scope", [])) & set(scopes)):
            return False
        if stages and not (set(src.get("stage", [])) & set(stages)):
            return False
        return True

    results = []
    for src in sources:
        if not keep(src):
            continue
        score, reasons = score_source(info, src)
        if score <= 0:
            continue
        results.append({
            "id": src.get("id"),
            "title": src.get("title"),
            "url": src.get("url"),
            "score": score,
            "reasons": reasons,
            "scope": src.get("scope", []),
            "stage": src.get("stage", []),
            "authority": src.get("authority"),
            "source_type": src.get("source_type"),
            "temporal": src.get("temporal"),
            "published_at": src.get("published_at"),
            "valid_for": src.get("valid_for", {}),
            "summary": src.get("summary"),
            "keywords": src.get("keywords", []),
            "claims": src.get("claims", []),
        })
    wants_current = (info["current_words"] or "requires_live_check" in info["guards"]) and not info["years"]
    results.sort(key=lambda r: (-r["score"], r["id"]))
    # Keep historical evidence available in Top-K, but never lead a dynamic
    # answer with it when a non-historical matched source is available.
    if wants_current and results and results[0]["temporal"] == "historical":
        fresh_index = next(
            (i for i, item in enumerate(results) if item["temporal"] != "historical"),
            None,
        )
        if fresh_index is not None:
            results.insert(0, results.pop(fresh_index))

    # Only dynamic/current Tongban questions need the historical-only guard.
    # Definition and explicitly historical questions can safely use the 2021
    # guide as historical evidence without being treated as current policy.
    asks_tongban = bool(info["mentions"].get("tongban"))
    explicitly_historical = (bool(info["years"]) and set(info["years"]) == {"2021"}) or any(
        w in info["normalized_query"] for w in ("历史", "当年")
    )
    tongban_dynamic = asks_tongban and "requires_live_check" in info["guards"] and not explicitly_historical
    if tongban_dynamic:
        tongban_results = [r for r in results if "tongban" in r["scope"]]
        has_historical = any(r["temporal"] == "historical" for r in tongban_results)
        has_current = any(
            r["temporal"] in ("current-cycle", "live-index")
            and r["source_type"] in ("annual-notice", "index", "portal")
            for r in tongban_results
        )
        if has_historical and not has_current and "historical_only_risk" not in info["guards"]:
            info["guards"].append("historical_only_risk")

    def promote(source_id, position):
        """Move an entity's canonical definition into a bounded evidence slot."""
        index = next((i for i, item in enumerate(results) if item["id"] == source_id), None)
        if index is None:
            return
        item = results.pop(index)
        results.insert(min(position, len(results)), item)

    if info["mentions"].get("yuanpei") and info["definition_intent"]:
        promote("yuanpei-overview", 0)
    if info["mentions"].get("air"):
        promote("ai-institute-overview", 0 if info["definition_intent"] else 2)
        route_question = any(w in info["normalized_query"] for w in ("依托", "院系", "报名路径"))
        explicit_master = any(w in info["normalized_query"] for w in ("硕士", "硕招"))
        if info["air_doctoral_intent"] or (route_question and not explicit_master):
            promote("ai-institute-graduate-admissions", 1)
    if asks_tongban:
        promote("yuanpei-tongban-guide-2021", min(4 if tongban_dynamic else 1, limit - 1))
    if info["mentions"].get("zhiban"):
        promote("sai-zhiban-cultivation", 0 if not wants_current else 1)
    if "needs_clarification" in info["guards"]:
        promote("sai-zhiban-cultivation", 1)
        promote("yuanpei-tongban-guide-2021", min(3, limit - 1))

    results = results[:limit]
    return {
        "query": query,
        "normalized_query": info["normalized_query"],
        "filters": {"scope": list(scopes or []), "stage": list(stages or [])},
        "inferred_scopes": info["inferred_scopes"],
        "inferred_stages": info["inferred_stages"],
        "guards": info["guards"],
        "retrieval_order": ["local_results", "results", "live_official_web"],
        "local_results": local_results,
        "results": results,
    }
