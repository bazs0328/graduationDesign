from __future__ import annotations

import logging
from typing import List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.config import settings
from app.services.qa_legacy import (
    build_sources_and_context_legacy,
    retrieve_documents_legacy,
)
from app.services.rag.base import RAGSearchRequest
from app.services.rag.factory import get_rag_provider

logger = logging.getLogger(__name__)

_QA_HUMAN_TEMPLATE = (
    "Conversation history:\n{history}\n\nQuestion: {question}\n\nContext:\n{context}\n\nAnswer:"
)

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

    if focus_keypoint and focus_keypoint.strip():
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
        "使用 [1]、[2] 这种形式标注引用来源。"
    )
    return "\n".join(prompt_parts)


def build_qa_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", _QA_HUMAN_TEMPLATE),
        ]
    )


def _retrieve_context_and_sources(
    *,
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> tuple[list[dict], str]:
    if kb_id:
        try:
            provider = get_rag_provider(user_id, kb_id)
            rag_result = provider.search(
                RAGSearchRequest(
                    user_id=user_id,
                    question=question,
                    doc_id=doc_id,
                    kb_id=kb_id,
                    top_k=top_k,
                    fetch_k=fetch_k,
                    mode=settings.rag_query_mode,
                )
            )
            if (rag_result.context or "").strip():
                return rag_result.sources or [], rag_result.context
        except Exception:  # noqa: BLE001
            logger.exception("RAG search failed; fallback to legacy retrieval")

    docs = retrieve_documents_legacy(
        user_id=user_id,
        question=question,
        doc_id=doc_id,
        kb_id=kb_id,
        top_k=top_k,
        fetch_k=fetch_k,
    )
    if not docs:
        return [], ""
    return build_sources_and_context_legacy(docs)


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
) -> Tuple[str, List[dict]]:
    sources, context = _retrieve_context_and_sources(
        user_id=user_id,
        question=question,
        doc_id=doc_id,
        kb_id=kb_id,
        top_k=top_k,
        fetch_k=fetch_k,
    )
    if not context:
        return "无法找到与该问题相关的内容。", []

    system_prompt = build_adaptive_system_prompt(
        ability_level=ability_level,
        weak_concepts=weak_concepts,
        focus_keypoint=focus_keypoint,
    )
    qa_prompt = build_qa_prompt(system_prompt)
    llm = get_llm(temperature=0.2)
    msg = qa_prompt.format_messages(
        question=question, context=context, history=history or "None"
    )
    result = llm.invoke(msg)
    return result.content.strip(), sources


def retrieve_documents(
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list:
    return retrieve_documents_legacy(
        user_id=user_id,
        question=question,
        doc_id=doc_id,
        kb_id=kb_id,
        top_k=top_k,
        fetch_k=fetch_k,
    )


def build_sources_and_context(docs: list) -> Tuple[List[dict], str]:
    return build_sources_and_context_legacy(docs)
