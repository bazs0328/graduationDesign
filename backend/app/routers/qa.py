import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.core.knowledge_bases import ensure_kb
from app.core.vectorstore import get_vectorstore
from app.db import get_db
from app.models import ChatMessage, ChatSession, Document, QARecord
from app.schemas import QARequest, QAResponse, SourceSnippet
from app.services.learner_profile import get_or_create_profile, get_weak_concepts
from app.services.mastery import record_study_interaction
from app.services.qa import answer_question

logger = logging.getLogger(__name__)

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

    profile = get_or_create_profile(db, resolved_user_id)
    weak_concepts = get_weak_concepts(profile)

    answer, sources = answer_question(
        resolved_user_id,
        payload.question,
        doc_id=doc_id,
        kb_id=kb_id,
        history=history,
        top_k=payload.top_k,
        fetch_k=payload.fetch_k,
        ability_level=profile.ability_level,
        weak_concepts=weak_concepts,
        focus_keypoint=payload.focus,
    )

    record = QARecord(
        id=str(uuid4()),
        user_id=resolved_user_id,
        kb_id=kb_id,
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
        sources_list = [
            {
                "source": s.get("source", ""),
                "snippet": s.get("snippet", ""),
                "doc_id": s.get("doc_id"),
                "kb_id": s.get("kb_id"),
                "page": s.get("page"),
                "chunk": s.get("chunk"),
            }
            for s in sources
        ]
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="assistant",
                content=answer,
                sources_json=json.dumps(sources_list, ensure_ascii=False) if sources_list else None,
            )
        )

    _update_mastery_from_qa(db, resolved_user_id, payload.question, doc_id, kb_id, payload.focus)

    db.commit()

    return QAResponse(
        answer=answer,
        sources=[SourceSnippet(**s) for s in sources],
        session_id=session.id if session else None,
        ability_level=profile.ability_level,
    )


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
