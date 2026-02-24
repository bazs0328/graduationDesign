"""Cross-document learning path with stages, modules and milestones."""

import logging
import time
from collections import defaultdict, deque
from copy import deepcopy
from threading import Lock
from typing import Any, Optional
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.models import Document, Keypoint, KeypointDependency, LearnerProfile
from app.schemas import (
    LearningPathEdge,
    LearningPathItem,
    LearningPathModule,
    LearningPathStage,
)
from app.services.mastery import (
    MASTERY_MASTERED,
    MASTERY_PREREQ_THRESHOLD,
    mastery_action,
    mastery_priority,
)
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

_LEARNING_PATH_RESULT_CACHE_TTL_SECONDS = 300
_LEARNING_PATH_RESULT_CACHE_MAX_ENTRIES = 64
_learning_path_result_cache: dict[tuple[str, str, int], tuple[float, Any]] = {}
_learning_path_result_cache_lock = Lock()

STAGE_ORDER = ["foundation", "intermediate", "advanced", "application"]
STAGE_META = {
    "foundation": ("基础阶段", "先建立核心概念与术语理解。"),
    "intermediate": ("进阶阶段", "连接概念并形成系统化理解。"),
    "advanced": ("高级阶段", "攻克复杂推理与综合分析问题。"),
    "application": ("应用阶段", "迁移到实战场景并完成综合应用。"),
}


def _learning_path_cache_key(user_id: str, kb_id: str, limit: int) -> tuple[str, str, int]:
    return (str(user_id), str(kb_id), int(limit or 0))


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


# ---------------------------------------------------------------------------
# Dependency graph building
# ---------------------------------------------------------------------------


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
            if not isinstance(edge, dict):
                continue
            from_id = edge.get("from_id", "")
            to_id = edge.get("to_id", "")
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
    if not force:
        existing = (
            db.query(KeypointDependency)
            .filter(KeypointDependency.kb_id == kb_id)
            .all()
        )
        if existing:
            return existing

    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id == kb_id)
        .order_by(Keypoint.doc_id, Keypoint.id)
        .all()
    )
    if not keypoints:
        return []

    doc_ids = {kp.doc_id for kp in keypoints}
    if len(doc_ids) <= 1:
        return _build_sequential_deps(db, kb_id, keypoints, force)

    doc_map = {
        row.id: row.filename
        for row in db.query(Document.id, Document.filename)
        .filter(Document.id.in_(doc_ids))
        .all()
    }
    points_text = _format_keypoints_for_prompt(keypoints, doc_map)
    kp_ids = {kp.id for kp in keypoints}

    try:
        payload = _invoke_prompt_json(DEPENDENCY_PROMPT, points_text=points_text)
        edge_tuples, _ = _parse_dependency_payload(payload, kp_ids)
    except Exception:
        logger.exception("LLM dependency inference failed, falling back to sequential")
        return _build_sequential_deps(db, kb_id, keypoints, force)

    if not edge_tuples:
        return _build_sequential_deps(db, kb_id, keypoints, force)

    edge_tuples = _remove_cycles(edge_tuples)
    return _save_dependencies(db, kb_id, edge_tuples, force)


def _build_sequential_deps(
    db: Session,
    kb_id: str,
    keypoints: list[Keypoint],
    force: bool,
) -> list[KeypointDependency]:
    """Build simple sequential dependencies from keypoint order."""
    edge_tuples: list[tuple[str, str]] = []
    for idx in range(len(keypoints) - 1):
        edge_tuples.append((keypoints[idx].id, keypoints[idx + 1].id))
    return _save_dependencies(db, kb_id, edge_tuples, force)


def _save_dependencies(
    db: Session,
    kb_id: str,
    edge_tuples: list[tuple[str, str]],
    force: bool,
) -> list[KeypointDependency]:
    """Persist dependency edges to DB, clearing old ones if force=True."""
    if force:
        db.query(KeypointDependency).filter(
            KeypointDependency.kb_id == kb_id
        ).delete()
        db.commit()

    deps: list[KeypointDependency] = []
    for from_id, to_id in edge_tuples:
        dep = KeypointDependency(
            id=str(uuid4()),
            kb_id=kb_id,
            from_keypoint_id=from_id,
            to_keypoint_id=to_id,
            relation="prerequisite",
            confidence=1.0,
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


def _fallback_modules(items: list[LearningPathItem]) -> tuple[list[LearningPathModule], dict[str, str]]:
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


def _infer_modules(
    items: list[LearningPathItem],
    edges: list[tuple[str, str]],
    ability_level: str,
) -> tuple[list[LearningPathModule], dict[str, str]]:
    """Infer topic modules with LLM and fallback to document grouping."""
    if len(items) < 4 or len(items) > 60:
        return _fallback_modules(items)

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
        return _fallback_modules(items)

    if not isinstance(payload, dict):
        return _fallback_modules(items)
    raw_modules = payload.get("modules")
    if not isinstance(raw_modules, list):
        return _fallback_modules(items)

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
        return _fallback_modules(items)
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

    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id == kb_id)
        .order_by(Keypoint.doc_id, Keypoint.id)
        .all()
    )
    if not keypoints:
        empty_result = ([], [], [], [], {})
        _set_cached_learning_path_result(user_id, kb_id, limit, empty_result)
        return empty_result

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    ability_level = profile.ability_level if profile and profile.ability_level else "intermediate"

    kp_map = {kp.id: kp for kp in keypoints}
    doc_ids = {kp.doc_id for kp in keypoints}
    doc_map = {
        row.id: row.filename
        for row in db.query(Document.id, Document.filename)
        .filter(Document.id.in_(doc_ids))
        .all()
    }

    deps = build_dependency_graph(db, user_id, kb_id, force=force)
    edge_tuples = [
        (dep.from_keypoint_id, dep.to_keypoint_id)
        for dep in deps
        if dep.from_keypoint_id in kp_map and dep.to_keypoint_id in kp_map
    ]
    edge_tuples = _remove_cycles(edge_tuples)

    prereq_map: dict[str, list[str]] = defaultdict(list)
    outgoing_map: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edge_tuples:
        prereq_map[to_id].append(from_id)
        outgoing_map[from_id].append(to_id)

    sorted_ids = _topological_sort([kp.id for kp in keypoints], edge_tuples)
    depth_map = _compute_depths(sorted_ids, prereq_map)
    max_depth = max(depth_map.values(), default=0)

    llm_hints = _infer_stage_hints(keypoints, doc_map, edge_tuples, ability_level)

    items: list[LearningPathItem] = []
    step = 0
    for kp_id in sorted_ids:
        kp = kp_map.get(kp_id)
        if not kp:
            continue

        mastery = kp.mastery_level or 0.0
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

        unmet_prereqs = []
        for prereq_id in prereq_map.get(kp_id, []):
            prereq_kp = kp_map.get(prereq_id)
            if prereq_kp and (prereq_kp.mastery_level or 0.0) < MASTERY_PREREQ_THRESHOLD:
                unmet_prereqs.append(prereq_kp.text)

        step += 1
        items.append(
            LearningPathItem(
                keypoint_id=kp.id,
                text=kp.text,
                doc_id=kp.doc_id,
                doc_name=doc_map.get(kp.doc_id),
                mastery_level=mastery,
                priority=mastery_priority(mastery),
                step=step,
                prerequisites=unmet_prereqs,
                action=mastery_action(mastery, kp.attempt_count or 0),
                stage=stage,
                module="module-1",
                difficulty=round(_clamp_score(difficulty, 0.5), 3),
                importance=round(_clamp_score(importance, 0.5), 3),
                estimated_time=_estimate_learning_time(
                    stage=stage,
                    difficulty=_clamp_score(difficulty, 0.5),
                    text=kp.text,
                    explanation=kp.explanation,
                    mastery=mastery,
                ),
                milestone=False,
            )
        )

    if limit and len(items) > limit:
        items = items[:limit]

    visible_ids = {item.keypoint_id for item in items}
    edge_tuples = [
        (from_id, to_id)
        for from_id, to_id in edge_tuples
        if from_id in visible_ids and to_id in visible_ids
    ]

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
        LearningPathEdge(from_id=from_id, to_id=to_id, relation="prerequisite")
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
            _, cached_kb_id, _ = key
            if cached_kb_id != kb_id:
                continue
            _learning_path_result_cache.pop(key, None)
            removed += 1
    return removed
