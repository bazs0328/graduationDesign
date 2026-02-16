"""Cross-document learning path: LLM dependency inference + topological sort + mastery filtering."""

import logging
from collections import defaultdict, deque
from typing import Optional
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.models import Document, Keypoint, KeypointDependency
from app.schemas import LearningPathEdge, LearningPathItem
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt for dependency inference
# ---------------------------------------------------------------------------

DEPENDENCY_SYSTEM = (
    "You are an expert learning-path planner. Given a list of knowledge points "
    "(each with an ID, text, and the document it belongs to), analyze their "
    "prerequisite relationships.\n\n"
    "Rules:\n"
    "- Only output prerequisite edges where learning A first is clearly necessary before B.\n"
    "- Do NOT output every possible association; only strong prerequisites.\n"
    "- Within the same document, infer order from the knowledge progression.\n"
    "- Across documents, infer from semantic dependency (e.g. 'derivatives' requires 'limits').\n"
    '- Return a JSON array of objects: [{{"from_id": "...", "to_id": "..."}}]\n'
    "  where from_id is the prerequisite and to_id depends on it.\n"
    "- If there are no clear prerequisites, return an empty array [].\n"
    "- Return ONLY the JSON array, no extra text."
)

DEPENDENCY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", DEPENDENCY_SYSTEM),
        (
            "human",
            "Analyze prerequisites among these knowledge points:\n\n{points_text}\n\n"
            "Return JSON array of prerequisite edges only.",
        ),
    ]
)


# ---------------------------------------------------------------------------
# Dependency graph building
# ---------------------------------------------------------------------------


def _format_keypoints_for_prompt(
    keypoints: list[Keypoint], doc_map: dict[str, str]
) -> str:
    """Format keypoints grouped by document for the LLM prompt."""
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


def _remove_cycles(edges: list[tuple[str, str]], all_ids: set[str]) -> list[tuple[str, str]]:
    """Remove edges that would create cycles using iterative DFS."""
    adj: dict[str, list[str]] = defaultdict(list)
    clean_edges: list[tuple[str, str]] = []

    for from_id, to_id in edges:
        adj[from_id].append(to_id)
        # Quick cycle check: can to_id reach from_id through existing adj?
        if _has_path(adj, to_id, from_id):
            adj[from_id].pop()
            continue
        clean_edges.append((from_id, to_id))

    return clean_edges


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


def build_dependency_graph(
    db: Session,
    user_id: str,
    kb_id: str,
    force: bool = False,
) -> list[KeypointDependency]:
    """Build or retrieve cached dependency graph for a KB using LLM inference."""

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

    kp_ids = {kp.id for kp in keypoints}
    doc_ids = {kp.doc_id for kp in keypoints}

    # Single-document KB: use sequential order, skip LLM
    if len(doc_ids) <= 1:
        return _build_sequential_deps(db, kb_id, keypoints, force)

    doc_map = {
        row.id: row.filename
        for row in db.query(Document.id, Document.filename)
        .filter(Document.id.in_(doc_ids))
        .all()
    }

    points_text = _format_keypoints_for_prompt(keypoints, doc_map)

    try:
        llm = get_llm(temperature=0.1)
        safe_text = points_text.replace("{", "{{").replace("}", "}}")
        messages = DEPENDENCY_PROMPT.format_messages(points_text=safe_text)
        result = llm.invoke(messages)
        raw_edges = safe_json_loads(result.content)
    except Exception:
        logger.exception("LLM dependency inference failed, falling back to sequential")
        return _build_sequential_deps(db, kb_id, keypoints, force)

    if not isinstance(raw_edges, list):
        return _build_sequential_deps(db, kb_id, keypoints, force)

    # Validate and deduplicate edges
    edge_tuples: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        from_id = edge.get("from_id", "")
        to_id = edge.get("to_id", "")
        if from_id not in kp_ids or to_id not in kp_ids:
            continue
        if from_id == to_id:
            continue
        pair = (from_id, to_id)
        if pair in seen:
            continue
        seen.add(pair)
        edge_tuples.append(pair)

    # Remove cycles
    edge_tuples = _remove_cycles(edge_tuples, kp_ids)

    return _save_dependencies(db, kb_id, edge_tuples, force)


def _build_sequential_deps(
    db: Session,
    kb_id: str,
    keypoints: list[Keypoint],
    force: bool,
) -> list[KeypointDependency]:
    """Build simple sequential dependencies from keypoint order."""
    edge_tuples: list[tuple[str, str]] = []
    for i in range(len(keypoints) - 1):
        edge_tuples.append((keypoints[i].id, keypoints[i + 1].id))
    return _save_dependencies(db, kb_id, edge_tuples, force)


def _save_dependencies(
    db: Session,
    kb_id: str,
    edge_tuples: list[tuple[str, str]],
    force: bool,
) -> list[KeypointDependency]:
    """Persist dependency edges to DB, clearing old ones if force."""
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
# Topological sort + mastery-weighted path generation
# ---------------------------------------------------------------------------


def _topological_sort(
    all_ids: list[str], edges: list[tuple[str, str]]
) -> list[str]:
    """Kahn's algorithm. Nodes in cycles are appended at the end."""
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

    # Remaining nodes (in cycles) sorted by id for determinism
    remaining = [nid for nid in all_ids if nid not in set(ordered)]
    remaining.sort()
    ordered.extend(remaining)
    return ordered


def generate_learning_path(
    db: Session,
    user_id: str,
    kb_id: str,
    limit: int = 15,
    force: bool = False,
) -> tuple[list[LearningPathItem], list[LearningPathEdge]]:
    """Generate a personalized learning path with dependency-aware ordering."""

    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id == kb_id)
        .order_by(Keypoint.doc_id, Keypoint.id)
        .all()
    )

    if not keypoints:
        return [], []

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
        (d.from_keypoint_id, d.to_keypoint_id)
        for d in deps
        if d.from_keypoint_id in kp_map and d.to_keypoint_id in kp_map
    ]

    # Build prerequisite lookup
    prereq_map: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edge_tuples:
        prereq_map[to_id].append(from_id)

    all_ids = [kp.id for kp in keypoints]
    sorted_ids = _topological_sort(all_ids, edge_tuples)

    # Build path items
    items: list[LearningPathItem] = []
    step = 0
    for kp_id in sorted_ids:
        kp = kp_map.get(kp_id)
        if not kp:
            continue

        mastery = kp.mastery_level or 0.0
        step += 1

        # Determine unmet prerequisites
        unmet_prereqs = []
        for prereq_id in prereq_map.get(kp_id, []):
            prereq_kp = kp_map.get(prereq_id)
            if prereq_kp and (prereq_kp.mastery_level or 0.0) < 0.6:
                unmet_prereqs.append(prereq_kp.text)

        # Priority
        if mastery >= 0.8:
            priority = "completed"
        elif mastery < 0.3:
            priority = "high"
        elif mastery < 0.7:
            priority = "medium"
        else:
            priority = "low"

        # Action
        if mastery >= 0.8:
            action = "review"
        elif (kp.attempt_count or 0) == 0:
            action = "study"
        else:
            action = "quiz"

        items.append(
            LearningPathItem(
                keypoint_id=kp.id,
                text=kp.text,
                doc_id=kp.doc_id,
                doc_name=doc_map.get(kp.doc_id),
                mastery_level=mastery,
                priority=priority,
                step=step,
                prerequisites=unmet_prereqs,
                action=action,
            )
        )

    # Build edges for frontend graph
    edges = [
        LearningPathEdge(from_id=f, to_id=t, relation="prerequisite")
        for f, t in edge_tuples
    ]

    if limit and len(items) > limit:
        items = items[:limit]

    return items, edges


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
    return count
