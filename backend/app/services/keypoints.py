import asyncio
from typing import Optional

from sqlalchemy.orm import Session

from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.models import Keypoint
from app.utils.json_tools import safe_json_loads

KEYPOINT_SYSTEM = (
    "You are a learning assistant. Extract concise key knowledge points from the material. "
    "Each point should be a short sentence focused on definitions, formulas, steps, or core ideas. "
    "Return JSON array of objects: [{{text: string, explanation?: string}}, ...]. "
    "Explanation is optional, a brief clarification or elaboration."
)

CHUNK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "Extract up to 5 keypoints from this chunk. Return JSON array of objects only.\n\n{chunk}",
        ),
    ]
)

FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "Merge and deduplicate these keypoints into 10-15 clear points. "
            "Return JSON array of objects [{{text, explanation?}}] only.\n\n{points}",
        ),
    ]
)

# Larger chunks = fewer LLM calls; cap prevents runaway on huge docs
_KP_CHUNK_SIZE = 6000
_KP_CHUNK_OVERLAP = 300
_MAX_CHUNKS = 15


def _sample_chunks(chunks: list[str], max_count: int) -> list[str]:
    """Evenly sample chunks when there are too many."""
    if len(chunks) <= max_count:
        return chunks
    step = len(chunks) / max_count
    return [chunks[int(i * step)] for i in range(max_count)]


def _parse_point(p) -> dict:
    if isinstance(p, str):
        t = p.strip()
        return {"text": t, "explanation": None, "source": None, "page": None, "chunk": None} if t else None
    if isinstance(p, dict):
        text = p.get("text") or str(p.get("text", "")).strip()
        if not text:
            return None
        return {
            "text": text,
            "explanation": p.get("explanation") or None,
            "source": None,
            "page": None,
            "chunk": None,
        }
    return None


def _attach_source(user_id: str, doc_id: str, point: dict) -> dict:
    query_text = point.get("text") or ""
    if not query_text:
        return point
    try:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query_text, k=1, filter={"doc_id": doc_id}
        )
        if docs:
            meta = docs[0].metadata or {}
            point["source"] = meta.get("source")
            point["page"] = meta.get("page")
            point["chunk"] = meta.get("chunk")
    except Exception:
        pass
    return point


def _build_keypoint_id(doc_id: str, index: int) -> str:
    """Build a stable keypoint id for a document."""
    safe_prefix = (doc_id or "doc")[:8]
    return f"KP-{safe_prefix}-{index:03d}"


def save_keypoints_to_db(
    db: Session,
    user_id: str,
    doc_id: str,
    points: list[dict],
    kb_id: Optional[str] = None,
    overwrite: bool = False,
) -> list[Keypoint]:
    """Persist keypoints to DB and vectorstore with stable ids."""
    if overwrite:
        db.query(Keypoint).filter(
            Keypoint.user_id == user_id, Keypoint.doc_id == doc_id
        ).delete()
        db.commit()
        try:
            vectorstore = get_vectorstore(user_id)
            vectorstore.delete(where={"doc_id": doc_id, "type": "keypoint"})
        except Exception:
            pass

    vectorstore = get_vectorstore(user_id)
    saved: list[Keypoint] = []
    for idx, point in enumerate(points, start=1):
        parsed = _parse_point(point) if isinstance(point, (dict, str)) else None
        if not parsed or not parsed.get("text"):
            continue
        kp_id = _build_keypoint_id(doc_id, idx)
        keypoint = Keypoint(
            id=kp_id,
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            text=parsed["text"],
            explanation=point.get("explanation") if isinstance(point, dict) else None,
            source=point.get("source") if isinstance(point, dict) else None,
            page=point.get("page") if isinstance(point, dict) else None,
            chunk=point.get("chunk") if isinstance(point, dict) else None,
        )
        db.add(keypoint)
        saved.append(keypoint)
        vectorstore.add_texts(
            [keypoint.text],
            metadatas=[
                {
                    "keypoint_id": kp_id,
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "type": "keypoint",
                }
            ],
            ids=[kp_id],
        )
    db.commit()
    return saved


def _search_keypoints_per_concept(
    vectorstore,
    concepts: list[str],
    filter_dict: dict,
    max_distance: float = 1.0,
    top_k_per_concept: int = 2,
) -> list[str]:
    """Search per concept individually and merge results (deduplicated)."""
    seen: set[str] = set()
    matched: list[str] = []
    for concept in concepts:
        text = str(concept).strip()
        if not text:
            continue
        try:
            results = vectorstore.similarity_search_with_score(
                text, k=top_k_per_concept, filter=filter_dict,
            )
        except Exception:
            continue
        for doc, score in results:
            meta = getattr(doc, "metadata", {}) or {}
            kp_id = meta.get("keypoint_id")
            if not kp_id or kp_id in seen:
                continue
            if score <= max_distance:
                seen.add(kp_id)
                matched.append(kp_id)
    return matched


def match_keypoints_by_concepts(
    user_id: str,
    doc_id: str,
    concepts: list[str],
    max_distance: float = 1.0,
    top_k: int = 2,
) -> list[str]:
    """Match concepts to keypoint ids within a document (per-concept search)."""
    if not concepts:
        return []
    vectorstore = get_vectorstore(user_id)
    return _search_keypoints_per_concept(
        vectorstore, concepts,
        filter_dict={"doc_id": doc_id, "type": "keypoint"},
        max_distance=max_distance,
        top_k_per_concept=top_k,
    )


def match_keypoints_by_kb(
    user_id: str,
    kb_id: str,
    concepts: list[str],
    max_distance: float = 1.0,
    top_k: int = 2,
) -> list[str]:
    """Match concepts to keypoint ids within a knowledge base (per-concept search)."""
    if not concepts:
        return []
    vectorstore = get_vectorstore(user_id)
    return _search_keypoints_per_concept(
        vectorstore, concepts,
        filter_dict={"kb_id": kb_id, "type": "keypoint"},
        max_distance=max_distance,
        top_k_per_concept=top_k,
    )


def update_keypoint_mastery(db: Session, keypoint_id: str, is_correct: bool) -> None:
    """Deprecated: use app.services.mastery.record_quiz_result instead."""
    from app.services.mastery import record_quiz_result

    record_quiz_result(db, keypoint_id, is_correct)
    db.commit()


async def extract_keypoints(
    text: str,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> list[dict]:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_KP_CHUNK_SIZE, chunk_overlap=_KP_CHUNK_OVERLAP
    )
    chunks = splitter.split_text(text)
    chunks = _sample_chunks(chunks, _MAX_CHUNKS)

    async def _process_chunk(chunk: str) -> list[dict]:
        safe_chunk = chunk.replace("{", "{{").replace("}", "}}")
        msg = CHUNK_PROMPT.format_messages(chunk=safe_chunk)
        result = await llm.ainvoke(msg)
        try:
            points = safe_json_loads(result.content)
        except Exception:
            points = []
        if not isinstance(points, list):
            return []
        return [p for p in (_parse_point(p) for p in points) if p and p.get("text")]

    chunk_results = await asyncio.gather(*[_process_chunk(c) for c in chunks])
    all_points: list[dict] = [p for chunk_pts in chunk_results for p in chunk_pts]

    points_str = "\n".join(
        f"- {p.get('text', '')}" + (f" ({p.get('explanation')})" if p.get("explanation") else "")
        for p in all_points
    )
    final_msg = FINAL_PROMPT.format_messages(points=points_str)
    final_result = await llm.ainvoke(final_msg)
    try:
        final_points = safe_json_loads(final_result.content)
    except Exception:
        final_points = []
    if not isinstance(final_points, list):
        return []

    out: list[dict] = []
    for p in final_points:
        parsed = _parse_point(p)
        if parsed and parsed.get("text"):
            if user_id and doc_id:
                parsed = _attach_source(user_id, doc_id, parsed)
            out.append(parsed)
    return out
