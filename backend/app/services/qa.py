import json
import logging
import re
from typing import Any, Iterator, List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.config import settings
from app.core.image_vectorstore import query_image_documents
from app.services.lexical import bm25_search
from app.core.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)

NO_RESULTS_ANSWER = "无法找到与该问题相关的内容。"

QA_MODE_NORMAL = "normal"
QA_MODE_EXPLAIN = "explain"
QA_EXPLAIN_SECTION_TITLES = [
    "题意理解",
    "相关知识点",
    "分步解答",
    "易错点",
    "自测问题",
]

_QA_HUMAN_TEMPLATE = (
    "Conversation history:\n{history}\n\nQuestion: {question}\n\nContext:\n{context}\n\nAnswer:"
)

_QA_INLINE_SOURCE_MARKER_RE = re.compile(r"\[(\d{1,3})\]")
_QA_PAGE_CHUNK_MARKER_RE = re.compile(r"\bp\.\d+\s*c\.\d+\b", re.IGNORECASE)

ADAPTIVE_SYSTEM_PROMPTS = {
    "beginner": (
        "你是一位耐心的辅导老师，正在帮助一位初学者。\n"
        "- 使用简单易懂的日常语言，避免专业术语。\n"
        "- 遇到必须使用的术语时，用括号给出通俗解释。\n"
        "- 多用类比和生活中的例子帮助理解。\n"
        "- 回答结构清晰，尽量分步骤讲解。\n"
        "- 在回答末尾给出一个简短的理解检查问题。"
    ),
    "intermediate": (
        "你是一位专业的学习导师，正在帮助一位有一定基础的学习者。\n"
        "- 可以适当使用专业术语，但对关键术语给出简要解释。\n"
        "- 回答兼顾深度与易读性。\n"
        "- 适当提及相关概念之间的联系。\n"
        "- 鼓励学习者进一步思考和拓展。"
    ),
    "advanced": (
        "你是一位学术顾问，正在与一位高水平学习者交流。\n"
        "- 可以自由使用专业术语和学术表达。\n"
        "- 提供深入分析，讨论底层原理和边界情况。\n"
        "- 给出可继续研究的方向或扩展阅读线索。\n"
        "- 鼓励批判性思考，并提出开放式问题。"
    ),
}


def normalize_qa_mode(mode: str | None) -> str:
    normalized = (mode or QA_MODE_NORMAL).strip().lower()
    if normalized == QA_MODE_EXPLAIN:
        return QA_MODE_EXPLAIN
    return QA_MODE_NORMAL


def build_adaptive_system_prompt(
    ability_level: str = "intermediate",
    weak_concepts: list[str] | None = None,
    focus_keypoint: str | None = None,
) -> str:
    normalized_level = (ability_level or "intermediate").strip().lower()
    if normalized_level not in ADAPTIVE_SYSTEM_PROMPTS:
        normalized_level = "intermediate"
    base_prompt = ADAPTIVE_SYSTEM_PROMPTS[normalized_level]

    prompt_parts = [base_prompt]
    
    # 如果指定了学习路径中的目标知识点，优先强调它
    if focus_keypoint and focus_keypoint.strip():
        # 转义大括号以避免 f-string 解析错误
        escaped_focus = focus_keypoint.strip().replace("{", "{{").replace("}", "}}")
        prompt_parts.append(
            f"重要提示：学习者当前正在学习以下知识点：「{escaped_focus}」。"
            f"请确保你的回答重点围绕这个知识点展开，帮助学习者深入理解这个概念。"
            f"如果问题与这个知识点相关，请给出更详细和针对性的解释。"
        )
    
    if weak_concepts:
        concepts = [concept.strip() for concept in weak_concepts if concept and concept.strip()]
        if concepts:
            prompt_parts.append(
                "学习者当前薄弱知识点："
                + "、".join(concepts[:5])
                + "。如果问题涉及这些知识点，请给出更细致的解释。"
            )
    prompt_parts.append(
        "仅根据提供的上下文回答问题。如果上下文中没有相关信息，请明确说明不知道。"
        "不要输出来源编号（如 [1]、[2]、[3]）或页块定位标记（如 p.19 c.177）。"
        "来源信息会由系统单独展示。"
    )
    return "\n".join(prompt_parts)


def build_explain_system_prompt(
    ability_level: str = "intermediate",
    weak_concepts: list[str] | None = None,
    focus_keypoint: str | None = None,
) -> str:
    base_prompt = build_adaptive_system_prompt(
        ability_level=ability_level,
        weak_concepts=weak_concepts,
        focus_keypoint=focus_keypoint,
    )
    titles = " / ".join(QA_EXPLAIN_SECTION_TITLES)
    explain_rules = (
        "你当前处于“讲解模式（Solve-Lite）”。请严格按照以下 5 个二级标题输出，"
        f"并保持顺序不变：{titles}。\n"
        "格式要求：每段使用 `## 标题` 开头；若上下文不足，也必须保留标题并说明缺失信息。"
        "不要输出 [1]、[2] 这类引用编号，也不要输出 p.19 c.177 这类页块定位标记。"
    )
    return f"{base_prompt}\n{explain_rules}"


def build_qa_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", _QA_HUMAN_TEMPLATE),
        ]
    )


def answer_question(
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    history: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
    ability_level: str = "intermediate",
    weak_concepts: list[str] | None = None,
    focus_keypoint: str | None = None,
    mode: str | None = None,
) -> Tuple[str, List[dict]]:
    prepared = prepare_qa_answer(
        user_id=user_id,
        question=question,
        doc_id=doc_id,
        kb_id=kb_id,
        history=history,
        top_k=top_k,
        fetch_k=fetch_k,
        ability_level=ability_level,
        weak_concepts=weak_concepts,
        focus_keypoint=focus_keypoint,
        mode=mode,
    )
    if prepared["no_results"]:
        return NO_RESULTS_ANSWER, []
    llm = get_llm(temperature=0.2)
    answer = generate_qa_answer(llm, prepared["formatted_messages"])
    return answer, prepared["sources"]


def prepare_qa_answer(
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    history: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
    ability_level: str = "intermediate",
    weak_concepts: list[str] | None = None,
    focus_keypoint: str | None = None,
    mode: str | None = None,
) -> dict:
    resolved_mode = normalize_qa_mode(mode)
    docs = retrieve_documents(
        user_id=user_id,
        question=question,
        doc_id=doc_id,
        kb_id=kb_id,
        top_k=top_k,
        fetch_k=fetch_k,
    )
    if not docs:
        return {
            "sources": [],
            "formatted_messages": None,
            "retrieved_count": 0,
            "no_results": True,
            "mode": resolved_mode,
        }

    sources, context = build_sources_and_context(docs)
    if resolved_mode == QA_MODE_EXPLAIN:
        system_prompt = build_explain_system_prompt(
            ability_level=ability_level,
            weak_concepts=weak_concepts,
            focus_keypoint=focus_keypoint,
        )
    else:
        system_prompt = build_adaptive_system_prompt(
            ability_level=ability_level,
            weak_concepts=weak_concepts,
            focus_keypoint=focus_keypoint,
        )
    qa_prompt = build_qa_prompt(system_prompt)
    msg = qa_prompt.format_messages(
        question=question, context=context, history=history or "None"
    )
    return {
        "sources": sources,
        "formatted_messages": msg,
        "retrieved_count": len(sources),
        "no_results": False,
        "mode": resolved_mode,
    }


def _coerce_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks)
    return str(content)


def generate_qa_answer(llm: Any, formatted_messages: Any) -> str:
    result = llm.invoke(formatted_messages)
    return _strip_inline_source_markers(_coerce_text_content(getattr(result, "content", result))).strip()


def _strip_inline_source_markers(text: str) -> str:
    normalized = (text or "")
    # Remove inline citation markers like [1][2][3]
    normalized = _QA_INLINE_SOURCE_MARKER_RE.sub("", normalized)
    # Remove page/chunk labels occasionally copied from source headers
    normalized = _QA_PAGE_CHUNK_MARKER_RE.sub("", normalized)
    # Cleanup extra spaces created by removals.
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"\s+([，。！？；,.;!?])", r"\1", normalized)
    return normalized


def _pseudo_stream_chunks(text: str) -> Iterator[str]:
    normalized = (text or "").strip()
    if not normalized:
        return
    parts = re.split(r"(?<=[。！？!?；;\n])", normalized)
    for part in parts:
        chunk = part.strip()
        if chunk:
            yield chunk


def _sanitize_stream_deltas(deltas: Iterator[str]) -> Iterator[str]:
    carry = ""
    tail_keep = 24  # enough to cover split markers like `[123]` / `p.19 c.177`
    for delta in deltas:
        if not delta:
            continue
        merged = carry + delta
        if len(merged) <= tail_keep:
            carry = merged
            continue
        emit = merged[:-tail_keep]
        carry = merged[-tail_keep:]
        cleaned = _strip_inline_source_markers(emit)
        if cleaned:
            yield cleaned
    if carry:
        cleaned_tail = _strip_inline_source_markers(carry)
        if cleaned_tail:
            yield cleaned_tail


def stream_qa_answer(llm: Any, formatted_messages: Any) -> Iterator[str]:
    try:
        raw_deltas = (
            _coerce_text_content(getattr(chunk, "content", chunk))
            for chunk in llm.stream(formatted_messages)
        )
        for cleaned in _sanitize_stream_deltas(raw_deltas):
            yield cleaned
        return
    except Exception as exc:
        logger.debug("LLM native stream unavailable, fallback to pseudo-stream: %s", exc, exc_info=True)

    full_answer = generate_qa_answer(llm, formatted_messages)
    yielded = False
    for piece in _pseudo_stream_chunks(full_answer):
        yielded = True
        yield piece
    if not yielded and full_answer:
        yield full_answer


def retrieve_documents(
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list:
    vectorstore = get_vectorstore(user_id)
    search_filter = None
    if doc_id:
        search_filter = {"doc_id": doc_id}
    elif kb_id:
        search_filter = {"kb_id": kb_id}

    k = top_k or settings.qa_top_k
    fetch = fetch_k or settings.qa_fetch_k
    if fetch < k:
        fetch = k

    docs = []
    if settings.rag_mode == "dense":
        try:
            docs = vectorstore.max_marginal_relevance_search(
                question, k=k, fetch_k=fetch, filter=search_filter
            )
        except Exception:
            docs = vectorstore.similarity_search(question, k=k, filter=search_filter)
        image_docs = [doc for doc, _ in query_image_documents(
            user_id,
            question,
            top_k=k,
            search_filter=search_filter,
        )]
        if image_docs:
            docs.extend(image_docs)
            # Preserve top-k-ish behavior while keeping image hits visible.
            docs = docs[: max(k, min(len(docs), k + len(image_docs)))]
        return docs

    dense_results: list[tuple[Any, float]] = []
    try:
        raw_dense_results = vectorstore.similarity_search_with_relevance_scores(
            question, k=fetch, filter=search_filter
        )
        for doc, score in raw_dense_results:
            dense_results.append((doc, float(score)))
    except Exception:
        try:
            raw_dense_results = vectorstore.similarity_search_with_score(
                question, k=fetch, filter=search_filter
            )
            for doc, score in raw_dense_results:
                dense_results.append((doc, 1.0 / (1.0 + max(float(score), 0.0))))
        except Exception:
            dense_results = []

    for doc, score in query_image_documents(
        user_id,
        question,
        top_k=fetch,
        search_filter=search_filter,
    ):
        dense_results.append((doc, float(score)))

    bm25_k = settings.qa_bm25_k
    if bm25_k < k:
        bm25_k = k
    lexical_results = []
    if kb_id:
        lexical_results = bm25_search(
            user_id,
            kb_id,
            question,
            top_k=bm25_k,
            doc_id=doc_id,
        )

    combined = {}
    for doc, score in dense_results:
        meta = doc.metadata or {}
        key = (
            meta.get("doc_id"),
            meta.get("page"),
            meta.get("chunk"),
            meta.get("modality"),
            doc.page_content[:80],
        )
        dense_score = float(score)
        if key not in combined:
            combined[key] = {
                "doc": doc,
                "dense": dense_score,
                "bm25": 0.0,
            }
        else:
            combined[key]["dense"] = max(combined[key]["dense"], dense_score)

    for doc, score in lexical_results:
        meta = doc.metadata or {}
        key = (
            meta.get("doc_id"),
            meta.get("page"),
            meta.get("chunk"),
            meta.get("modality"),
            doc.page_content[:80],
        )
        if key not in combined:
            combined[key] = {"doc": doc, "dense": 0.0, "bm25": float(score)}
        else:
            combined[key]["bm25"] = max(combined[key]["bm25"], float(score))

    if not combined:
        return []

    dense_scores = [item["dense"] for item in combined.values()]
    bm25_scores = [item["bm25"] for item in combined.values()]
    dense_min = min(dense_scores)
    dense_max = max(dense_scores)
    bm25_min = min(bm25_scores)
    bm25_max = max(bm25_scores)

    def _norm(val: float, min_val: float, max_val: float) -> float:
        if max_val - min_val < 1e-9:
            return 0.0
        return (val - min_val) / (max_val - min_val)

    dense_weight = max(0.0, settings.rag_dense_weight)
    bm25_weight = max(0.0, settings.rag_bm25_weight)
    if dense_weight + bm25_weight < 1e-9:
        dense_weight = 1.0

    weighted = []
    for item in combined.values():
        dense_norm = _norm(item["dense"], dense_min, dense_max)
        bm25_norm = _norm(item["bm25"], bm25_min, bm25_max)
        score = dense_norm * dense_weight + bm25_norm * bm25_weight
        weighted.append((item["doc"], score))

    weighted.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in weighted[:k]]


def build_sources_and_context(docs: list) -> Tuple[List[dict], str]:
    sources = []
    context_blocks = []
    for idx, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        snippet = doc.page_content[:400].replace("\n", " ")
        source_name = (
            metadata.get("source")
            or metadata.get("filename")
            or metadata.get("title")
            or "文档片段"
        )
        page = metadata.get("page")
        chunk = metadata.get("chunk")
        doc_id_meta = metadata.get("doc_id")
        kb_id_meta = metadata.get("kb_id")
        modality = (metadata.get("modality") or "text")
        asset_path = metadata.get("asset_path") or None
        caption = metadata.get("caption") or None
        bbox = None
        raw_bbox = metadata.get("bbox")
        if isinstance(raw_bbox, str) and raw_bbox.strip():
            try:
                parsed = json.loads(raw_bbox)
                if isinstance(parsed, list):
                    bbox = parsed
            except Exception:
                bbox = None
        elif isinstance(raw_bbox, list):
            bbox = raw_bbox

        source_label = str(source_name)
        if modality == "image":
            source_label = f"{source_label} (图片块)"
        context_label = source_name
        if modality == "image":
            context_label = f"{source_name} (图片相关)"

        sources.append(
            {
                "source": source_label,
                "snippet": snippet,
                "doc_id": doc_id_meta,
                "kb_id": kb_id_meta,
                "page": page,
                "chunk": chunk,
                "modality": modality,
                "asset_path": asset_path,
                "caption": caption,
                "bbox": bbox,
            }
        )
        if modality == "image":
            image_lines = [f"[{idx}] Source: {context_label}"]
            if caption:
                image_lines.append(f"图注: {caption}")
            image_lines.append(doc.page_content)
            context_blocks.append("\n".join(image_lines))
        else:
            context_blocks.append(f"[{idx}] Source: {context_label}\n{doc.page_content}")

    context = "\n\n".join(context_blocks)
    return sources, context
