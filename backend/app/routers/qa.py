import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.users import ensure_user
from app.core.knowledge_bases import ensure_kb
from app.core.vectorstore import get_vectorstore
from app.db import get_db
from app.models import ChatMessage, ChatSession, Document, QARecord
from app.schemas import QARequest, QAResponse, SourceSnippet
from app.services.learner_profile import get_or_create_profile, get_weak_concepts_by_mastery
from app.services.learning_path import invalidate_learning_path_result_cache
from app.services.mastery import record_study_interaction
from app.services.qa import (
    NO_RESULTS_ANSWER,
    generate_qa_answer,
    normalize_qa_mode,
    prepare_qa_answer,
    stream_qa_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter()

HISTORY_LIMIT = 6
HISTORY_FETCH_LIMIT = 24
QA_HISTORY_TOTAL_CHAR_BUDGET = 2400
QA_HISTORY_RECENT_CHAR_BUDGET = 1600
QA_HISTORY_SUMMARY_CHAR_BUDGET = 700
QA_HISTORY_LINE_PREVIEW_CHARS = 220


@dataclass
class QAResolvedContext:
    resolved_user_id: str
    doc_id: str | None
    kb_id: str | None
    history: str | None
    session: ChatSession | None
    profile: Any
    weak_concepts: list[str]


def _truncate_history_text(value: str, limit: int) -> str:
    text = " ".join((value or "").replace("\r", "\n").split())
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _render_history_line(role: str, content: str, preview_chars: int = QA_HISTORY_LINE_PREVIEW_CHARS) -> str:
    return f"{role}: {_truncate_history_text(content, preview_chars)}"


def _fit_history_block(lines: list[str], max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    output: list[str] = []
    for line in lines:
        candidate = line.strip()
        if not candidate:
            continue
        joined = "\n".join(output + [candidate])
        if len(joined) <= max_chars:
            output.append(candidate)
            continue
        remaining = max_chars - len("\n".join(output))
        if output:
            remaining -= 1  # newline
        if remaining > 6:
            output.append(_truncate_history_text(candidate, remaining))
        break
    return "\n".join(output)


def _build_history_text(history_rows: list[ChatMessage]) -> str | None:
    if not history_rows:
        return None
    ordered = list(reversed(history_rows))
    recent_rows = ordered[-HISTORY_LIMIT:] if HISTORY_LIMIT > 0 else ordered
    older_rows = ordered[:-HISTORY_LIMIT] if HISTORY_LIMIT > 0 else []

    recent_lines = [_render_history_line(row.role, row.content) for row in recent_rows]
    recent_block = _fit_history_block(recent_lines, QA_HISTORY_RECENT_CHAR_BUDGET)
    if recent_block:
        recent_block = "[Recent messages]\n" + recent_block

    summary_block = ""
    if older_rows:
        user_count = sum(1 for row in older_rows if row.role == "user")
        assistant_count = sum(1 for row in older_rows if row.role == "assistant")
        summary_lines = [
            f"[Earlier conversation summary] messages={len(older_rows)}, user={user_count}, assistant={assistant_count}",
        ]
        # Keep the latest older messages as a concise bridge into the recent window.
        for row in older_rows[-4:]:
            summary_lines.append(_render_history_line(row.role, row.content, preview_chars=90))
        summary_block = _fit_history_block(summary_lines, QA_HISTORY_SUMMARY_CHAR_BUDGET)

    combined = "\n".join([block for block in [summary_block, recent_block] if block]).strip()
    if not combined:
        return None
    return _truncate_history_text(combined, QA_HISTORY_TOTAL_CHAR_BUDGET)


def _serialize_sources(sources: list[dict]) -> list[dict]:
    return [
        {
            "source": s.get("source", ""),
            "snippet": s.get("snippet", ""),
            "doc_id": s.get("doc_id"),
            "kb_id": s.get("kb_id"),
            "page": s.get("page"),
            "chunk": s.get("chunk"),
        }
        for s in (sources or [])
    ]


def _resolve_qa_request_context(payload: QARequest, db: Session) -> QAResolvedContext:
    resolved_user_id = ensure_user(db, payload.user_id)
    doc = None
    kb_id = None
    doc_id = None
    history = None
    session = None

    if payload.session_id:
        session = (
            db.query(ChatSession)
            .filter(
                ChatSession.id == payload.session_id,
                ChatSession.user_id == resolved_user_id,
            )
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if payload.doc_id and session.doc_id and payload.doc_id != session.doc_id:
            raise HTTPException(
                status_code=400, detail="Session is bound to a different document"
            )
        if payload.kb_id and session.kb_id and payload.kb_id != session.kb_id:
            raise HTTPException(
                status_code=400, detail="Session is bound to a different knowledge base"
            )

    if payload.doc_id:
        doc = (
            db.query(Document)
            .filter(Document.id == payload.doc_id, Document.user_id == resolved_user_id)
            .first()
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail="Document is still processing")
        doc_id = doc.id
        kb_id = doc.kb_id
    elif payload.kb_id:
        try:
            kb = ensure_kb(db, resolved_user_id, payload.kb_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        kb_id = kb.id
    elif session:
        doc_id = session.doc_id
        kb_id = session.kb_id
        if not doc_id and not kb_id:
            raise HTTPException(status_code=400, detail="Session has no context bound")
    else:
        raise HTTPException(status_code=400, detail="doc_id or kb_id is required")

    if session:
        history_rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_FETCH_LIMIT)
            .all()
        )
        if history_rows:
            history = _build_history_text(history_rows)

    profile = get_or_create_profile(db, resolved_user_id)
    weak_concepts = get_weak_concepts_by_mastery(db, resolved_user_id)

    return QAResolvedContext(
        resolved_user_id=resolved_user_id,
        doc_id=doc_id,
        kb_id=kb_id,
        history=history,
        session=session,
        profile=profile,
        weak_concepts=weak_concepts,
    )


def _persist_qa_result(
    db: Session,
    payload: QARequest,
    ctx: QAResolvedContext,
    answer: str,
    sources: list[dict],
) -> None:
    record = QARecord(
        id=str(uuid4()),
        user_id=ctx.resolved_user_id,
        kb_id=ctx.kb_id,
        doc_id=ctx.doc_id,
        question=payload.question,
        answer=answer,
    )
    db.add(record)

    if ctx.session:
        if not ctx.session.title:
            ctx.session.title = payload.question[:60]
            db.add(ctx.session)
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=ctx.session.id,
                role="user",
                content=payload.question,
            )
        )
        sources_list = _serialize_sources(sources)
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=ctx.session.id,
                role="assistant",
                content=answer,
                sources_json=json.dumps(sources_list, ensure_ascii=False) if sources_list else None,
            )
        )

    _update_mastery_from_qa(
        db,
        ctx.resolved_user_id,
        payload.question,
        ctx.doc_id,
        ctx.kb_id,
        payload.focus,
    )
    db.commit()
    invalidate_learning_path_result_cache(db, ctx.kb_id)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _http_error_event(exc: HTTPException, stage: str) -> tuple[dict, dict]:
    detail = str(exc.detail)
    code = "validation_error"
    retryable = False
    if exc.status_code == 404:
        code = "not_found"
    elif exc.status_code >= 500:
        code = "unknown"
        retryable = True
    elif exc.status_code == 409:
        code = "validation_error"
    status_payload = {"stage": "failed", "message": detail}
    error_payload = {
        "code": code,
        "stage": stage,
        "message": detail,
        "retryable": retryable,
    }
    return status_payload, error_payload


def _qa_stream_response(payload: QARequest, db: Session) -> StreamingResponse:
    def event_iter():
        total_started = time.perf_counter()
        retrieve_started = total_started
        retrieve_ms = 0
        generate_ms = 0
        current_stage = "retrieving"
        ctx: QAResolvedContext | None = None
        try:
            yield _sse_event(
                "status",
                {"stage": "retrieving", "message": "正在检索相关片段..."},
            )
            ctx = _resolve_qa_request_context(payload, db)
            prepared = prepare_qa_answer(
                user_id=ctx.resolved_user_id,
                question=payload.question,
                doc_id=ctx.doc_id,
                kb_id=ctx.kb_id,
                history=ctx.history,
                top_k=payload.top_k,
                fetch_k=payload.fetch_k,
                ability_level=ctx.profile.ability_level,
                weak_concepts=ctx.weak_concepts,
                focus_keypoint=payload.focus,
                mode=payload.mode,
            )
            retrieve_ms = int((time.perf_counter() - retrieve_started) * 1000)
            retrieved_count = int(prepared.get("retrieved_count") or 0)
            sources = prepared.get("sources") or []
            yield _sse_event(
                "sources",
                {
                    "sources": _serialize_sources(sources),
                    "retrieved_count": retrieved_count,
                },
            )

            if prepared.get("no_results"):
                no_results_answer = NO_RESULTS_ANSWER
                resolved_mode = prepared.get("mode") or normalize_qa_mode(payload.mode)
                current_stage = "saving"
                _persist_qa_result(db, payload, ctx, no_results_answer, [])
                total_ms = int((time.perf_counter() - total_started) * 1000)
                done_payload = {
                    "session_id": ctx.session.id if ctx.session else None,
                    "ability_level": getattr(ctx.profile, "ability_level", None),
                    "mode": resolved_mode,
                    "result": "no_results",
                    "retrieved_count": 0,
                    "timings": {
                        "retrieve_ms": retrieve_ms,
                        "generate_ms": 0,
                        "total_ms": total_ms,
                    },
                }
                yield _sse_event(
                    "status",
                    {
                        "stage": "done",
                        "message": "未检索到相关内容",
                        "result": "no_results",
                        "retrieved_count": 0,
                        "timings": done_payload["timings"],
                    },
                )
                yield _sse_event("done", done_payload)
                return

            llm = get_llm(temperature=0.2)
            current_stage = "generating"
            yield _sse_event(
                "status",
                {
                    "stage": "generating",
                    "message": "正在生成回答...",
                    "retrieved_count": retrieved_count,
                    "timings": {"retrieve_ms": retrieve_ms},
                },
            )

            generate_started = time.perf_counter()
            answer_parts: list[str] = []
            for delta in stream_qa_answer(llm, prepared["formatted_messages"]):
                if not delta:
                    continue
                answer_parts.append(delta)
                yield _sse_event("chunk", {"delta": delta})
            generate_ms = int((time.perf_counter() - generate_started) * 1000)

            answer = "".join(answer_parts).strip()
            if not answer:
                answer = generate_qa_answer(llm, prepared["formatted_messages"])
                generate_ms = max(generate_ms, 1)

            yield _sse_event(
                "status",
                {
                    "stage": "saving",
                    "message": "正在保存会话记录...",
                    "retrieved_count": retrieved_count,
                    "timings": {
                        "retrieve_ms": retrieve_ms,
                        "generate_ms": generate_ms,
                    },
                },
            )
            current_stage = "saving"
            _persist_qa_result(db, payload, ctx, answer, sources)
            total_ms = int((time.perf_counter() - total_started) * 1000)
            done_payload = {
                "session_id": ctx.session.id if ctx.session else None,
                "ability_level": getattr(ctx.profile, "ability_level", None),
                "mode": prepared.get("mode") or normalize_qa_mode(payload.mode),
                "result": "ok",
                "retrieved_count": retrieved_count,
                "timings": {
                    "retrieve_ms": retrieve_ms,
                    "generate_ms": generate_ms,
                    "total_ms": total_ms,
                },
            }
            yield _sse_event(
                "status",
                {
                    "stage": "done",
                    "message": "回答生成完成",
                    "result": "ok",
                    "retrieved_count": retrieved_count,
                    "timings": done_payload["timings"],
                },
            )
            yield _sse_event("done", done_payload)
        except HTTPException as exc:
            if db.in_transaction():
                db.rollback()
            status_payload, error_payload = _http_error_event(exc, current_stage)
            yield _sse_event("status", status_payload)
            yield _sse_event("error", error_payload)
        except Exception as exc:
            if db.in_transaction():
                db.rollback()
            logger.exception("QA stream failed")
            total_ms = int((time.perf_counter() - total_started) * 1000)
            if current_stage == "generating":
                error_code = "generation_failed"
                retryable = True
            elif current_stage == "saving":
                error_code = "unknown"
                retryable = False
            else:
                error_code = "unknown"
                retryable = True
            yield _sse_event(
                "status",
                {
                    "stage": "failed",
                    "message": "回答生成失败",
                    "timings": {
                        "retrieve_ms": retrieve_ms,
                        "generate_ms": generate_ms,
                        "total_ms": total_ms,
                    },
                },
            )
            yield _sse_event(
                "error",
                {
                    "code": error_code,
                    "stage": current_stage,
                    "message": str(exc) or "回答生成失败",
                    "retryable": retryable,
                },
            )

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/qa", response_model=QAResponse)
def ask_question(payload: QARequest, db: Session = Depends(get_db)):
    ctx = _resolve_qa_request_context(payload, db)
    prepared = prepare_qa_answer(
        user_id=ctx.resolved_user_id,
        question=payload.question,
        doc_id=ctx.doc_id,
        kb_id=ctx.kb_id,
        history=ctx.history,
        top_k=payload.top_k,
        fetch_k=payload.fetch_k,
        ability_level=ctx.profile.ability_level,
        weak_concepts=ctx.weak_concepts,
        focus_keypoint=payload.focus,
        mode=payload.mode,
    )
    if prepared["no_results"]:
        answer = NO_RESULTS_ANSWER
        sources = []
    else:
        llm = get_llm(temperature=0.2)
        answer = generate_qa_answer(llm, prepared["formatted_messages"])
        sources = prepared["sources"]

    _persist_qa_result(db, payload, ctx, answer, sources)

    return QAResponse(
        answer=answer,
        sources=[SourceSnippet(**s) for s in sources],
        session_id=ctx.session.id if ctx.session else None,
        ability_level=ctx.profile.ability_level,
        mode=prepared.get("mode") or normalize_qa_mode(payload.mode),
    )


@router.post("/qa/stream")
def ask_question_stream(payload: QARequest, db: Session = Depends(get_db)):
    return _qa_stream_response(payload, db)


@router.get("/qa/stream")
def ask_question_stream_get(
    question: str,
    db: Session = Depends(get_db),
    user_id: str | None = None,
    doc_id: str | None = None,
    kb_id: str | None = None,
    session_id: str | None = None,
    top_k: int | None = Query(default=None, ge=1, le=20),
    fetch_k: int | None = Query(default=None, ge=1, le=50),
    focus: str | None = None,
    mode: str | None = None,
):
    payload = QARequest(
        question=question,
        user_id=user_id,
        doc_id=doc_id,
        kb_id=kb_id,
        session_id=session_id,
        top_k=top_k,
        fetch_k=fetch_k,
        focus=focus,
        mode=mode,
    )
    return _qa_stream_response(payload, db)


def _update_mastery_from_qa(
    db: Session,
    user_id: str,
    question: str,
    doc_id: str | None,
    kb_id: str | None,
    focus_keypoint_text: str | None = None,
) -> None:
    """Match the user's question to keypoints and record a study interaction."""
    from app.models import Keypoint
    
    # 优先：如果指定了 focus_keypoint_text（从学习路径跳转），直接查找匹配的知识点
    if focus_keypoint_text and focus_keypoint_text.strip():
        focus_text = focus_keypoint_text.strip()
        query = db.query(Keypoint).filter(Keypoint.user_id == user_id)
        if doc_id:
            query = query.filter(Keypoint.doc_id == doc_id)
        elif kb_id:
            query = query.filter(Keypoint.kb_id == kb_id)
        else:
            return
        
        # 精确匹配或模糊匹配知识点文本
        matched_kp = query.filter(Keypoint.text == focus_text).first()
        if not matched_kp:
            # 尝试模糊匹配（去除空格和标点）
            import re
            normalized_focus = re.sub(r'[^\w\s]', '', focus_text.lower().strip())
            for kp in query.all():
                normalized_kp_text = re.sub(r'[^\w\s]', '', kp.text.lower().strip())
                if normalized_kp_text == normalized_focus or normalized_focus in normalized_kp_text:
                    matched_kp = kp
                    break
        
        if matched_kp:
            result = record_study_interaction(db, matched_kp.id)
            if result:
                logger.info(f"QA mastery updated for keypoint {matched_kp.id} (focus match)")
            return
    
    # 回退：使用向量搜索匹配问题文本到知识点
    filter_dict: dict = {"type": "keypoint"}
    if doc_id:
        filter_dict["doc_id"] = doc_id
    elif kb_id:
        filter_dict["kb_id"] = kb_id
    else:
        return

    try:
        vectorstore = get_vectorstore(user_id)
        results = vectorstore.similarity_search_with_score(
            question, k=3, filter=filter_dict,
        )
    except Exception as e:
        logger.debug(f"QA mastery: vector search failed: {e}", exc_info=True)
        return

    updated_count = 0
    for doc_result, score in results:
        if score > 1.0:
            continue
        meta = getattr(doc_result, "metadata", {}) or {}
        kp_id = meta.get("keypoint_id")
        if kp_id:
            result = record_study_interaction(db, kp_id)
            if result:
                updated_count += 1
    
    if updated_count > 0:
        logger.info(f"QA mastery updated for {updated_count} keypoint(s) (vector search match)")
