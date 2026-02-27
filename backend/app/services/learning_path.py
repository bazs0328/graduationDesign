"""Cross-document learning path with stages, modules and milestones."""

import logging
import re
import time
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Optional
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.models import Keypoint, KeypointDependency, LearnerProfile
from app.schemas import (
    LearningPathEdge,
    LearningPathItem,
    LearningPathModule,
    LearningPathStage,
)
from app.services.keypoint_dedup import cluster_kb_keypoints
from app.services.mastery import (
    MASTERY_MASTERED,
    MASTERY_PREREQ_THRESHOLD,
    mastery_action,
    mastery_priority,
)
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

DEPENDENCY_GRAPH_VERSION = "v2"
DEPENDENCY_RELATION = f"prerequisite:{DEPENDENCY_GRAPH_VERSION}"
_LEARNING_PATH_CACHE_SCHEMA_VERSION = "lpv2"

_LEARNING_PATH_RESULT_CACHE_TTL_SECONDS = 300
_LEARNING_PATH_RESULT_CACHE_MAX_ENTRIES = 64
_learning_path_result_cache: dict[tuple[str, str, int, str], tuple[float, Any]] = {}
_learning_path_result_cache_lock = Lock()

STAGE_ORDER = ["foundation", "intermediate", "advanced", "application"]
STAGE_META = {
    "foundation": ("基础阶段", "先建立核心概念与术语理解。"),
    "intermediate": ("进阶阶段", "连接概念并形成系统化理解。"),
    "advanced": ("高级阶段", "攻克复杂推理与综合分析问题。"),
    "application": ("应用阶段", "迁移到实战场景并完成综合应用。"),
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_NUMERIC_PREFIX_RE = re.compile(r"^\s*(?:第\s*(\d+)\s*[章节篇条]|(\d+)\s*[\.、)\-:])")
_CJK_NUM_PREFIX_RE = re.compile(r"^\s*([一二三四五六七八九十百零两]+)\s*[、\.]")
_BASIC_HINT_RE = re.compile(r"(定义|概念|基础|术语|简介|入门|原理)")
_ADVANCED_HINT_RE = re.compile(r"(应用|算法|推导|案例|实现|实践|优化|综合)")

_CJK_NUM_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "百": 100,
}

_RULE_EDGE_CONFIDENCE_STRONG = 0.55
_RULE_EDGE_CONFIDENCE_MEDIUM = 0.46
_RULE_EDGE_CONFIDENCE_LIGHT = 0.38
_LLM_EDGE_CONFIDENCE = 0.72
_MAX_IN_DEGREE = 3
_MAX_OUT_DEGREE = 4


@dataclass(frozen=True)
class _DependencyEdgeCandidate:
    from_id: str
    to_id: str
    confidence: float
    source: str


def _learning_path_cache_key(
    user_id: str, kb_id: str, limit: int
) -> tuple[str, str, int, str]:
    return (str(user_id), str(kb_id), int(limit or 0), _LEARNING_PATH_CACHE_SCHEMA_VERSION)


def _prune_learning_path_result_cache(now: float) -> None:
    expired = [key for key, (expires_at, _) in _learning_path_result_cache.items() if expires_at <= now]
    for key in expired:
        _learning_path_result_cache.pop(key, None)

    overflow = len(_learning_path_result_cache) - _LEARNING_PATH_RESULT_CACHE_MAX_ENTRIES
    if overflow <= 0:
        return
    oldest = sorted(
        _learning_path_result_cache.items(),
        key=lambda item: item[1][0],
    )[:overflow]
    for key, _ in oldest:
        _learning_path_result_cache.pop(key, None)


def _get_cached_learning_path_result(
    user_id: str,
    kb_id: str,
    limit: int,
) -> Optional[tuple[list[Any], list[Any], list[Any], list[Any], dict[str, Any]]]:
    key = _learning_path_cache_key(user_id, kb_id, limit)
    now = time.monotonic()
    with _learning_path_result_cache_lock:
        entry = _learning_path_result_cache.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at <= now:
            _learning_path_result_cache.pop(key, None)
            return None
        return deepcopy(payload)


def _set_cached_learning_path_result(
    user_id: str,
    kb_id: str,
    limit: int,
    payload: tuple[list[Any], list[Any], list[Any], list[Any], dict[str, Any]],
) -> None:
    key = _learning_path_cache_key(user_id, kb_id, limit)
    now = time.monotonic()
    with _learning_path_result_cache_lock:
        _prune_learning_path_result_cache(now)
        _learning_path_result_cache[key] = (
            now + _LEARNING_PATH_RESULT_CACHE_TTL_SECONDS,
            deepcopy(payload),
        )
        _prune_learning_path_result_cache(now)


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

DEPENDENCY_SYSTEM = (
    "You are an expert learning-path planner.\n"
    "Given keypoints (ID, text, document), infer strong prerequisite edges.\n"
    "Also provide optional per-keypoint hints for difficulty/importance/topic/stage.\n\n"
    "Output JSON ONLY, using either:\n"
    "1) Object format with keys: edges, attributes.\n"
    "   - edges: array of pairs (from_id, to_id)\n"
    "   - attributes: array of per-id hints (id, difficulty_level, importance_score, topic_category, learning_stage_hint)\n"
    "2) Or legacy format: array of edge objects with keys from_id, to_id.\n\n"
    "Rules:\n"
    "- Keep only strong prerequisite edges.\n"
    "- Avoid noisy associations.\n"
    "- Stage hint must be one of: foundation, intermediate, advanced, application.\n"
    "- difficulty_level/importance_score must be in [0, 1]."
)

DEPENDENCY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", DEPENDENCY_SYSTEM),
        (
            "human",
            "Keypoints:\n{points_text}\n\nReturn JSON only.",
        ),
    ]
)

STAGE_SYSTEM = (
    "You are a curriculum designer. For each keypoint ID, estimate:\n"
    "- stage: foundation/intermediate/advanced/application\n"
    "- difficulty_level: 0~1\n"
    "- importance_score: 0~1\n"
    "Return JSON array only. Each item must include keys: id, stage, difficulty_level, importance_score."
)

STAGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", STAGE_SYSTEM),
        (
            "human",
            "Learner ability: {ability_level}\n\n"
            "Keypoints:\n{points_text}\n\n"
            "Edges:\n{edges_text}\n\n"
            "Return JSON only.",
        ),
    ]
)

MODULE_SYSTEM = (
    "You are a learning-module planner.\n"
    "Group keypoints into coherent modules (topic-based, practical study chunks).\n"
    "Output JSON object only with key modules.\n"
    "Each module item must include keys: module_id, name, description, keypoint_ids.\n"
    "Rules:\n"
    "- Each keypoint ID can appear in at most one module.\n"
    "- Prefer 3~8 keypoints per module when possible.\n"
    "- module_id must be unique."
)

MODULE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", MODULE_SYSTEM),
        (
            "human",
            "Learner ability: {ability_level}\n\n"
            "Keypoints:\n{points_text}\n\n"
            "Edges:\n{edges_text}\n\n"
            "Return JSON only.",
        ),
    ]
)

MILESTONE_SYSTEM = (
    "You are a milestone planner.\n"
    "Pick keypoint IDs that should be marked as milestones.\n"
    "Prefer one key milestone per stage and key module junctions.\n"
    "Return JSON object only with key milestone_ids (array of keypoint IDs)."
)

MILESTONE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", MILESTONE_SYSTEM),
        (
            "human",
            "Items:\n{items_text}\n\n"
            "Stages:\n{stages_text}\n\n"
            "Modules:\n{modules_text}\n\n"
            "Return JSON only.",
        ),
    ]
)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def _escape_prompt_text(text: str) -> str:
    """Escape braces so LangChain format placeholders are not corrupted."""
    return text.replace("{", "{{").replace("}", "}}")


def _invoke_prompt_json(prompt: ChatPromptTemplate, **kwargs: str) -> Any:
    """Invoke an LLM prompt and parse JSON output safely."""
    llm = get_llm(temperature=0.1)
    safe_kwargs = {k: _escape_prompt_text(v) for k, v in kwargs.items()}
    messages = prompt.format_messages(**safe_kwargs)
    result = llm.invoke(messages)
    return safe_json_loads(result.content)


def _clamp_score(value: Any, fallback: float = 0.5) -> float:
    """Clamp score into [0, 1] with fallback."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(0.0, min(1.0, numeric))


def _normalize_stage(stage: Any) -> Optional[str]:
    """Normalize stage labels to the known stage set."""
    if not isinstance(stage, str):
        return None
    s = stage.strip().lower()
    alias_map = {
        "basic": "foundation",
        "beginner": "foundation",
        "intro": "foundation",
        "introductory": "foundation",
        "mid": "intermediate",
        "mid-level": "intermediate",
        "expert": "advanced",
        "practical": "application",
        "practice": "application",
    }
    s = alias_map.get(s, s)
    if s in STAGE_ORDER:
        return s
    return None


def _dependency_relation_is_current(relation: Optional[str]) -> bool:
    return (relation or "") == DEPENDENCY_RELATION


def _tokenize_text(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _token_overlap_count(a: str, b: str) -> int:
    if not a or not b:
        return 0
    tokens_a = set(_tokenize_text(a))
    tokens_b = set(_tokenize_text(b))
    if not tokens_a or not tokens_b:
        return 0
    return len(tokens_a.intersection(tokens_b))


def _looks_basic(text: str) -> bool:
    return bool(_BASIC_HINT_RE.search(text or ""))


def _looks_advanced(text: str) -> bool:
    return bool(_ADVANCED_HINT_RE.search(text or ""))


def _cjk_numeral_to_int(text: str) -> Optional[int]:
    s = (text or "").strip()
    if not s:
        return None
    total = 0
    current = 0
    seen = False
    for ch in s:
        value = _CJK_NUM_MAP.get(ch)
        if value is None:
            return None
        seen = True
        if value == 100:
            current = max(1, current) * value
            total += current
            current = 0
        elif value == 10:
            current = max(1, current) * value
        else:
            current += value
    if not seen:
        return None
    return total + current


def _extract_order_number(text: str) -> Optional[int]:
    if not text:
        return None
    match = _NUMERIC_PREFIX_RE.match(text)
    if match:
        number = match.group(1) or match.group(2)
        if number:
            try:
                return int(number)
            except ValueError:
                return None
    match = _CJK_NUM_PREFIX_RE.match(text)
    if match:
        return _cjk_numeral_to_int(match.group(1))
    return None


def _keypoint_local_sort_tuple(keypoint: Keypoint) -> tuple[Any, ...]:
    page = keypoint.page if isinstance(keypoint.page, int) else 10**9
    chunk = keypoint.chunk if isinstance(keypoint.chunk, int) else 10**9
    created_at = keypoint.created_at.isoformat() if getattr(keypoint, "created_at", None) else "9999-12-31T23:59:59"
    return (
        str(keypoint.doc_id or ""),
        page,
        chunk,
        created_at,
        str(keypoint.id or ""),
    )


def _add_rule_candidate(
    candidate_map: dict[tuple[str, str], _DependencyEdgeCandidate],
    from_id: str,
    to_id: str,
    confidence: float,
    source: str,
) -> None:
    if not from_id or not to_id or from_id == to_id:
        return
    key = (from_id, to_id)
    current = candidate_map.get(key)
    new_candidate = _DependencyEdgeCandidate(
        from_id=from_id,
        to_id=to_id,
        confidence=round(_clamp_score(confidence, 0.5), 3),
        source=source,
    )
    if current is None or new_candidate.confidence > current.confidence:
        candidate_map[key] = new_candidate


def _infer_rule_dependency_edges(
    keypoints: list[Keypoint],
    doc_map: dict[str, str],  # kept for future richer prompts/rules
) -> list[_DependencyEdgeCandidate]:
    """Infer conservative dependency edges using local structural heuristics."""
    del doc_map  # currently unused in rule inference
    if len(keypoints) < 2:
        return []

    candidate_map: dict[tuple[str, str], _DependencyEdgeCandidate] = {}
    grouped: dict[str, list[Keypoint]] = defaultdict(list)
    for kp in keypoints:
        grouped[str(kp.doc_id or "")].append(kp)

    for doc_kps in grouped.values():
        ordered = sorted(doc_kps, key=_keypoint_local_sort_tuple)
        for idx, left in enumerate(ordered):
            left_text = str(left.text or "")
            left_num = _extract_order_number(left_text)
            for offset in (1, 2):
                j = idx + offset
                if j >= len(ordered):
                    break
                right = ordered[j]
                right_text = str(right.text or "")
                right_num = _extract_order_number(right_text)
                overlap = _token_overlap_count(left_text, right_text)

                if left_num is not None and right_num is not None and left_num < right_num:
                    confidence = _RULE_EDGE_CONFIDENCE_STRONG if right_num - left_num <= 1 else _RULE_EDGE_CONFIDENCE_MEDIUM
                    _add_rule_candidate(candidate_map, left.id, right.id, confidence, "rule:number_prefix")

                if overlap >= 2 and _looks_basic(left_text) and _looks_advanced(right_text):
                    _add_rule_candidate(
                        candidate_map,
                        left.id,
                        right.id,
                        _RULE_EDGE_CONFIDENCE_STRONG,
                        "rule:basic_to_advanced",
                    )

                if overlap >= (2 if offset == 1 else 3):
                    _add_rule_candidate(
                        candidate_map,
                        left.id,
                        right.id,
                        _RULE_EDGE_CONFIDENCE_LIGHT if offset == 2 else _RULE_EDGE_CONFIDENCE_MEDIUM,
                        "rule:local_overlap",
                    )

    # Cross-document conservative linking for deduplicated KBs:
    # only near neighbors in stable order with strong lexical overlap and a basic/ordered cue.
    global_ordered = sorted(keypoints, key=_keypoint_local_sort_tuple)
    for idx, left in enumerate(global_ordered):
        left_text = str(left.text or "")
        left_num = _extract_order_number(left_text)
        for offset in (1, 2, 3):
            j = idx + offset
            if j >= len(global_ordered):
                break
            right = global_ordered[j]
            if left.doc_id == right.doc_id:
                continue
            right_text = str(right.text or "")
            overlap = _token_overlap_count(left_text, right_text)
            if overlap < 2:
                continue
            if left_num is not None or _looks_basic(left_text):
                _add_rule_candidate(
                    candidate_map,
                    left.id,
                    right.id,
                    _RULE_EDGE_CONFIDENCE_LIGHT,
                    "rule:cross_doc_overlap",
                )

    return sorted(
        candidate_map.values(),
        key=lambda c: (-c.confidence, c.source, c.from_id, c.to_id),
    )


def _infer_llm_dependency_edges(
    keypoints: list[Keypoint],
    doc_map: dict[str, str],
) -> tuple[list[_DependencyEdgeCandidate], dict[str, dict[str, Any]]]:
    """Infer dependency edges with LLM and return candidates + optional attributes."""
    if not keypoints:
        return [], {}
    kp_ids = {kp.id for kp in keypoints}
    points_text = _format_keypoints_for_prompt(keypoints, doc_map)
    payload = _invoke_prompt_json(DEPENDENCY_PROMPT, points_text=points_text)
    edge_tuples, attr_hints = _parse_dependency_payload(payload, kp_ids)
    candidates = [
        _DependencyEdgeCandidate(
            from_id=from_id,
            to_id=to_id,
            confidence=_LLM_EDGE_CONFIDENCE,
            source="llm",
        )
        for from_id, to_id in edge_tuples
    ]
    return candidates, attr_hints


def _merge_dependency_edges_with_constraints(
    candidates: list[_DependencyEdgeCandidate],
    valid_ids: set[str],
) -> list[_DependencyEdgeCandidate]:
    """Merge edge candidates by confidence while enforcing DAG and degree limits."""
    if not candidates:
        return []

    seen: set[tuple[str, str]] = set()
    in_degree: dict[str, int] = defaultdict(int)
    out_degree: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    merged: list[_DependencyEdgeCandidate] = []

    def source_rank(source: str) -> int:
        if source == "llm":
            return 0
        if source.startswith("rule:number_prefix"):
            return 1
        if source.startswith("rule:basic_to_advanced"):
            return 2
        return 3

    ordered = sorted(
        candidates,
        key=lambda c: (-c.confidence, source_rank(c.source), c.from_id, c.to_id),
    )

    for candidate in ordered:
        from_id = candidate.from_id
        to_id = candidate.to_id
        if from_id not in valid_ids or to_id not in valid_ids or from_id == to_id:
            continue
        pair = (from_id, to_id)
        if pair in seen:
            continue
        if out_degree[from_id] >= _MAX_OUT_DEGREE or in_degree[to_id] >= _MAX_IN_DEGREE:
            continue
        adj[from_id].append(to_id)
        if _has_path(adj, to_id, from_id):
            adj[from_id].pop()
            continue
        seen.add(pair)
        out_degree[from_id] += 1
        in_degree[to_id] += 1
        merged.append(candidate)

    return merged


# ---------------------------------------------------------------------------
# Dependency graph building
# ---------------------------------------------------------------------------


def _load_clustered_kb_keypoints(
    db: Session,
    user_id: str,
    kb_id: str,
) -> tuple[list[Any], list[Keypoint], dict[str, Any], dict[str, str]]:
    """Load KB keypoints and return deduplicated clusters + representative views."""
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    if not clusters:
        return [], [], {}, {}

    keypoints = sorted(
        [cluster.representative_keypoint for cluster in clusters],
        key=lambda kp: (kp.doc_id or "", kp.id or ""),
    )
    cluster_map = {cluster.representative_id: cluster for cluster in clusters}

    doc_map: dict[str, str] = {}
    for cluster in clusters:
        for member in cluster.members:
            if member.doc_id not in doc_map:
                doc_map[member.doc_id] = member.doc_name or member.doc_id
    return clusters, keypoints, cluster_map, doc_map


def _format_keypoints_for_prompt(
    keypoints: list[Keypoint], doc_map: dict[str, str]
) -> str:
    """Format keypoints grouped by document for LLM prompts."""
    grouped: dict[str, list[Keypoint]] = defaultdict(list)
    for kp in keypoints:
        grouped[kp.doc_id].append(kp)

    lines: list[str] = []
    for doc_id, kps in grouped.items():
        doc_name = doc_map.get(doc_id, doc_id)
        lines.append(f"== Document: {doc_name} ==")
        for kp in kps:
            lines.append(f"  [{kp.id}] {kp.text}")
        lines.append("")
    return "\n".join(lines)


def _has_path(adj: dict[str, list[str]], start: str, target: str) -> bool:
    """BFS to check if start can reach target."""
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        for neighbor in adj.get(node, []):
            queue.append(neighbor)
    return False


def _remove_cycles(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Remove edges that would create cycles."""
    adj: dict[str, list[str]] = defaultdict(list)
    clean_edges: list[tuple[str, str]] = []
    for from_id, to_id in edges:
        adj[from_id].append(to_id)
        if _has_path(adj, to_id, from_id):
            adj[from_id].pop()
            continue
        clean_edges.append((from_id, to_id))
    return clean_edges


def _parse_dependency_payload(
    payload: Any, kp_ids: set[str]
) -> tuple[list[tuple[str, str]], dict[str, dict[str, Any]]]:
    """Parse dependency payload from LLM and extract edge list + attribute hints."""
    raw_edges: Any = payload
    raw_attrs: Any = []
    if isinstance(payload, dict):
        raw_edges = payload.get("edges", [])
        raw_attrs = payload.get("attributes", [])

    edge_tuples: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    if isinstance(raw_edges, list):
        for edge in raw_edges:
            from_id = ""
            to_id = ""
            if isinstance(edge, dict):
                from_id = edge.get("from_id", "")
                to_id = edge.get("to_id", "")
            elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
                from_id = str(edge[0] or "")
                to_id = str(edge[1] or "")
            else:
                continue
            if from_id not in kp_ids or to_id not in kp_ids or from_id == to_id:
                continue
            pair = (from_id, to_id)
            if pair in seen_edges:
                continue
            seen_edges.add(pair)
            edge_tuples.append(pair)

    attr_hints: dict[str, dict[str, Any]] = {}
    if isinstance(raw_attrs, list):
        for item in raw_attrs:
            if not isinstance(item, dict):
                continue
            kp_id = item.get("id")
            if kp_id not in kp_ids:
                continue
            stage_hint = _normalize_stage(
                item.get("learning_stage_hint") or item.get("stage")
            )
            attr_hints[kp_id] = {
                "difficulty": _clamp_score(
                    item.get("difficulty_level", item.get("difficulty")), 0.5
                ),
                "importance": _clamp_score(
                    item.get("importance_score", item.get("importance")), 0.5
                ),
                "topic": str(item.get("topic_category", "")).strip(),
                "stage_hint": stage_hint,
            }
    return edge_tuples, attr_hints


def build_dependency_graph(
    db: Session,
    user_id: str,
    kb_id: str,
    force: bool = False,
) -> list[KeypointDependency]:
    """Build or retrieve cached dependency graph for a KB."""
    existing = (
        db.query(KeypointDependency)
        .filter(KeypointDependency.kb_id == kb_id)
        .all()
    )
    if not force and existing:
        if all(_dependency_relation_is_current(dep.relation) for dep in existing):
            return existing
        logger.info(
            "Rebuilding legacy dependency graph for kb=%s (version=%s)",
            kb_id,
            DEPENDENCY_GRAPH_VERSION,
        )
        force = True

    _, keypoints, _, doc_map = _load_clustered_kb_keypoints(db, user_id, kb_id)
    if not keypoints:
        if force and existing:
            _save_dependencies(db, kb_id, [], True)
        return []

    kp_ids = {kp.id for kp in keypoints}
    rule_candidates = _infer_rule_dependency_edges(keypoints, doc_map)
    llm_candidates: list[_DependencyEdgeCandidate] = []
    llm_failed = False
    try:
        llm_candidates, _ = _infer_llm_dependency_edges(keypoints, doc_map)
    except Exception:
        llm_failed = True
        logger.exception("LLM dependency inference failed; using rule-only sparse graph")

    merged_candidates = _merge_dependency_edges_with_constraints(
        [*llm_candidates, *rule_candidates],
        kp_ids,
    )
    edge_records = [
        (candidate.from_id, candidate.to_id, candidate.confidence)
        for candidate in merged_candidates
    ]

    logger.info(
        "Learning-path dependency graph built for kb=%s keypoints=%d edges=%d llm_edges=%d rule_edges=%d llm_failed=%s version=%s",
        kb_id,
        len(keypoints),
        len(edge_records),
        len(llm_candidates),
        len(rule_candidates),
        llm_failed,
        DEPENDENCY_GRAPH_VERSION,
    )

    return _save_dependencies(db, kb_id, edge_records, force, relation=DEPENDENCY_RELATION)


def _build_sequential_deps(
    db: Session,
    kb_id: str,
    keypoints: list[Keypoint],
    force: bool,
) -> list[KeypointDependency]:
    """Build simple sequential dependencies from keypoint order (debug/test helper)."""
    edge_tuples: list[tuple[str, str]] = []
    for idx in range(len(keypoints) - 1):
        edge_tuples.append((keypoints[idx].id, keypoints[idx + 1].id))
    return _save_dependencies(db, kb_id, edge_tuples, force, relation=DEPENDENCY_RELATION)


def _save_dependencies(
    db: Session,
    kb_id: str,
    edge_tuples: list[tuple[Any, ...]],
    force: bool,
    relation: str = DEPENDENCY_RELATION,
) -> list[KeypointDependency]:
    """Persist dependency edges to DB, clearing old ones if force=True."""
    if force:
        db.query(KeypointDependency).filter(
            KeypointDependency.kb_id == kb_id
        ).delete()
        db.commit()

    deps: list[KeypointDependency] = []
    for raw_edge in edge_tuples:
        if len(raw_edge) < 2:
            continue
        from_id = str(raw_edge[0] or "")
        to_id = str(raw_edge[1] or "")
        confidence = _clamp_score(raw_edge[2], 1.0) if len(raw_edge) >= 3 else 1.0
        if not from_id or not to_id or from_id == to_id:
            continue
        dep = KeypointDependency(
            id=str(uuid4()),
            kb_id=kb_id,
            from_keypoint_id=from_id,
            to_keypoint_id=to_id,
            relation=relation,
            confidence=confidence,
        )
        db.add(dep)
        deps.append(dep)
    db.commit()
    return deps


# ---------------------------------------------------------------------------
# Learning path generation helpers
# ---------------------------------------------------------------------------


def _topological_sort(all_ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """Kahn's algorithm with deterministic output for cycle leftovers."""
    in_degree: dict[str, int] = {nid: 0 for nid in all_ids}
    adj: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edges:
        if from_id in in_degree and to_id in in_degree:
            adj[from_id].append(to_id)
            in_degree[to_id] += 1

    queue = deque([nid for nid in all_ids if in_degree[nid] == 0])
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    remaining = [nid for nid in all_ids if nid not in set(ordered)]
    remaining.sort()
    ordered.extend(remaining)
    return ordered


def _compute_depths(
    sorted_ids: list[str], prereq_map: dict[str, list[str]]
) -> dict[str, int]:
    """Compute graph depth from prerequisite map."""
    depth_map: dict[str, int] = {}
    for node_id in sorted_ids:
        prereqs = prereq_map.get(node_id, [])
        if not prereqs:
            depth_map[node_id] = 0
            continue
        depth_map[node_id] = max(depth_map.get(pid, 0) for pid in prereqs) + 1
    return depth_map


def _prioritized_topological_order(
    all_ids: list[str],
    edges: list[tuple[str, str]],
    rank_key: Callable[[str], tuple[Any, ...]],
) -> list[str]:
    """Topological order that prioritizes available nodes by a rank key."""
    in_degree: dict[str, int] = {nid: 0 for nid in all_ids}
    adj: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edges:
        if from_id in in_degree and to_id in in_degree:
            adj[from_id].append(to_id)
            in_degree[to_id] += 1

    available = [nid for nid in all_ids if in_degree[nid] == 0]
    ordered: list[str] = []
    while available:
        available.sort(key=rank_key)
        node = available.pop(0)
        ordered.append(node)
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                available.append(neighbor)

    remaining = [nid for nid in all_ids if nid not in set(ordered)]
    remaining.sort(key=rank_key)
    ordered.extend(remaining)
    return ordered


def _heuristic_difficulty(
    keypoint: Keypoint, prereq_count: int, out_count: int
) -> float:
    """Estimate keypoint difficulty with simple text + graph heuristics."""
    text_factor = min(len((keypoint.text or "").strip()) / 80.0, 1.0)
    explanation_factor = min(len((keypoint.explanation or "").strip()) / 120.0, 1.0)
    prereq_factor = min(prereq_count / 3.0, 1.0)
    out_factor = min(out_count / 4.0, 1.0)
    score = 0.18 + 0.34 * text_factor + 0.24 * prereq_factor + 0.14 * explanation_factor
    score += 0.1 * out_factor
    return round(max(0.05, min(1.0, score)), 3)


def _heuristic_importance(
    mastery: float, prereq_count: int, out_count: int
) -> float:
    """Estimate keypoint importance by graph centrality and learner mastery."""
    prereq_factor = min(prereq_count / 3.0, 1.0)
    out_factor = min(out_count / 5.0, 1.0)
    score = 0.22 + 0.42 * out_factor + 0.2 * prereq_factor + 0.16 * (1.0 - mastery)
    return round(max(0.05, min(1.0, score)), 3)


def _stage_by_complexity(
    depth: int,
    max_depth: int,
    difficulty: float,
    ability_level: str,
) -> str:
    """Assign stage by graph depth + difficulty, adjusted by learner ability."""
    depth_ratio = depth / max(1, max_depth)
    complexity = 0.55 * depth_ratio + 0.45 * difficulty
    if ability_level == "beginner":
        if complexity < 0.45:
            return "foundation"
        if complexity < 0.7:
            return "intermediate"
        if complexity < 0.88:
            return "advanced"
        return "application"
    if ability_level == "advanced":
        if complexity < 0.2:
            return "foundation"
        if complexity < 0.5:
            return "intermediate"
        if complexity < 0.78:
            return "advanced"
        return "application"
    if complexity < 0.3:
        return "foundation"
    if complexity < 0.6:
        return "intermediate"
    if complexity < 0.82:
        return "advanced"
    return "application"


def _estimate_learning_time(
    stage: str,
    difficulty: float,
    text: str,
    explanation: Optional[str],
    mastery: float,
) -> int:
    """Estimate study time (minutes) by stage, text complexity and mastery."""
    base_map = {
        "foundation": 8,
        "intermediate": 14,
        "advanced": 22,
        "application": 30,
    }
    base = base_map.get(stage, 12)
    text_bonus = min(len((text or "").strip()) // 20, 4)
    explanation_bonus = min(len((explanation or "").strip()) // 60, 4)
    diff_bonus = round(difficulty * 6)
    raw = base + text_bonus + explanation_bonus + diff_bonus
    mastery_factor = 1.0 - min(0.55, mastery * 0.45)
    minutes = int(round(raw * mastery_factor))
    return max(5, minutes)


def _format_edges_for_prompt(edges: list[tuple[str, str]]) -> str:
    """Format edges into text lines for prompts."""
    if not edges:
        return "(none)"
    return "\n".join([f"{from_id} -> {to_id}" for from_id, to_id in edges])


def _infer_stage_hints(
    keypoints: list[Keypoint],
    doc_map: dict[str, str],
    edges: list[tuple[str, str]],
    ability_level: str,
) -> dict[str, dict[str, Any]]:
    """Infer stage/difficulty/importance hints from LLM."""
    if not keypoints or len(keypoints) > 60:
        return {}
    points_text = _format_keypoints_for_prompt(keypoints, doc_map)
    edges_text = _format_edges_for_prompt(edges)
    try:
        payload = _invoke_prompt_json(
            STAGE_PROMPT,
            ability_level=ability_level,
            points_text=points_text,
            edges_text=edges_text,
        )
    except Exception:
        logger.exception("LLM stage hint inference failed; using heuristics")
        return {}

    hint_map: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, list):
        return hint_map
    valid_ids = {kp.id for kp in keypoints}
    for row in payload:
        if not isinstance(row, dict):
            continue
        kp_id = row.get("id")
        if kp_id not in valid_ids:
            continue
        stage = _normalize_stage(row.get("stage") or row.get("learning_stage_hint"))
        hint_map[kp_id] = {
            "stage_hint": stage,
            "difficulty": _clamp_score(
                row.get("difficulty_level", row.get("difficulty")), 0.5
            ),
            "importance": _clamp_score(
                row.get("importance_score", row.get("importance")), 0.5
            ),
        }
    return hint_map


def _fallback_modules_by_document(
    items: list[LearningPathItem],
) -> tuple[list[LearningPathModule], dict[str, str]]:
    """Fallback module grouping by document."""
    grouped: dict[str, list[LearningPathItem]] = defaultdict(list)
    for item in items:
        grouped[item.doc_id].append(item)

    modules: list[LearningPathModule] = []
    kp_to_module: dict[str, str] = {}
    idx = 1
    for _, module_items in sorted(
        grouped.items(), key=lambda pair: pair[1][0].step if pair[1] else 0
    ):
        module_items.sort(key=lambda it: it.step)
        module_id = f"module-{idx}"
        idx += 1
        doc_name = module_items[0].doc_name or "文档模块"
        keypoint_ids = [item.keypoint_id for item in module_items]
        module = LearningPathModule(
            module_id=module_id,
            name=f"{doc_name}模块",
            description=f"围绕 {doc_name} 的相关知识点学习。",
            keypoint_ids=keypoint_ids,
        )
        modules.append(module)
        for kp_id in keypoint_ids:
            kp_to_module[kp_id] = module_id
    return modules, kp_to_module


def _fallback_modules(
    items: list[LearningPathItem],
    edges: list[tuple[str, str]],
) -> tuple[list[LearningPathModule], dict[str, str]]:
    """Fallback module grouping by dependency-connected components, then document."""
    if not items:
        return [], {}
    if not edges:
        return _fallback_modules_by_document(items)

    item_map = {item.keypoint_id: item for item in items}
    item_ids = set(item_map.keys())
    undirected: dict[str, set[str]] = defaultdict(set)
    for from_id, to_id in edges:
        if from_id not in item_ids or to_id not in item_ids:
            continue
        undirected[from_id].add(to_id)
        undirected[to_id].add(from_id)
    for kp_id in item_ids:
        undirected.setdefault(kp_id, set())

    visited: set[str] = set()
    components: list[list[str]] = []
    for kp_id in sorted(item_ids, key=lambda nid: item_map[nid].step):
        if kp_id in visited:
            continue
        queue = deque([kp_id])
        comp: list[str] = []
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            comp.append(node)
            for neighbor in sorted(undirected.get(node, set()), key=lambda nid: item_map[nid].step):
                if neighbor not in visited:
                    queue.append(neighbor)
        comp.sort(key=lambda nid: item_map[nid].step)
        components.append(comp)

    components.sort(key=lambda comp: item_map[comp[0]].step if comp else 10**9)
    modules: list[LearningPathModule] = []
    kp_to_module: dict[str, str] = {}
    idx = 1

    def _chunk_size(component_len: int) -> int:
        if component_len <= 8:
            return component_len
        return 6

    for comp in components:
        size = _chunk_size(len(comp))
        for start in range(0, len(comp), size):
            part = comp[start : start + size]
            if not part:
                continue
            module_id = f"module-{idx}"
            idx += 1
            first_item = item_map[part[0]]
            short_title = (first_item.text or "知识点").strip()
            if len(short_title) > 12:
                short_title = f"{short_title[:12]}…"
            modules.append(
                LearningPathModule(
                    module_id=module_id,
                    name=f"学习模块 {len(modules) + 1}（{short_title}）",
                    description="按依赖结构自动分组的知识点集合。",
                    keypoint_ids=part,
                )
            )
            for kp_id in part:
                kp_to_module[kp_id] = module_id

    if not modules:
        return _fallback_modules_by_document(items)
    return modules, kp_to_module


def _infer_modules(
    items: list[LearningPathItem],
    edges: list[tuple[str, str]],
    ability_level: str,
) -> tuple[list[LearningPathModule], dict[str, str]]:
    """Infer topic modules with LLM and fallback to document grouping."""
    if len(items) < 4 or len(items) > 60:
        return _fallback_modules(items, edges)

    points_lines = []
    for item in items:
        points_lines.append(
            f"[{item.keypoint_id}] {item.text} | doc={item.doc_name or item.doc_id} "
            f"| stage={item.stage} | diff={item.difficulty:.2f} | imp={item.importance:.2f}"
        )
    points_text = "\n".join(points_lines)
    edges_text = _format_edges_for_prompt(edges)

    try:
        payload = _invoke_prompt_json(
            MODULE_PROMPT,
            ability_level=ability_level,
            points_text=points_text,
            edges_text=edges_text,
        )
    except Exception:
        logger.exception("LLM module inference failed; fallback to document grouping")
        return _fallback_modules(items, edges)

    if not isinstance(payload, dict):
        return _fallback_modules(items, edges)
    raw_modules = payload.get("modules")
    if not isinstance(raw_modules, list):
        return _fallback_modules(items, edges)

    item_map = {item.keypoint_id: item for item in items}
    modules: list[LearningPathModule] = []
    kp_to_module: dict[str, str] = {}
    module_name_seen: set[str] = set()

    for idx, raw in enumerate(raw_modules, start=1):
        if not isinstance(raw, dict):
            continue
        keypoint_ids = raw.get("keypoint_ids", [])
        if not isinstance(keypoint_ids, list):
            continue
        filtered_ids = [kp_id for kp_id in keypoint_ids if kp_id in item_map]
        filtered_ids = [kp_id for kp_id in filtered_ids if kp_id not in kp_to_module]
        if not filtered_ids:
            continue

        module_id = str(raw.get("module_id") or "").strip() or f"module-{idx}"
        if module_id in module_name_seen:
            module_id = f"{module_id}-{idx}"
        module_name_seen.add(module_id)

        name = str(raw.get("name") or "").strip() or f"学习模块 {idx}"
        description = str(raw.get("description") or "").strip() or "按主题组织的知识点集合。"
        modules.append(
            LearningPathModule(
                module_id=module_id,
                name=name,
                description=description,
                keypoint_ids=filtered_ids,
            )
        )
        for kp_id in filtered_ids:
            kp_to_module[kp_id] = module_id

    # Fill uncovered keypoints
    uncovered = [item.keypoint_id for item in items if item.keypoint_id not in kp_to_module]
    if uncovered:
        module_id = f"module-{len(modules) + 1}"
        modules.append(
            LearningPathModule(
                module_id=module_id,
                name="补充模块",
                description="自动补充未分组知识点。",
                keypoint_ids=uncovered,
            )
        )
        for kp_id in uncovered:
            kp_to_module[kp_id] = module_id

    if not modules:
        return _fallback_modules(items, edges)
    return modules, kp_to_module


def _attach_module_dependencies(
    modules: list[LearningPathModule],
    kp_to_module: dict[str, str],
    edges: list[tuple[str, str]],
    item_map: dict[str, LearningPathItem],
) -> None:
    """Derive module prerequisites and estimated time from keypoint edges/items."""
    dep_map: dict[str, set[str]] = defaultdict(set)
    for from_id, to_id in edges:
        from_module = kp_to_module.get(from_id)
        to_module = kp_to_module.get(to_id)
        if not from_module or not to_module or from_module == to_module:
            continue
        dep_map[to_module].add(from_module)

    for module in modules:
        module.prerequisite_modules = sorted(dep_map.get(module.module_id, set()))
        module.estimated_time = sum(
            item_map[kp_id].estimated_time
            for kp_id in module.keypoint_ids
            if kp_id in item_map
        )


def _infer_milestones(
    items: list[LearningPathItem],
    stages: list[LearningPathStage],
    modules: list[LearningPathModule],
) -> set[str]:
    """Infer milestone keypoints with LLM and fallback heuristics."""
    item_map = {item.keypoint_id: item for item in items}
    fallback_ids: set[str] = set()
    for stage in stages:
        if stage.milestone_keypoint_id:
            fallback_ids.add(stage.milestone_keypoint_id)
    for module in modules:
        best_id = None
        best_score = -1.0
        for kp_id in module.keypoint_ids:
            item = item_map.get(kp_id)
            if not item:
                continue
            if item.importance > best_score:
                best_score = item.importance
                best_id = kp_id
        if best_id:
            fallback_ids.add(best_id)

    if not items or len(items) > 60:
        return fallback_ids

    items_text = "\n".join(
        [
            f"[{it.keypoint_id}] stage={it.stage}, module={it.module}, "
            f"importance={it.importance:.2f}, text={it.text}"
            for it in items
        ]
    )
    stages_text = "\n".join(
        [f"{st.stage_id}: {','.join(st.keypoint_ids)}" for st in stages]
    )
    modules_text = "\n".join(
        [f"{mod.module_id}: {','.join(mod.keypoint_ids)}" for mod in modules]
    )
    try:
        payload = _invoke_prompt_json(
            MILESTONE_PROMPT,
            items_text=items_text,
            stages_text=stages_text,
            modules_text=modules_text,
        )
    except Exception:
        logger.exception("LLM milestone inference failed; using fallback milestones")
        return fallback_ids

    if not isinstance(payload, dict):
        return fallback_ids
    raw_ids = payload.get("milestone_ids")
    if not isinstance(raw_ids, list):
        return fallback_ids
    valid_ids = {item.keypoint_id for item in items}
    llm_ids = {kp_id for kp_id in raw_ids if kp_id in valid_ids}
    if not llm_ids:
        return fallback_ids
    return fallback_ids.union(llm_ids)


def _build_stages(items: list[LearningPathItem]) -> list[LearningPathStage]:
    """Build stage records from path items."""
    grouped: dict[str, list[LearningPathItem]] = defaultdict(list)
    for item in items:
        grouped[item.stage].append(item)

    stages: list[LearningPathStage] = []
    for stage_id in STAGE_ORDER:
        stage_items = sorted(grouped.get(stage_id, []), key=lambda item: item.step)
        if not stage_items:
            continue
        name, description = STAGE_META.get(stage_id, (stage_id, ""))
        milestone_item = next(
            (item for item in reversed(stage_items) if item.milestone),
            stage_items[-1],
        )
        stages.append(
            LearningPathStage(
                stage_id=stage_id,
                name=name,
                description=description,
                keypoint_ids=[item.keypoint_id for item in stage_items],
                milestone_keypoint_id=milestone_item.keypoint_id,
                estimated_time=sum(item.estimated_time for item in stage_items),
            )
        )
    return stages


def _build_path_summary(
    items: list[LearningPathItem],
    stages: list[LearningPathStage],
    modules: list[LearningPathModule],
    ability_level: str,
) -> dict[str, Any]:
    """Build path-level summary metadata."""
    total_items = len(items)
    if total_items == 0:
        return {
            "total_items": 0,
            "completed_items": 0,
            "completion_rate": 0.0,
            "total_estimated_time": 0,
            "stages_count": 0,
            "modules_count": 0,
            "current_stage": "foundation",
            "current_stage_label": STAGE_META["foundation"][0],
            "ability_level": ability_level,
        }

    completed_items = sum(1 for item in items if item.priority == "completed")
    completion_rate = round(completed_items / total_items, 4)
    item_map = {item.keypoint_id: item for item in items}

    current_stage = "completed"
    for stage in stages:
        unfinished = any(
            item_map[kp_id].priority != "completed"
            for kp_id in stage.keypoint_ids
            if kp_id in item_map
        )
        if unfinished:
            current_stage = stage.stage_id
            break

    current_stage_label = (
        "全部完成" if current_stage == "completed" else STAGE_META[current_stage][0]
    )
    return {
        "total_items": total_items,
        "completed_items": completed_items,
        "completion_rate": completion_rate,
        "total_estimated_time": sum(item.estimated_time for item in items),
        "stages_count": len(stages),
        "modules_count": len(modules),
        "current_stage": current_stage,
        "current_stage_label": current_stage_label,
        "ability_level": ability_level,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_unlocked_keypoint_ids(
    db: Session,
    user_id: str,
    kb_id: str,
    *,
    keypoints: list[Keypoint] | None = None,
    cluster_map: dict[str, Any] | None = None,
) -> set[str]:
    """
    Return representative keypoint ids that are currently unlocked by prerequisite mastery.

    This helper relies on the persisted dependency graph only. If a KB has no current
    dependency graph yet, all keypoints are treated as unlocked.
    """
    if keypoints is None or cluster_map is None:
        _, keypoints, cluster_map, _ = _load_clustered_kb_keypoints(db, user_id, kb_id)
    if not keypoints:
        return set()

    kp_map = {kp.id: kp for kp in keypoints}
    deps = (
        db.query(KeypointDependency)
        .filter(KeypointDependency.kb_id == kb_id)
        .all()
    )
    current_deps = [dep for dep in deps if _dependency_relation_is_current(dep.relation)]
    if not current_deps:
        return set(kp_map.keys())

    prereq_map: dict[str, list[str]] = defaultdict(list)
    for dep in current_deps:
        from_id = str(dep.from_keypoint_id or "")
        to_id = str(dep.to_keypoint_id or "")
        if (
            not from_id
            or not to_id
            or from_id == to_id
            or from_id not in kp_map
            or to_id not in kp_map
        ):
            continue
        prereq_map[to_id].append(from_id)

    unlocked: set[str] = set()
    for kp_id in kp_map:
        blocked = False
        for prereq_id in prereq_map.get(kp_id, []):
            prereq_cluster = cluster_map.get(prereq_id)
            prereq_mastery = (
                prereq_cluster.mastery_level_max
                if prereq_cluster is not None
                else float(kp_map[prereq_id].mastery_level or 0.0)
            )
            if prereq_mastery < MASTERY_PREREQ_THRESHOLD:
                blocked = True
                break
        if not blocked:
            unlocked.add(kp_id)
    return unlocked


def generate_learning_path(
    db: Session,
    user_id: str,
    kb_id: str,
    limit: int = 15,
    force: bool = False,
) -> tuple[
    list[LearningPathItem],
    list[LearningPathEdge],
    list[LearningPathStage],
    list[LearningPathModule],
    dict[str, Any],
]:
    """Generate personalized learning path with stages/modules/milestones."""
    if not force:
        cached = _get_cached_learning_path_result(user_id, kb_id, limit)
        if cached is not None:
            return cached

    _, keypoints, cluster_map, doc_map = _load_clustered_kb_keypoints(db, user_id, kb_id)
    if not keypoints:
        empty_result = ([], [], [], [], {})
        _set_cached_learning_path_result(user_id, kb_id, limit, empty_result)
        return empty_result

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    ability_level = profile.ability_level if profile and profile.ability_level else "intermediate"

    kp_map = {kp.id: kp for kp in keypoints}

    deps = build_dependency_graph(db, user_id, kb_id, force=force)
    edge_records = [
        (
            dep.from_keypoint_id,
            dep.to_keypoint_id,
            round(float(dep.confidence if dep.confidence is not None else 1.0), 3),
        )
        for dep in deps
        if dep.from_keypoint_id in kp_map and dep.to_keypoint_id in kp_map
    ]
    edge_tuples = _remove_cycles([(from_id, to_id) for from_id, to_id, _ in edge_records])
    valid_pairs = set(edge_tuples)
    edge_records = [
        (from_id, to_id, confidence)
        for from_id, to_id, confidence in edge_records
        if (from_id, to_id) in valid_pairs
    ]
    edge_confidence_map = {
        (from_id, to_id): confidence for from_id, to_id, confidence in edge_records
    }

    prereq_map: dict[str, list[str]] = defaultdict(list)
    outgoing_map: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edge_tuples:
        prereq_map[to_id].append(from_id)
        outgoing_map[from_id].append(to_id)

    all_ids = [kp.id for kp in keypoints]
    sorted_ids = _topological_sort(all_ids, edge_tuples)
    base_order_idx = {kp_id: idx for idx, kp_id in enumerate(sorted_ids)}
    depth_map = _compute_depths(sorted_ids, prereq_map)
    max_depth = max(depth_map.values(), default=0)

    llm_hints = _infer_stage_hints(keypoints, doc_map, edge_tuples, ability_level)

    runtime_meta: dict[str, dict[str, Any]] = {}
    for kp_id in sorted_ids:
        kp = kp_map.get(kp_id)
        if not kp:
            continue
        cluster = cluster_map.get(kp_id)
        if not cluster:
            continue

        mastery = cluster.mastery_level_max
        attempt_count = cluster.attempt_count_sum
        prereq_count = len(prereq_map.get(kp_id, []))
        outgoing_count = len(outgoing_map.get(kp_id, []))
        hint = llm_hints.get(kp_id, {})
        difficulty = hint.get(
            "difficulty", _heuristic_difficulty(kp, prereq_count, outgoing_count)
        )
        importance = hint.get(
            "importance", _heuristic_importance(mastery, prereq_count, outgoing_count)
        )
        stage = hint.get("stage_hint") or _stage_by_complexity(
            depth=depth_map.get(kp_id, 0),
            max_depth=max_depth,
            difficulty=difficulty,
            ability_level=ability_level,
        )

        prereq_ids = sorted(
            prereq_map.get(kp_id, []),
            key=lambda pid: (depth_map.get(pid, 0), base_order_idx.get(pid, 10**9), pid),
        )
        unmet_prereq_ids: list[str] = []
        unmet_prereqs: list[str] = []
        for prereq_id in prereq_ids:
            prereq_kp = kp_map.get(prereq_id)
            prereq_cluster = cluster_map.get(prereq_id)
            prereq_mastery = (
                prereq_cluster.mastery_level_max
                if prereq_cluster is not None
                else float(prereq_kp.mastery_level or 0.0) if prereq_kp else 0.0
            )
            prereq_text = (
                prereq_cluster.representative_text
                if prereq_cluster is not None
                else str(prereq_kp.text or "") if prereq_kp else ""
            )
            if prereq_text and prereq_mastery < MASTERY_PREREQ_THRESHOLD:
                unmet_prereq_ids.append(prereq_id)
                unmet_prereqs.append(prereq_text)
        difficulty = round(_clamp_score(difficulty, 0.5), 3)
        importance = round(_clamp_score(importance, 0.5), 3)
        runtime_meta[kp_id] = {
            "mastery": mastery,
            "attempt_count": attempt_count,
            "difficulty": difficulty,
            "importance": importance,
            "stage": stage,
            "prerequisite_ids": prereq_ids,
            "unmet_prereq_ids": unmet_prereq_ids,
            "unmet_prereq_texts": unmet_prereqs,
            "is_unlocked": len(unmet_prereq_ids) == 0,
            "path_level": depth_map.get(kp_id, 0),
            "unlocks_count": outgoing_count,
            "estimated_time": _estimate_learning_time(
                stage=stage,
                difficulty=difficulty,
                text=kp.text,
                explanation=cluster.explanation,
                mastery=mastery,
            ),
            "member_count": cluster.member_count,
            "source_doc_ids": cluster.source_doc_ids,
            "source_doc_names": cluster.source_doc_names,
        }

    def _display_rank_key(node_id: str) -> tuple[Any, ...]:
        meta = runtime_meta.get(node_id, {})
        kp = kp_map.get(node_id)
        return (
            0 if meta.get("is_unlocked", True) else 1,
            int(meta.get("path_level", 0)),
            -int(meta.get("unlocks_count", 0)),
            -float(meta.get("importance", 0.0)),
            float(meta.get("mastery", 0.0)),
            _keypoint_local_sort_tuple(kp) if kp is not None else ("", 10**9, 10**9, "9999", node_id),
            str(node_id),
        )

    display_ids = _prioritized_topological_order(all_ids, edge_tuples, _display_rank_key)

    items: list[LearningPathItem] = []
    for step, kp_id in enumerate(display_ids, start=1):
        kp = kp_map.get(kp_id)
        cluster = cluster_map.get(kp_id)
        meta = runtime_meta.get(kp_id)
        if not kp or not cluster or not meta:
            continue
        items.append(
            LearningPathItem(
                keypoint_id=kp.id,
                text=kp.text,
                doc_id=kp.doc_id,
                doc_name=doc_map.get(kp.doc_id),
                mastery_level=float(meta["mastery"]),
                priority=mastery_priority(float(meta["mastery"])),
                step=step,
                prerequisites=list(meta["unmet_prereq_texts"]),
                prerequisite_ids=list(meta["prerequisite_ids"]),
                unmet_prerequisite_ids=list(meta["unmet_prereq_ids"]),
                is_unlocked=bool(meta["is_unlocked"]),
                action=mastery_action(float(meta["mastery"]), int(meta["attempt_count"])),
                stage=str(meta["stage"]),
                module="module-1",
                difficulty=float(meta["difficulty"]),
                importance=float(meta["importance"]),
                path_level=int(meta["path_level"]),
                unlocks_count=int(meta["unlocks_count"]),
                estimated_time=int(meta["estimated_time"]),
                milestone=False,
                member_count=int(meta["member_count"]),
                source_doc_ids=list(meta["source_doc_ids"]),
                source_doc_names=list(meta["source_doc_names"]),
            )
        )

    if limit and len(items) > limit:
        items = items[:limit]

    visible_ids = {item.keypoint_id for item in items}
    edge_records = [
        (from_id, to_id, confidence)
        for from_id, to_id, confidence in edge_records
        if from_id in visible_ids and to_id in visible_ids
    ]
    edge_tuples = [(from_id, to_id) for from_id, to_id, _ in edge_records]
    edge_confidence_map = {
        (from_id, to_id): confidence for from_id, to_id, confidence in edge_records
    }

    modules, kp_to_module = _infer_modules(items, edge_tuples, ability_level)
    item_map = {item.keypoint_id: item for item in items}
    _attach_module_dependencies(modules, kp_to_module, edge_tuples, item_map)

    for item in items:
        item.module = kp_to_module.get(item.keypoint_id, "module-1")

    stages = _build_stages(items)
    milestone_ids = _infer_milestones(items, stages, modules)
    for item in items:
        item.milestone = item.keypoint_id in milestone_ids

    # Rebuild stages so milestone_keypoint_id stays accurate after milestone update.
    stages = _build_stages(items)
    path_summary = _build_path_summary(items, stages, modules, ability_level)

    edges = [
        LearningPathEdge(
            from_id=from_id,
            to_id=to_id,
            relation="prerequisite",
            confidence=float(edge_confidence_map.get((from_id, to_id), 1.0)),
        )
        for from_id, to_id in edge_tuples
    ]
    result_payload = (items, edges, stages, modules, path_summary)
    _set_cached_learning_path_result(user_id, kb_id, limit, result_payload)
    return result_payload


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


def invalidate_dependency_cache(db: Session, kb_id: Optional[str]) -> int:
    """Delete cached dependency edges for a KB. Returns deleted count."""
    if not kb_id:
        return 0
    count = (
        db.query(KeypointDependency)
        .filter(KeypointDependency.kb_id == kb_id)
        .delete()
    )
    db.commit()
    invalidate_learning_path_result_cache(db, kb_id)
    return count


def invalidate_learning_path_result_cache(db: Session | None, kb_id: Optional[str]) -> int:
    """Delete in-process cached learning-path results for a KB. Returns removed entry count."""
    if not kb_id:
        return 0
    removed = 0
    with _learning_path_result_cache_lock:
        for key in list(_learning_path_result_cache.keys()):
            _, cached_kb_id, _, _ = key
            if cached_kb_id != kb_id:
                continue
            _learning_path_result_cache.pop(key, None)
            removed += 1
    return removed
