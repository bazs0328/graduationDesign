from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Document, Keypoint
from app.services.keypoint_dedup import (
    KeypointCluster,
    build_keypoint_cluster_index,
    cluster_kb_keypoints,
)


@dataclass
class AggregateMasteryPoint:
    keypoint_id: str
    text: str
    kb_id: str | None
    mastery_level: float
    attempt_count: int
    correct_count: int
    source_doc_ids: list[str]
    member_keypoint_ids: list[str]


def resolve_effective_kb_id(
    db: Session,
    user_id: str,
    *,
    doc_id: str | None = None,
    kb_id: str | None = None,
) -> str | None:
    """Resolve the KB that should govern aggregate mastery semantics."""
    if kb_id:
        return str(kb_id)
    if not doc_id:
        return None
    row = (
        db.query(Document.kb_id)
        .filter(Document.id == doc_id, Document.user_id == user_id)
        .first()
    )
    if not row:
        return None
    resolved = row[0]
    return str(resolved) if resolved else None


def build_kb_cluster_maps(
    db: Session,
    user_id: str,
    kb_id: str,
) -> tuple[list[KeypointCluster], dict[str, str], dict[str, KeypointCluster]]:
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    member_to_rep = build_keypoint_cluster_index(clusters)
    rep_cluster_map = {cluster.representative_id: cluster for cluster in clusters}
    return clusters, member_to_rep, rep_cluster_map


def collapse_keypoint_ids_to_aggregate_targets(
    db: Session,
    user_id: str,
    *,
    doc_id: str | None = None,
    kb_id: str | None = None,
    keypoint_ids: list[str] | None = None,
    member_to_rep: dict[str, str] | None = None,
) -> list[str]:
    """Collapse raw keypoint ids to KB representative ids when a KB is available."""
    items = [str(item) for item in (keypoint_ids or []) if str(item or "").strip()]
    if not items:
        return []
    effective_kb_id = resolve_effective_kb_id(db, user_id, doc_id=doc_id, kb_id=kb_id)
    if not effective_kb_id:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out
    if member_to_rep is None:
        _, member_to_rep, _ = build_kb_cluster_maps(db, user_id, effective_kb_id)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        target = str(member_to_rep.get(item, item))
        if not target or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def resolve_keypoint_id_to_aggregate_target(
    db: Session,
    user_id: str,
    keypoint_id: str,
    *,
    doc_id: str | None = None,
    kb_id: str | None = None,
    member_to_rep: dict[str, str] | None = None,
) -> str:
    collapsed = collapse_keypoint_ids_to_aggregate_targets(
        db,
        user_id,
        doc_id=doc_id,
        kb_id=kb_id,
        keypoint_ids=[keypoint_id],
        member_to_rep=member_to_rep,
    )
    return collapsed[0] if collapsed else str(keypoint_id)


def _cluster_to_aggregate_point(cluster: KeypointCluster, kb_id: str) -> AggregateMasteryPoint:
    rep = cluster.representative_keypoint
    return AggregateMasteryPoint(
        keypoint_id=str(rep.id),
        text=str(rep.text or "").strip(),
        kb_id=kb_id,
        mastery_level=float(cluster.mastery_level_max or 0.0),
        attempt_count=int(cluster.attempt_count_sum or 0),
        correct_count=int(cluster.correct_count_sum or 0),
        source_doc_ids=list(cluster.source_doc_ids),
        member_keypoint_ids=list(cluster.member_keypoint_ids),
    )


def list_kb_aggregate_mastery_points(
    db: Session,
    user_id: str,
    kb_id: str,
) -> list[AggregateMasteryPoint]:
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    return [_cluster_to_aggregate_point(cluster, kb_id) for cluster in clusters]


def list_user_aggregate_mastery_points(
    db: Session,
    user_id: str,
) -> list[AggregateMasteryPoint]:
    """List aggregate mastery points across KBs plus raw fallback for non-KB docs."""
    rows = (
        db.query(Keypoint.kb_id)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id.isnot(None))
        .distinct()
        .all()
    )
    kb_ids = [str(row[0]) for row in rows if row and row[0]]

    points: list[AggregateMasteryPoint] = []
    for kb_id in kb_ids:
        points.extend(list_kb_aggregate_mastery_points(db, user_id, kb_id))

    raw_rows = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id.is_(None))
        .all()
    )
    for kp in raw_rows:
        points.append(
            AggregateMasteryPoint(
                keypoint_id=str(kp.id),
                text=str(kp.text or "").strip(),
                kb_id=None,
                mastery_level=float(kp.mastery_level or 0.0),
                attempt_count=int(kp.attempt_count or 0),
                correct_count=int(kp.correct_count or 0),
                source_doc_ids=[str(kp.doc_id)] if kp.doc_id else [],
                member_keypoint_ids=[str(kp.id)],
            )
        )
    return points
