import json
import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

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
            "Return JSON array with fields: question, options, answer_index, explanation, concepts.\n"
            "concepts must be a list of 1-3 key concepts tested.\n\n"
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
    "Return JSON array with fields: question, options, answer_index, explanation, concepts.\n"
    "concepts must be a list of 1-3 key concepts tested.\n\n"
    "{extra_instructions}"
    "Context:\n{context}"
)


def _extract_keypoint_ids(docs) -> List[str]:
    """Extract unique keypoint_ids from vector search result metadata."""
    seen: set[str] = set()
    ids: List[str] = []
    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        kp_id = meta.get("keypoint_id")
        if kp_id and kp_id not in seen:
            seen.add(kp_id)
            ids.append(kp_id)
    return ids


def _build_context(
    user_id: str,
    doc_id: Optional[str],
    kb_id: Optional[str],
    reference_questions: Optional[str],
    focus_concepts: Optional[List[str]] = None,
) -> tuple[str, List[str]]:
    """Build context and collect related keypoint_ids from vector search metadata.

    Returns (context_text, keypoint_ids).
    """
    query = "key concepts and definitions"
    if focus_concepts:
        cleaned = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned:
            query = ", ".join(cleaned)
    if doc_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query, k=6, filter={"doc_id": doc_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs), _extract_keypoint_ids(docs)
    if kb_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query, k=6, filter={"kb_id": kb_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs), _extract_keypoint_ids(docs)
    if reference_questions:
        text = reference_questions.strip()
        if len(text) > REFERENCE_QUESTIONS_MAX_CHARS:
            text = text[:REFERENCE_QUESTIONS_MAX_CHARS] + "\n[... truncated]"
        return text, []
    return "General knowledge.", []


def _build_extra_instructions(
    style_prompt: Optional[str],
    reference_questions: Optional[str],
    context_is_from_reference: bool,
    focus_concepts: Optional[List[str]] = None,
) -> str:
    """Build extra prompt section for mimic (style / reference questions)."""
    parts = []
    if focus_concepts:
        cleaned = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned:
            parts.append(
                "Focus on the following concepts when generating questions:\n"
                f"{', '.join(cleaned)}\n\n"
            )
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
    focus_concepts: Optional[List[str]] = None,
    style_prompt: Optional[str] = None,
    reference_questions: Optional[str] = None,
) -> List[dict]:
    context, keypoint_ids = _build_context(
        user_id, doc_id, kb_id, reference_questions, focus_concepts
    )
    context_is_from_reference = not doc_id and not kb_id and bool(
        reference_questions and reference_questions.strip()
    )
    extra = _build_extra_instructions(
        style_prompt, reference_questions, context_is_from_reference, focus_concepts
    )

    try:
        llm = get_llm(temperature=0.4)
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        raise ValueError(f"Failed to initialize LLM: {str(e)}")

    try:
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
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        raise ValueError(f"Failed to generate quiz questions from LLM: {str(e)}")
    
    if not hasattr(result, 'content') or not result.content:
        logger.error("LLM returned empty or invalid response")
        raise ValueError("LLM returned empty or invalid response")

    try:
        data = safe_json_loads(result.content)
    except Exception as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.debug(f"LLM response content: {result.content[:500]}")
        raise ValueError(f"Failed to parse quiz questions from LLM response: {str(e)}")

    if isinstance(data, dict):
        data = data.get("questions", [])
    
    if not isinstance(data, list):
        logger.error(f"Expected list of questions, got {type(data)}: {data}")
        raise ValueError(f"Expected list of questions, got {type(data).__name__}")

    if len(data) == 0:
        logger.warning("LLM returned empty question list")
        raise ValueError("No questions generated. Please check context or try again.")

    # Validate and normalize each question
    validated_questions = []
    for idx, q in enumerate(data):
        if not isinstance(q, dict):
            logger.warning(f"Question {idx} is not a dict, skipping: {q}")
            continue
        
        # Ensure required fields exist
        required_fields = ["question", "options", "answer_index", "explanation"]
        missing_fields = [f for f in required_fields if f not in q]
        if missing_fields:
            logger.warning(f"Question {idx} missing fields {missing_fields}, skipping")
            continue
        
        # Normalize types
        if not isinstance(q.get("options"), list) or len(q["options"]) != 4:
            logger.warning(f"Question {idx} has invalid options, skipping")
            continue
        
        if not isinstance(q.get("answer_index"), int) or q["answer_index"] < 0 or q["answer_index"] >= 4:
            logger.warning(f"Question {idx} has invalid answer_index, skipping")
            continue
        
        # Ensure concepts is a list
        if "concepts" not in q or not isinstance(q.get("concepts"), list):
            q["concepts"] = []
        
        validated_questions.append(q)
    
    if len(validated_questions) == 0:
        logger.error("No valid questions after validation")
        raise ValueError("No valid questions generated. Please check LLM output format.")

    if keypoint_ids:
        for q in validated_questions:
            if "keypoint_ids" not in q:
                q["keypoint_ids"] = keypoint_ids

    try:
        json.dumps(validated_questions)  # validate serializable
    except TypeError as e:
        logger.error(f"Questions are not JSON serializable: {e}")
        raise ValueError(f"Generated questions are not JSON serializable: {str(e)}")
    
    return validated_questions
