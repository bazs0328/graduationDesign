import asyncio

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.services.sampling import sample_evenly

SUMMARY_SYSTEM = (
    "你是一位文档摘要专家。你的任务是以清晰、结构化、简洁的方式从教育材料中提取和组织核心内容。\n\n"
    "核心原则：\n"
    "1. **具体化优先**：基于实际内容进行摘要 - 引用材料中提到的具体定义、公式、"
    "定理、方法和关键概念\n"
    "2. **聚焦要点**：仅提取最重要的信息 - 避免次要细节、示例或无关内容\n"
    "3. **结构化组织**：逻辑地组织内容 - 将相关概念分组，展示关系，保持逻辑流程\n"
    "4. **清晰精确**：使用清晰、精确的语言 - 避免模糊陈述，确保每个点传达具体信息\n\n"
    "应包含的内容：\n"
    "- 核心定义和概念（使用精确的陈述）\n"
    "- 关键公式、定理或原理（尽可能使用精确表达式）\n"
    "- 重要方法、程序或算法（关键时提供逐步说明）\n"
    "- 概念之间的基本关系\n"
    "- 关键应用或含义\n\n"
    "应避免的内容：\n"
    "- 重复的解释\n"
    "- 过多的示例或说明\n"
    "- 次要细节或边缘情况\n"
    "- 模糊或通用的陈述\n"
    "- 过于冗长的描述\n\n"
    "重要：所有输出必须使用中文（简体中文）。"
)

CHUNK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM),
        (
            "human",
            "分析此文档片段并提取核心内容。重点关注：\n"
            "- 关键定义、概念或原理\n"
            "- 重要公式、定理或方法\n"
            "- 关键关系或模式\n"
            "- 基本步骤或程序\n\n"
            "输出一个简洁的摘要（3-5 个要点），捕捉最重要的信息。"
            "要具体和明确 - 引用材料中的实际内容。"
            "所有内容必须使用中文（简体中文）。\n\n"
            "文档片段：\n{chunk}"
        ),
    ]
)

FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM),
        (
            "human",
            "审查并综合这些片段摘要，生成一份全面而简洁的文档摘要。\n\n"
            "你的任务：\n"
            "1. **合并和去重**：合并相似点，删除冗余\n"
            "2. **逻辑组织**：将相关概念分组，保持逻辑流程\n"
            "3. **优先核心内容**：仅保留最重要的信息\n"
            "4. **确保具体性**：每个点应传达具体、明确的信息\n"
            "5. **保持结构**：使用清晰的标题和要点以提高可读性\n\n"
            "输出要求：\n"
            "- 使用 Markdown 格式，结构清晰（标题、要点）\n"
            "- 目标长度：8-15 个要点，组织成逻辑章节\n"
            "- 每个点应具体且信息丰富（避免模糊陈述）\n"
            "- 包含实际的定义、公式或方法（如果存在）\n"
            "- 确保摘要全面捕捉文档的核心内容\n"
            "- 所有内容必须使用中文（简体中文）\n\n"
            "片段摘要：\n{chunks}"
        ),
    ]
)

# Larger chunks = fewer LLM calls; cap prevents runaway on huge docs
_SUMMARY_CHUNK_SIZE = 6000
_SUMMARY_CHUNK_OVERLAP = 300
_MAX_CHUNKS = 20


async def summarize_text(text: str) -> str:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_SUMMARY_CHUNK_SIZE, chunk_overlap=_SUMMARY_CHUNK_OVERLAP
    )
    chunks = splitter.split_text(text)
    chunks = sample_evenly(chunks, _MAX_CHUNKS)

    async def _summarize_chunk(chunk: str) -> str:
        msg = CHUNK_PROMPT.format_messages(chunk=chunk)
        result = await llm.ainvoke(msg)
        return result.content

    chunk_summaries = await asyncio.gather(*[_summarize_chunk(c) for c in chunks])

    final_msg = FINAL_PROMPT.format_messages(chunks="\n\n".join(chunk_summaries))
    final_result = await llm.ainvoke(final_msg)
    return final_result.content.strip()
