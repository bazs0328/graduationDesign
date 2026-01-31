import json

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.utils.json_tools import safe_json_loads


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


def generate_quiz(user_id: str, doc_id: str, count: int, difficulty: str):
    vectorstore = get_vectorstore(user_id)
    docs = vectorstore.similarity_search(
        "key concepts and definitions", k=6, filter={"doc_id": doc_id}
    )

    if not docs:
        raise ValueError("No relevant context found for quiz generation")

    context = "\n\n".join(doc.page_content for doc in docs)

    llm = get_llm(temperature=0.4)
    msg = QUIZ_PROMPT.format_messages(count=count, difficulty=difficulty, context=context)
    result = llm.invoke(msg)

    data = safe_json_loads(result.content)
    if isinstance(data, dict):
        data = data.get("questions", [])
    json.dumps(data)  # validate serializable
    return data
