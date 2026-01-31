import os
from typing import Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LCDocument

from app.core.paths import ensure_user_dirs, user_base_dir
from app.core.vectorstore import get_vectorstore
from app.core.config import settings
from app.services.text_extraction import extract_text
from app.services.lexical import append_lexical_chunks


SUPPORTED_TYPES = {".pdf", ".txt", ".md"}


def ingest_document(
    file_path: str, filename: str, doc_id: str, user_id: str, kb_id: str
) -> Tuple[str, int, int, int]:
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_TYPES:
        raise ValueError("Unsupported file type")

    extraction = extract_text(file_path, suffix)
    text = extraction.text.strip()
    if not text:
        raise ValueError("No text extracted from file")

    ensure_user_dirs(user_id)
    text_path = os.path.join(user_base_dir(user_id), "text", f"{doc_id}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    chunk_size = max(200, settings.chunk_size)
    chunk_overlap = max(0, min(settings.chunk_overlap, chunk_size - 1))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    docs: list[LCDocument] = []
    if suffix == ".pdf":
        for page_num, page_text in enumerate(extraction.pages, start=1):
            if not page_text:
                continue
            docs.append(
                LCDocument(
                    page_content=page_text,
                    metadata={
                        "doc_id": doc_id,
                        "kb_id": kb_id,
                        "source": filename,
                        "page": page_num,
                    },
                )
            )
    else:
        docs.append(
            LCDocument(
                page_content=text,
                metadata={"doc_id": doc_id, "kb_id": kb_id, "source": filename},
            )
        )

    if not docs:
        raise ValueError("No text extracted from file")

    docs = splitter.split_documents(docs)
    for idx, doc in enumerate(docs, start=1):
        doc.metadata.setdefault("chunk", idx)

    vectorstore = get_vectorstore(user_id)
    vectorstore.add_documents(docs)
    vectorstore.persist()
    append_lexical_chunks(user_id, kb_id, docs)

    char_count = len(text)
    return text_path, len(docs), extraction.page_count, char_count
