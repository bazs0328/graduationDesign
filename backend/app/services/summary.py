from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm


SUMMARY_SYSTEM = (
    "You are a learning assistant. Summarize the material clearly and concisely. "
    "Use bullet points and highlight key definitions, formulas, and steps."
)

CHUNK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM),
        ("human", "Summarize this chunk:\n\n{chunk}"),
    ]
)

FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM),
        (
            "human",
            "Combine these chunk summaries into a final summary (8-12 bullets):\n\n{chunks}",
        ),
    ]
)


def summarize_text(text: str) -> str:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    chunks = splitter.split_text(text)

    chunk_summaries = []
    for chunk in chunks:
        msg = CHUNK_PROMPT.format_messages(chunk=chunk)
        result = llm.invoke(msg)
        chunk_summaries.append(result.content)

    final_msg = FINAL_PROMPT.format_messages(chunks="\n\n".join(chunk_summaries))
    final_result = llm.invoke(final_msg)
    return final_result.content.strip()
