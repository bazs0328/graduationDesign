from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import get_llm
from app.utils.json_tools import safe_json_loads


KEYPOINT_SYSTEM = (
    "You are a learning assistant. Extract concise key knowledge points from the material. "
    "Each point should be a short sentence focused on definitions, formulas, steps, or core ideas. "
    "Return JSON array of strings only."
)

CHUNK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "Extract up to 5 keypoints from this chunk. Return JSON array only.\n\n{chunk}",
        ),
    ]
)

FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "Merge and deduplicate these keypoints into 10-15 clear points. "
            "Return JSON array only.\n\n{points}",
        ),
    ]
)


def extract_keypoints(text: str) -> list[str]:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    chunks = splitter.split_text(text)

    all_points: list[str] = []
    for chunk in chunks:
        msg = CHUNK_PROMPT.format_messages(chunk=chunk)
        result = llm.invoke(msg)
        try:
            points = safe_json_loads(result.content)
        except Exception:
            points = []
        if isinstance(points, list):
            all_points.extend([str(p).strip() for p in points if str(p).strip()])

    final_msg = FINAL_PROMPT.format_messages(points="\n".join(all_points))
    final_result = llm.invoke(final_msg)
    try:
        final_points = safe_json_loads(final_result.content)
    except Exception:
        final_points = []
    if isinstance(final_points, list):
        return [str(p).strip() for p in final_points if str(p).strip()]
    return []
