from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.core.knowledge_bases import ensure_kb
from app.db import get_db
from app.models import ChatMessage, ChatSession, Document, QARecord
from app.schemas import QARequest, QAResponse, SourceSnippet
from app.services.qa import answer_question

router = APIRouter()

HISTORY_LIMIT = 6


@router.post("/qa", response_model=QAResponse)
def ask_question(payload: QARequest, db: Session = Depends(get_db)):
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
            .limit(HISTORY_LIMIT)
            .all()
        )
        if history_rows:
            history_rows = list(reversed(history_rows))
            history = "\n".join(f"{row.role}: {row.content}" for row in history_rows)

    answer, sources = answer_question(
        resolved_user_id,
        payload.question,
        doc_id=doc_id,
        kb_id=kb_id,
        history=history,
        top_k=payload.top_k,
        fetch_k=payload.fetch_k,
    )

    record = QARecord(
        id=str(uuid4()),
        user_id=resolved_user_id,
        doc_id=doc_id,
        question=payload.question,
        answer=answer,
    )
    db.add(record)

    if session:
        if not session.title:
            session.title = payload.question[:60]
            db.add(session)
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="user",
                content=payload.question,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="assistant",
                content=answer,
            )
        )

    db.commit()

    return QAResponse(
        answer=answer,
        sources=[SourceSnippet(**s) for s in sources],
        session_id=session.id if session else None,
    )
