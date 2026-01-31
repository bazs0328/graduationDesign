from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import ChatMessage, ChatSession, Document
from app.schemas import ChatMessageOut, ChatSessionCreateRequest, ChatSessionOut

router = APIRouter()


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
def list_sessions(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == resolved_user_id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


@router.post("/chat/sessions", response_model=ChatSessionOut)
def create_session(payload: ChatSessionCreateRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)

    doc_id = None
    kb_id = None
    if payload.doc_id:
        doc = (
            db.query(Document)
            .filter(Document.id == payload.doc_id, Document.user_id == resolved_user_id)
            .first()
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        doc_id = doc.id
        kb_id = doc.kb_id
    elif payload.kb_id:
        try:
            kb = ensure_kb(db, resolved_user_id, payload.kb_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        kb_id = kb.id
    else:
        kb_id = ensure_kb(db, resolved_user_id, None).id

    title = (payload.name or "").strip() or None
    session = ChatSession(
        id=str(uuid4()),
        user_id=resolved_user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        title=title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def list_messages(session_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == resolved_user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
