import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.vectorstore import get_vectorstore
from app.models import Document, Keypoint
from app.utils.chroma_filters import build_chroma_eq_filter

logger = logging.getLogger(__name__)

_SEMANTIC_DISTANCE_MAX = 0.22
_SEMANTIC_TOP_K = 6
_SEMANTIC_MIN_COMPARE_LEN = 4
_SEMANTIC_BIGRAM_JACCARD_MIN = 0.45

_PREFIX_PATTERNS = [
    re.compile(r"^\s*\d+\s*[.)、．]\s*"),
    re.compile(r"^\s*[A-Za-z]\s*[.)、．]\s*"),
    re.compile(r"^\s*[（(]\s*[0-9一二三四五六七八九十百零]+\s*[)）]\s*"),
    re.compile(r"^\s*[一二三四五六七八九十百零]+\s*[、.．]\s*"),
]
_TAIL_PUNCT = "。；;，,：:、 "
_COMPARE_REMOVE_RE = re.compile(
    r"[\s\-_—·•、，,。；;：:()（）\[\]{}<>《》\"'“”‘’]+"
)


def normalize_keypoint_text(text: str) -> str:
    """Normalize keypoint text for stable comparison and display-level matching."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    changed = True
    while changed and s:
        changed = False
        for pattern in _PREFIX_PATTERNS:
            updated = pattern.sub("", s, count=1).strip()
            if updated != s:
                s = updated
                changed = True
    s = s.rstrip(_TAIL_PUNCT).strip()
    return s


def _comparison_key(text: str) -> str:
    normalized = normalize_keypoint_text(text)
    return _COMPARE_REMOVE_RE.sub("", normalized)


def _bigram_set(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[idx : idx + 2] for idx in range(len(text) - 1)}


def _bigram_jaccard(a: str, b: str) -> float:
    sa = _bigram_set(a)
    sb = _bigram_set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def _sortable_created_at(value: Optional[datetime]) -> datetime:
    return value or datetime.max


def _member_sort_key(member: "KeypointClusterMember") -> tuple[datetime, str]:
    return (_sortable_created_at(member.keypoint.created_at), str(member.keypoint.id or ""))


class _DisjointSet:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
            return
        if self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
            return
        self.parent[rb] = ra
        self.rank[ra] += 1


@dataclass
class KeypointClusterMember:
    keypoint: Keypoint
    doc_name: Optional[str]
    normalized_text: str
    comparison_key: str

    @property
    def id(self) -> str:
        return str(self.keypoint.id)

    @property
    def doc_id(self) -> str:
        return str(self.keypoint.doc_id)


@dataclass
class KeypointCluster:
    representative: KeypointClusterMember
    members: list[KeypointClusterMember]

    @property
    def representative_keypoint(self) -> Keypoint:
        return self.representative.keypoint

    @property
    def representative_id(self) -> str:
        return self.representative.id

    @property
    def representative_doc_id(self) -> str:
        return self.representative.doc_id

    @property
    def representative_doc_name(self) -> Optional[str]:
        return self.representative.doc_name

    @property
    def representative_text(self) -> str:
        return str(self.representative.keypoint.text or "")

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def member_keypoint_ids(self) -> list[str]:
        return [member.id for member in self.sorted_members()]

    @property
    def mastery_level_max(self) -> float:
        return max((float(member.keypoint.mastery_level or 0.0) for member in self.members), default=0.0)

    @property
    def attempt_count_sum(self) -> int:
        return sum(int(member.keypoint.attempt_count or 0) for member in self.members)

    @property
    def correct_count_sum(self) -> int:
        return sum(int(member.keypoint.correct_count or 0) for member in self.members)

    @property
    def explanation(self) -> Optional[str]:
        rep_explanation = (self.representative.keypoint.explanation or "").strip()
        if rep_explanation:
            return rep_explanation
        for member in self.sorted_members():
            explanation = (member.keypoint.explanation or "").strip()
            if explanation:
                return explanation
        return None

    @property
    def source_doc_ids(self) -> list[str]:
        doc_ids = sorted({member.doc_id for member in self.members})
        return [doc_id for doc_id in doc_ids if doc_id]

    @property
    def source_doc_names(self) -> list[str]:
        names: list[str] = []
        for doc_id in self.source_doc_ids:
            match = next((m for m in self.members if m.doc_id == doc_id), None)
            names.append((match.doc_name or doc_id) if match else doc_id)
        return names

    def sorted_members(self) -> list[KeypointClusterMember]:
        return sorted(self.members, key=_member_sort_key)


def _pick_representative(members: list[KeypointClusterMember]) -> KeypointClusterMember:
    return sorted(members, key=_member_sort_key)[0]


def _build_members(
    keypoints: list[Keypoint],
    doc_name_map: dict[str, str],
) -> list[KeypointClusterMember]:
    members: list[KeypointClusterMember] = []
    for kp in keypoints:
        members.append(
            KeypointClusterMember(
                keypoint=kp,
                doc_name=doc_name_map.get(kp.doc_id),
                normalized_text=normalize_keypoint_text(kp.text or ""),
                comparison_key=_comparison_key(kp.text or ""),
            )
        )
    return members


def _build_exact_clusters(members: list[KeypointClusterMember]) -> list[KeypointCluster]:
    grouped: dict[str, list[KeypointClusterMember]] = defaultdict(list)
    singles: list[KeypointClusterMember] = []
    for member in members:
        if member.comparison_key:
            grouped[member.comparison_key].append(member)
        else:
            singles.append(member)

    clusters: list[KeypointCluster] = []
    for group_members in grouped.values():
        sorted_members = sorted(group_members, key=_member_sort_key)
        rep = _pick_representative(sorted_members)
        clusters.append(KeypointCluster(representative=rep, members=sorted_members))

    for member in singles:
        clusters.append(KeypointCluster(representative=member, members=[member]))

    clusters.sort(key=lambda c: _member_sort_key(c.representative))
    return clusters


def _passes_semantic_text_gate(a: KeypointCluster, b: KeypointCluster) -> bool:
    a_key = a.representative.comparison_key
    b_key = b.representative.comparison_key
    if not a_key or not b_key:
        return False
    if len(a_key) < _SEMANTIC_MIN_COMPARE_LEN or len(b_key) < _SEMANTIC_MIN_COMPARE_LEN:
        return False
    if a_key in b_key or b_key in a_key:
        return True
    return _bigram_jaccard(a_key, b_key) >= _SEMANTIC_BIGRAM_JACCARD_MIN


def _merge_semantic_clusters(
    user_id: str,
    kb_id: str,
    clusters: list[KeypointCluster],
) -> list[KeypointCluster]:
    if len(clusters) <= 1:
        return clusters
    all_doc_ids = {
        member.doc_id
        for cluster in clusters
        for member in cluster.members
        if member.doc_id
    }
    if len(all_doc_ids) <= 1:
        return clusters

    member_to_cluster_idx: dict[str, int] = {}
    for idx, cluster in enumerate(clusters):
        for member in cluster.members:
            member_to_cluster_idx[member.id] = idx

    try:
        vectorstore = get_vectorstore(user_id)
    except Exception:
        logger.debug("Keypoint semantic dedup disabled: vectorstore unavailable", exc_info=True)
        return clusters

    dsu = _DisjointSet(len(clusters))
    try:
        for idx, cluster in enumerate(clusters):
            rep = cluster.representative
            if len(rep.comparison_key) < _SEMANTIC_MIN_COMPARE_LEN:
                continue

            results = vectorstore.similarity_search_with_score(
                rep.keypoint.text or "",
                k=_SEMANTIC_TOP_K,
                filter=build_chroma_eq_filter(kb_id=kb_id, type="keypoint"),
            )
            for doc_result, score in results:
                if score is None or float(score) > _SEMANTIC_DISTANCE_MAX:
                    continue
                meta = getattr(doc_result, "metadata", {}) or {}
                keypoint_id = meta.get("keypoint_id")
                if not keypoint_id:
                    continue
                other_idx = member_to_cluster_idx.get(str(keypoint_id))
                if other_idx is None or other_idx == idx:
                    continue

                other_cluster = clusters[other_idx]
                candidate_doc_id = str(meta.get("doc_id") or other_cluster.representative_doc_id or "")
                if candidate_doc_id == rep.doc_id:
                    continue
                if not _passes_semantic_text_gate(cluster, other_cluster):
                    continue
                dsu.union(idx, other_idx)
    except Exception:
        logger.debug("Keypoint semantic dedup failed; fallback to exact clusters", exc_info=True)
        return clusters

    merged_members: dict[int, list[KeypointClusterMember]] = defaultdict(list)
    for idx, cluster in enumerate(clusters):
        merged_members[dsu.find(idx)].extend(cluster.members)

    merged_clusters: list[KeypointCluster] = []
    for members in merged_members.values():
        sorted_members = sorted(members, key=_member_sort_key)
        rep = _pick_representative(sorted_members)
        merged_clusters.append(KeypointCluster(representative=rep, members=sorted_members))

    merged_clusters.sort(key=lambda c: _member_sort_key(c.representative))
    return merged_clusters


def cluster_kb_keypoints(
    db: Session,
    user_id: str,
    kb_id: str,
    doc_name_map: Optional[dict[str, str]] = None,
) -> list[KeypointCluster]:
    """Cluster KB keypoints across documents by exact + semantic similarity."""
    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == user_id, Keypoint.kb_id == kb_id)
        .order_by(Keypoint.doc_id.asc(), Keypoint.created_at.asc(), Keypoint.id.asc())
        .all()
    )
    if not keypoints:
        return []

    if doc_name_map is None:
        doc_ids = sorted({str(kp.doc_id) for kp in keypoints if kp.doc_id})
        if doc_ids:
            doc_name_map = {
                row.id: row.filename
                for row in db.query(Document.id, Document.filename)
                .filter(Document.id.in_(doc_ids))
                .all()
            }
        else:
            doc_name_map = {}

    members = _build_members(keypoints, doc_name_map)
    exact_clusters = _build_exact_clusters(members)
    return _merge_semantic_clusters(user_id, kb_id, exact_clusters)


def build_keypoint_cluster_index(clusters: list[KeypointCluster]) -> dict[str, str]:
    """Map each member keypoint id to its cluster representative id."""
    index: dict[str, str] = {}
    for cluster in clusters:
        rep_id = cluster.representative_id
        for member in cluster.members:
            index[str(member.id)] = rep_id
    return index


def collapse_kb_keypoint_ids_to_representatives(
    db: Session,
    user_id: str,
    kb_id: str,
    keypoint_ids: list[str],
) -> list[str]:
    """Collapse raw KB keypoint ids to representative ids, preserving input order."""
    if not keypoint_ids:
        return []
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    if not clusters:
        return []
    member_to_rep = build_keypoint_cluster_index(clusters)
    out: list[str] = []
    seen: set[str] = set()
    for keypoint_id in keypoint_ids:
        rep_id = member_to_rep.get(str(keypoint_id), str(keypoint_id))
        if not rep_id or rep_id in seen:
            continue
        seen.add(rep_id)
        out.append(rep_id)
    return out


def find_kb_representative_by_text(
    db: Session,
    user_id: str,
    kb_id: str,
    text: str,
) -> Optional[Keypoint]:
    """Find the representative keypoint for a KB by exact/normalized member text match."""
    query_text = str(text or "").strip()
    if not query_text:
        return None
    normalized_query = normalize_keypoint_text(query_text)
    compare_query = _comparison_key(query_text)
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    if not clusters:
        return None

    # Prefer exact representative text, then exact member text.
    for cluster in clusters:
        rep_text = str(cluster.representative_keypoint.text or "").strip()
        if rep_text == query_text:
            return cluster.representative_keypoint
    for cluster in clusters:
        for member in cluster.members:
            if str(member.keypoint.text or "").strip() == query_text:
                return cluster.representative_keypoint

    # Fallback to normalized/contains matching across all members.
    if not normalized_query and not compare_query:
        return None
    for cluster in clusters:
        for member in cluster.members:
            normalized_member = member.normalized_text
            compare_member = member.comparison_key
            if normalized_member and normalized_member == normalized_query:
                return cluster.representative_keypoint
            if compare_query and compare_member:
                if compare_member == compare_query:
                    return cluster.representative_keypoint
                if compare_query in compare_member or compare_member in compare_query:
                    return cluster.representative_keypoint
    return None


def collapse_edges_to_cluster_representatives(
    edges: list[tuple[str, str]],
    member_to_rep: dict[str, str],
) -> list[tuple[str, str]]:
    """Collapse member-level edges to representative ids and remove duplicates/self-loops."""
    collapsed: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for from_id, to_id in edges:
        from_rep = member_to_rep.get(str(from_id), str(from_id))
        to_rep = member_to_rep.get(str(to_id), str(to_id))
        if not from_rep or not to_rep or from_rep == to_rep:
            continue
        pair = (from_rep, to_rep)
        if pair in seen:
            continue
        seen.add(pair)
        collapsed.append(pair)
    return collapsed
