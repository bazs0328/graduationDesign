import asyncio

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

# Larger chunks = fewer LLM calls; cap prevents runaway on huge docs
_SUMMARY_CHUNK_SIZE = 6000
_SUMMARY_CHUNK_OVERLAP = 300
_MAX_CHUNKS = 20


def _sample_chunks(chunks: list[str], max_count: int) -> list[str]:
    """Evenly sample chunks when there are too many."""
    if len(chunks) <= max_count:
        return chunks
    step = len(chunks) / max_count
    return [chunks[int(i * step)] for i in range(max_count)]


async def summarize_text(text: str) -> str:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_SUMMARY_CHUNK_SIZE, chunk_overlap=_SUMMARY_CHUNK_OVERLAP
    )
    chunks = splitter.split_text(text)
    chunks = _sample_chunks(chunks, _MAX_CHUNKS)

    async def _summarize_chunk(chunk: str) -> str:
        msg = CHUNK_PROMPT.format_messages(chunk=chunk)
        result = await llm.ainvoke(msg)
        return result.content

    chunk_summaries = await asyncio.gather(*[_summarize_chunk(c) for c in chunks])

    final_msg = FINAL_PROMPT.format_messages(chunks="\n\n".join(chunk_summaries))
    final_result = await llm.ainvoke(final_msg)
    return final_result.content.strip()
