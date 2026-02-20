import os
import shutil
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.kb_metadata import init_kb_metadata
from app.core.kb_metadata import get_kb_parse_settings
from app.core.kb_metadata import get_kb_rag_settings
from app.core.kb_metadata import remove_file_hash
from app.core.kb_metadata import update_kb_parse_settings
from app.core.kb_metadata import update_kb_rag_settings
from app.core.paths import ensure_kb_dirs, kb_base_dir, user_base_dir
from app.core.vectorstore import delete_doc_vectors
from app.core.users import ensure_user
from app.db import get_db
from app.models import (
    ChatMessage,
    ChatSession,
    DocumentAsset,
    Document,
    IngestRun,
    Keypoint,
    KeypointDependency,
    KeypointRecord,
    KnowledgeBase,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
)
from app.schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseOut,
    KnowledgeBaseParseSettingsResponse,
    KnowledgeBaseParseSettingsUpdateRequest,
    KnowledgeBaseRagSettingsResponse,
    KnowledgeBaseRagSettingsUpdateRequest,
    KnowledgeBaseUpdateRequest,
)
from app.services.lexical import remove_doc_chunks

router = APIRouter()


@router.get("/kb", response_model=list[KnowledgeBaseOut])
def list_kbs(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == resolved_user_id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )


@router.post("/kb", response_model=KnowledgeBaseOut)
def create_kb(payload: KnowledgeBaseCreateRequest, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Knowledge base name is required")

    resolved_user_id = ensure_user(db, payload.user_id)
    existing = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == resolved_user_id,
            KnowledgeBase.name == payload.name.strip(),
        )
        .first()
    )
    if existing:
        return existing

    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id=resolved_user_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    ensure_kb_dirs(resolved_user_id, kb.id)
    init_kb_metadata(resolved_user_id, kb.id)
    return kb


@router.get("/kb/{kb_id}/settings", response_model=KnowledgeBaseParseSettingsResponse)
def get_kb_settings(kb_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    settings_obj = get_kb_parse_settings(resolved_user_id, kb_id)
    return KnowledgeBaseParseSettingsResponse(
        kb_id=kb_id,
        parse_policy=settings_obj.get("parse_policy", "balanced"),
        preferred_parser=settings_obj.get("preferred_parser", "auto"),
    )


@router.patch("/kb/{kb_id}/settings", response_model=KnowledgeBaseParseSettingsResponse)
def patch_kb_settings(
    kb_id: str,
    payload: KnowledgeBaseParseSettingsUpdateRequest,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, payload.user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    try:
        updated = update_kb_parse_settings(
            resolved_user_id,
            kb_id,
            parse_policy=payload.parse_policy,
            preferred_parser=payload.preferred_parser,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KnowledgeBaseParseSettingsResponse(
        kb_id=kb_id,
        parse_policy=updated.get("parse_policy", "balanced"),
        preferred_parser=updated.get("preferred_parser", "auto"),
    )


@router.get("/kb/{kb_id}/rag-settings", response_model=KnowledgeBaseRagSettingsResponse)
def get_kb_rag_config(kb_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    settings_obj = get_kb_rag_settings(resolved_user_id, kb_id)
    return KnowledgeBaseRagSettingsResponse(
        kb_id=kb_id,
        rag_backend=settings_obj.get("rag_backend", "raganything_mineru"),
        query_mode=settings_obj.get("query_mode", "hybrid"),
        parser_preference=settings_obj.get("parser_preference", "mineru"),
    )


@router.patch("/kb/{kb_id}/rag-settings", response_model=KnowledgeBaseRagSettingsResponse)
def patch_kb_rag_config(
    kb_id: str,
    payload: KnowledgeBaseRagSettingsUpdateRequest,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, payload.user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    try:
        updated = update_kb_rag_settings(
            resolved_user_id,
            kb_id,
            rag_backend=payload.rag_backend,
            query_mode=payload.query_mode,
            parser_preference=payload.parser_preference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KnowledgeBaseRagSettingsResponse(
        kb_id=kb_id,
        rag_backend=updated.get("rag_backend", "raganything_mineru"),
        query_mode=updated.get("query_mode", "hybrid"),
        parser_preference=updated.get("parser_preference", "mineru"),
    )


@router.patch("/kb/{kb_id}", response_model=KnowledgeBaseOut)
def update_kb(
    kb_id: str,
    payload: KnowledgeBaseUpdateRequest,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, payload.user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    changed = False
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Knowledge base name is required")
        existing = (
            db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.user_id == resolved_user_id,
                KnowledgeBase.name == name,
                KnowledgeBase.id != kb.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Knowledge base name already exists")
        kb.name = name
        changed = True

    if payload.description is not None:
        kb.description = payload.description
        changed = True

    if changed:
        db.add(kb)
        db.commit()
        db.refresh(kb)
    return kb


@router.delete("/kb/{kb_id}")
def delete_kb(
    kb_id: str,
    user_id: str | None = None,
    cascade: bool = False,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == resolved_user_id)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    docs = (
        db.query(Document)
        .filter(Document.user_id == resolved_user_id, Document.kb_id == kb.id)
        .all()
    )
    if docs and not cascade:
        raise HTTPException(
            status_code=409,
            detail="Knowledge base is not empty. Retry with cascade=true to delete all documents.",
        )

    doc_ids = [doc.id for doc in docs]

    for doc in docs:
        delete_doc_vectors(resolved_user_id, doc.id)
        remove_doc_chunks(resolved_user_id, kb.id, doc.id)
        remove_file_hash(resolved_user_id, kb.id, doc.filename)
        if doc.text_path and os.path.exists(doc.text_path):
            os.remove(doc.text_path)

    if doc_ids:
        db.query(DocumentAsset).filter(
            DocumentAsset.user_id == resolved_user_id,
            DocumentAsset.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        db.query(IngestRun).filter(
            IngestRun.user_id == resolved_user_id,
            IngestRun.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        db.query(SummaryRecord).filter(
            SummaryRecord.user_id == resolved_user_id,
            SummaryRecord.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        db.query(KeypointRecord).filter(
            KeypointRecord.user_id == resolved_user_id,
            KeypointRecord.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        db.query(Keypoint).filter(
            Keypoint.user_id == resolved_user_id,
            Keypoint.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        db.query(QARecord).filter(
            QARecord.user_id == resolved_user_id,
            QARecord.doc_id.in_(doc_ids),
        ).delete(synchronize_session=False)

    db.query(QARecord).filter(
        QARecord.user_id == resolved_user_id,
        QARecord.kb_id == kb.id,
    ).delete(synchronize_session=False)

    quiz_ids = {
        row[0]
        for row in db.query(Quiz.id)
        .filter(Quiz.user_id == resolved_user_id, Quiz.kb_id == kb.id)
        .all()
    }
    if doc_ids:
        quiz_ids.update(
            row[0]
            for row in db.query(Quiz.id)
            .filter(Quiz.user_id == resolved_user_id, Quiz.doc_id.in_(doc_ids))
            .all()
        )
    if quiz_ids:
        db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id.in_(list(quiz_ids))
        ).delete(synchronize_session=False)
        db.query(Quiz).filter(Quiz.id.in_(list(quiz_ids))).delete(
            synchronize_session=False
        )

    session_ids = {
        row[0]
        for row in db.query(ChatSession.id)
        .filter(ChatSession.user_id == resolved_user_id, ChatSession.kb_id == kb.id)
        .all()
    }
    if doc_ids:
        session_ids.update(
            row[0]
            for row in db.query(ChatSession.id)
            .filter(
                ChatSession.user_id == resolved_user_id,
                ChatSession.doc_id.in_(doc_ids),
            )
            .all()
        )
    if session_ids:
        db.query(ChatMessage).filter(
            ChatMessage.session_id.in_(list(session_ids))
        ).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.id.in_(list(session_ids))).delete(
            synchronize_session=False
        )

    if doc_ids:
        db.query(Document).filter(Document.id.in_(doc_ids)).delete(
            synchronize_session=False
        )

    db.query(KeypointDependency).filter(
        KeypointDependency.kb_id == kb.id
    ).delete(synchronize_session=False)
    db.delete(kb)
    db.commit()

    kb_dir = kb_base_dir(resolved_user_id, kb.id)
    if os.path.exists(kb_dir):
        shutil.rmtree(kb_dir, ignore_errors=True)
    lexical_path = os.path.join(user_base_dir(resolved_user_id), "lexical", f"{kb.id}.jsonl")
    if os.path.exists(lexical_path):
        os.remove(lexical_path)

    return {"kb_id": kb_id, "deleted": True, "cascade": cascade}
