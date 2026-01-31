import os

from langchain_community.vectorstores import Chroma

from app.core.llm import get_embeddings
from app.core.paths import ensure_user_dirs, user_base_dir


def get_vectorstore(user_id: str):
    ensure_user_dirs(user_id)
    persist_dir = os.path.join(user_base_dir(user_id), "chroma")
    embeddings = get_embeddings()
    return Chroma(
        collection_name="documents",
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )
