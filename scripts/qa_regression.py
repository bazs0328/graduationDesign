#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import textwrap
import time
from uuid import uuid4

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_candidate = os.path.join(REPO_ROOT, "backend")
if os.path.isdir(backend_candidate):
    BACKEND_ROOT = backend_candidate
else:
    # Docker dev mode may mount backend as repo root.
    BACKEND_ROOT = REPO_ROOT
sys.path.insert(0, BACKEND_ROOT)

from app.core.kb_metadata import init_kb_metadata  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.paths import ensure_kb_dirs, kb_base_dir, user_base_dir  # noqa: E402
from app.core.users import ensure_user  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Document, KnowledgeBase  # noqa: E402
from app.services.ingest import ingest_document  # noqa: E402
from app.services.lexical import append_lexical_chunks, bm25_search  # noqa: E402
from app.services.qa import retrieve_documents  # noqa: E402
from app.services.text_extraction import extract_text  # noqa: E402
from app.core.vectorstore import get_vectorstore  # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

TOPICS = [
    "Linear Algebra",
    "Probability",
    "Operating Systems",
    "Computer Networks",
    "Machine Learning",
    "Database Systems",
    "Software Engineering",
    "Algorithms",
]


def build_doc_text(topic: str, key: str, noise_keys: list[str]) -> str:
    paragraphs = []
    paragraphs.append(f"Topic: {topic}. This document focuses on {topic.lower()} basics.")
    paragraphs.append(
        f"Definition {key}: {key} refers to a core concept in {topic.lower()} with practical implications."
    )
    paragraphs.append(
        "This section provides examples, common pitfalls, and brief intuition."
    )
    for idx, noise in enumerate(noise_keys, start=1):
        paragraphs.append(
            f"Related mention {idx}: {noise} is discussed briefly as a contrasting idea."
        )
    return "\n\n".join(textwrap.fill(p, width=100) for p in paragraphs)


def ingest_bm25_only(file_path: str, filename: str, doc_id: str, user_id: str, kb_id: str):
    suffix = os.path.splitext(filename)[1].lower()
    extraction = extract_text(file_path, suffix)
    text = extraction.text.strip()
    if not text:
        raise ValueError("No text extracted from file")

    text_dir = os.path.join(user_base_dir(user_id), "text")
    os.makedirs(text_dir, exist_ok=True)
    text_path = os.path.join(text_dir, f"{doc_id}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    docs = []
    if suffix == ".pdf":
        for page_num, page_text in enumerate(extraction.pages, start=1):
            if not page_text:
                continue
            docs.append(
                {
                    "content": page_text,
                    "metadata": {
                        "doc_id": doc_id,
                        "kb_id": kb_id,
                        "source": filename,
                        "page": page_num,
                    },
                }
            )
    else:
        docs.append(
            {
                "content": text,
                "metadata": {"doc_id": doc_id, "kb_id": kb_id, "source": filename},
            }
        )

    split_docs = []
    for item in docs:
        split = splitter.create_documents([item["content"]], metadatas=[item["metadata"]])
        split_docs.extend(split)

    for idx, doc in enumerate(split_docs, start=1):
        doc.metadata.setdefault("chunk", idx)

    append_lexical_chunks(user_id, kb_id, split_docs)
    return text_path, len(split_docs), extraction.page_count, len(text)


def main():
    parser = argparse.ArgumentParser(description="QA regression dataset (synthetic)")
    parser.add_argument("--user-id", default="qa_regression")
    parser.add_argument("--kb-name", default=None)
    parser.add_argument("--doc-count", type=int, default=12)
    parser.add_argument("--queries", type=int, default=None)
    parser.add_argument("--mode", choices=["hybrid", "dense", "bm25"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fetch-k", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-recall", type=float, default=0.8)
    parser.add_argument("--out", default="/tmp/qa_regression_results.json")
    args = parser.parse_args()

    random.seed(args.seed)
    kb_name = args.kb_name or f"qa_reg_{int(time.time())}"
    if args.mode in ("hybrid", "dense"):
        settings.rag_mode = args.mode

    db = SessionLocal()
    try:
        ensure_user(db, args.user_id)
        kb = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.user_id == args.user_id, KnowledgeBase.name == kb_name)
            .first()
        )
        if not kb:
            kb = KnowledgeBase(id=str(uuid4()), user_id=args.user_id, name=kb_name)
            db.add(kb)
            db.commit()
            db.refresh(kb)

        ensure_kb_dirs(args.user_id, kb.id)
        init_kb_metadata(args.user_id, kb.id)

        raw_dir = os.path.join(kb_base_dir(args.user_id, kb.id), "raw")
        os.makedirs(raw_dir, exist_ok=True)

        doc_infos = []
        for idx in range(args.doc_count):
            topic = TOPICS[idx % len(TOPICS)]
            key = f"KEY_{idx:03d}"
            noise = [f"KEY_{(idx + j + 1) % args.doc_count:03d}" for j in range(2)]
            content = build_doc_text(topic, key, noise)

            filename = f"doc_{idx:03d}_{topic.replace(' ', '_')}.txt"
            doc_id = str(uuid4())
            file_path = os.path.join(raw_dir, f"{doc_id}_{filename}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            if args.mode == "bm25":
                text_path, num_chunks, num_pages, char_count = ingest_bm25_only(
                    file_path, filename, doc_id, args.user_id, kb.id
                )
            else:
                text_path, num_chunks, num_pages, char_count = ingest_document(
                    file_path, filename, doc_id, args.user_id, kb.id
                )

            doc = Document(
                id=doc_id,
                user_id=args.user_id,
                kb_id=kb.id,
                filename=filename,
                file_type="txt",
                text_path=text_path,
                num_chunks=num_chunks,
                num_pages=num_pages,
                char_count=char_count,
                file_size=len(content.encode("utf-8")),
                file_hash=None,
                status="ready",
            )
            db.add(doc)
            doc_infos.append({"doc_id": doc_id, "key": key, "filename": filename})

        db.commit()

        total_queries = args.queries or len(doc_infos)
        queries = []
        for i in range(total_queries):
            info = doc_infos[i % len(doc_infos)]
            queries.append({
                "question": f"Explain {info['key']} and its role in the topic.",
                "expected_doc_id": info["doc_id"],
            })

        hits = 0
        details = []

        if args.mode == "dense":
            vectorstore = get_vectorstore(args.user_id)

        for idx, item in enumerate(queries, start=1):
            if args.mode == "bm25":
                results = bm25_search(
                    args.user_id, kb.id, item["question"], top_k=args.top_k
                )
                docs = [doc for doc, _ in results]
            elif args.mode == "dense":
                try:
                    docs = vectorstore.similarity_search(
                        item["question"], k=args.top_k, filter={"kb_id": kb.id}
                    )
                except Exception:
                    docs = []
            else:
                docs = retrieve_documents(
                    user_id=args.user_id,
                    question=item["question"],
                    kb_id=kb.id,
                    top_k=args.top_k,
                    fetch_k=args.fetch_k,
                )

            found = False
            for doc in docs:
                if (doc.metadata or {}).get("doc_id") == item["expected_doc_id"]:
                    found = True
                    break
            hits += 1 if found else 0
            details.append(
                {
                    "question": item["question"],
                    "expected_doc_id": item["expected_doc_id"],
                    "hit": found,
                }
            )

        recall = hits / max(len(queries), 1)
        result = {
            "kb_id": kb.id,
            "kb_name": kb_name,
            "user_id": args.user_id,
            "mode": args.mode,
            "top_k": args.top_k,
            "fetch_k": args.fetch_k,
            "queries": len(queries),
            "recall": round(recall, 4),
            "min_recall": args.min_recall,
            "details": details,
        }

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(json.dumps(result, indent=2, ensure_ascii=False))

        if recall < args.min_recall:
            sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
