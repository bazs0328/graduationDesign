from __future__ import annotations

from dataclasses import dataclass
import os
from time import perf_counter
from typing import Callable, Optional, Tuple, Union

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.paths import ensure_user_dirs, user_base_dir
from app.core.vectorstore import get_vectorstore
from app.services.lexical import append_lexical_chunks
from app.services.parsers.base import ParseRequest
from app.services.parsers.router import ParserRouter


SUPPORTED_TYPES = {".pdf", ".txt", ".md"}


StageCallback = Optional[Callable[[str, int, str], None]]


@dataclass(slots=True)
class IngestResult:
    text_path: str
    num_chunks: int
    num_pages: int
    char_count: int
    parser_provider: str
    extract_method: str
    quality_score: float | None
    diagnostics: dict
    timing: dict[str, float]


def _emit(cb: StageCallback, stage: str, progress: int, message: str):
    if cb:
        cb(stage, max(0, min(progress, 100)), message)


def ingest_document(
    file_path: str,
    filename: str,
    doc_id: str,
    user_id: str,
    kb_id: str,
    *,
    mode: str = "auto",
    parse_policy: str = "balanced",
    preferred_parser: str = "auto",
    stage_callback: StageCallback = None,
    return_details: bool = False,
) -> Union[Tuple[str, int, int, int], IngestResult]:
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_TYPES:
        raise ValueError("Unsupported file type")

    router = ParserRouter()

    _emit(stage_callback, "preflight", 5, "Analyzing document complexity")
    parse_started = perf_counter()
    result = router.parse(
        ParseRequest(
            file_path=file_path,
            suffix=suffix,
            mode=mode,
            parse_policy=parse_policy,
            preferred_parser=preferred_parser,
        )
    )
    parse_elapsed = (perf_counter() - parse_started) * 1000

    text = result.text.strip()
    if not text:
        raise ValueError("No text extracted from file")

    _emit(stage_callback, "extract", 30, "Extraction complete")
    if result.diagnostics.get("ocr_pages"):
        _emit(stage_callback, "ocr", 45, "OCR replacement completed")
    else:
        _emit(stage_callback, "ocr", 45, "OCR not required for this document")

    ensure_user_dirs(user_id)
    text_path = os.path.join(user_base_dir(user_id), "text", f"{doc_id}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    chunk_size = max(200, settings.chunk_size)
    chunk_overlap = max(0, min(settings.chunk_overlap, chunk_size - 1))
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    _emit(stage_callback, "chunk", 60, "Splitting document into chunks")
    docs: list[LCDocument] = []
    if suffix == ".pdf":
        for page_num, page_text in enumerate(result.pages, start=1):
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
                        "parser_provider": result.parser_provider,
                        "extract_method": result.extract_method,
                    },
                )
            )
    else:
        docs.append(
            LCDocument(
                page_content=text,
                metadata={
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "source": filename,
                    "parser_provider": result.parser_provider,
                    "extract_method": result.extract_method,
                },
            )
        )

    if not docs:
        raise ValueError("No text extracted from file")

    docs = splitter.split_documents(docs)
    for idx, doc in enumerate(docs, start=1):
        doc.metadata.setdefault("chunk", idx)

    _emit(stage_callback, "index_dense", 75, "Indexing dense vectors")
    vectorstore = get_vectorstore(user_id)
    batch_size = max(1, int(settings.ingest_vector_batch_size))
    for start in range(0, len(docs), batch_size):
        vectorstore.add_documents(docs[start : start + batch_size])
    vectorstore.persist()

    _emit(stage_callback, "index_lexical", 90, "Indexing lexical chunks")
    append_lexical_chunks(user_id, kb_id, docs)

    _emit(stage_callback, "done", 100, "Document indexed successfully")

    char_count = len(text)
    timing = {
        **{k: float(v) for k, v in (result.timing_ms or {}).items()},
        "parse_total": round(parse_elapsed, 2),
    }

    if return_details:
        return IngestResult(
            text_path=text_path,
            num_chunks=len(docs),
            num_pages=result.page_count,
            char_count=char_count,
            parser_provider=result.parser_provider,
            extract_method=result.extract_method,
            quality_score=result.quality_score,
            diagnostics=result.diagnostics,
            timing=timing,
        )

    return text_path, len(docs), result.page_count, char_count
