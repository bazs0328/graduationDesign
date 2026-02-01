import json
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
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


def extract_keypoints(
    text: str,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> list[dict]:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    chunks = splitter.split_text(text)

    all_points: list[dict] = []
    for i, chunk in enumerate(chunks):
        safe_chunk = chunk.replace("{", "{{").replace("}", "}}")
        msg = CHUNK_PROMPT.format_messages(chunk=safe_chunk)
        result = llm.invoke(msg)
        try:
            points = safe_json_loads(result.content)
        except Exception:
            points = []
        if isinstance(points, list):
            for p in points:
                parsed = _parse_point(p)
                if parsed and parsed.get("text"):
                    all_points.append(parsed)

    points_str = "\n".join(
        f"- {p.get('text', '')}" + (f" ({p.get('explanation')})" if p.get("explanation") else "")
        for p in all_points
    )
    final_msg = FINAL_PROMPT.format_messages(points=points_str)
    final_result = llm.invoke(final_msg)
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
