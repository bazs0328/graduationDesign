import json
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.utils.json_tools import safe_json_loads

# Max length for reference_questions to avoid exceeding model context
REFERENCE_QUESTIONS_MAX_CHARS = 8000

QUIZ_SYSTEM = (
    "You are an exam writer. Generate multiple-choice questions strictly from the context. "
    "Return JSON only."
)

QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", QUIZ_SYSTEM),
        (
            "human",
            "Create {count} {difficulty} multiple-choice questions. "
            "Each question must have 4 options and one correct answer. "
            "Return JSON array with fields: question, options, answer_index, explanation.\n\n"
            "Context:\n{context}",
        ),
    ]
)

QUIZ_MIMIC_SYSTEM = (
    "You are an exam writer. Generate multiple-choice questions. "
    "When reference questions or style requirements are given, match their style and difficulty. "
    "Return JSON only."
)

QUIZ_MIMIC_HUMAN_TEMPLATE = (
    "Create {count} {difficulty} multiple-choice questions. "
    "Each question must have 4 options and one correct answer. "
    "Return JSON array with fields: question, options, answer_index, explanation.\n\n"
    "{extra_instructions}"
    "Context:\n{context}"
)


def _build_context(
    user_id: str,
    doc_id: Optional[str],
    kb_id: Optional[str],
    reference_questions: Optional[str],
) -> str:
    """Build context from doc_id or kb_id (vectorstore), reference_questions, or placeholder."""
    if doc_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            "key concepts and definitions", k=6, filter={"doc_id": doc_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs)
    if kb_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            "key concepts and definitions", k=6, filter={"kb_id": kb_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs)
    if reference_questions:
        text = reference_questions.strip()
        if len(text) > REFERENCE_QUESTIONS_MAX_CHARS:
            text = text[:REFERENCE_QUESTIONS_MAX_CHARS] + "\n[... truncated]"
        return text
    return "General knowledge."


def _build_extra_instructions(
    style_prompt: Optional[str],
    reference_questions: Optional[str],
    context_is_from_reference: bool,
) -> str:
    """Build extra prompt section for mimic (style / reference questions)."""
    parts = []
    if reference_questions and not context_is_from_reference:
        text = reference_questions.strip()
        if len(text) > REFERENCE_QUESTIONS_MAX_CHARS:
            text = text[:REFERENCE_QUESTIONS_MAX_CHARS] + "\n[... truncated]"
        parts.append(
            "Reference the following questions for style and difficulty, then generate new questions in the same style:\n"
            f"{text}\n\n"
        )
    if style_prompt and style_prompt.strip():
        parts.append(f"Style/template requirements:\n{style_prompt.strip()}\n\n")
    return "".join(parts) if parts else ""


def generate_quiz(
    user_id: str,
    doc_id: Optional[str],
    count: int,
    difficulty: str,
    kb_id: Optional[str] = None,
    style_prompt: Optional[str] = None,
    reference_questions: Optional[str] = None,
) -> List[dict]:
    context = _build_context(user_id, doc_id, kb_id, reference_questions)
    context_is_from_reference = not doc_id and not kb_id and bool(
        reference_questions and reference_questions.strip()
    )
    extra = _build_extra_instructions(
        style_prompt, reference_questions, context_is_from_reference
    )

    llm = get_llm(temperature=0.4)
    if extra:
        human_msg = QUIZ_MIMIC_HUMAN_TEMPLATE.format(
            count=count,
            difficulty=difficulty,
            extra_instructions=extra,
            context=context,
        )
        msg_list = [
            SystemMessage(content=QUIZ_MIMIC_SYSTEM),
            HumanMessage(content=human_msg),
        ]
        result = llm.invoke(msg_list)
    else:
        messages = QUIZ_PROMPT.format_messages(
            count=count, difficulty=difficulty, context=context
        )
        result = llm.invoke(messages)

    data = safe_json_loads(result.content)
    if isinstance(data, dict):
        data = data.get("questions", [])
    json.dumps(data)  # validate serializable
    return data
