import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import (
    Document,
    Keypoint,
    KeypointRecord,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
)
from app.schemas import (
    RecommendationAction,
    RecommendationItem,
    RecommendationNextStep,
    RecommendationsResponse,
)
from app.services.aggregate_mastery import list_kb_aggregate_mastery_points
from app.services.learner_profile import (
    get_or_create_profile,
    get_weak_concepts_by_mastery,
)
from app.services.learning_path import generate_learning_path
from app.services.mastery import (
    MASTERY_STABLE,
    is_weak_mastery,
    mastery_completion_rate,
    mastery_ratio,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ACTION_PRIORITY = {
    "summary": 100,
    "keypoints": 95,
    "review": 85,
    "quiz": 80,
    "qa": 65,
    "challenge": 55,
}

PRACTICE_DIFFICULTY_BY_ABILITY = {
    "beginner": "easy",
    "intermediate": "medium",
    "advanced": "medium",
}

CHALLENGE_DIFFICULTY_BY_ABILITY = {
    "beginner": "medium",
    "intermediate": "hard",
    "advanced": "hard",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _round_score(value: float) -> float:
    return round(_clamp(value, 0.0, 100.0), 1)


def _add_action(
    actions_by_type: dict[str, RecommendationAction],
    *,
    action_type: str,
    reason: str,
    params: dict | None = None,
    priority: int | None = None,
    cta: str | None = None,
) -> None:
    action = RecommendationAction(
        type=action_type,
        reason=reason,
        params=params or None,
        priority=priority or ACTION_PRIORITY.get(action_type, 50),
        cta=cta,
    )
    previous = actions_by_type.get(action_type)
    if not previous or action.priority >= previous.priority:
        actions_by_type[action_type] = action


def _unique_nonempty(values: list[str], *, limit: int = 3) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = (value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _build_summary_text(status: str, focus_concepts: list[str]) -> str:
    if status == "blocked":
        return "先补齐摘要与知识点，再进入练习阶段。"
    if status == "needs_practice":
        if focus_concepts:
            return f"优先围绕「{focus_concepts[0]}」进行复习与练习。"
        return "当前掌握度偏弱，建议先复习再进行测验。"
    if status == "ready_for_challenge":
        return "基础与练习表现稳定，可尝试更高难度挑战。"
    if status == "ready_for_practice":
        return "已具备基础材料，建议尽快进行一次测验校准。"
    return "学习状态稳定，可按当前节奏持续推进。"


def _build_doc_status(
    *,
    has_summary: bool,
    has_keypoints: bool,
    attempt_count: int,
    avg_score: float,
    weak_count: int,
    stable_mastery_rate: float,
) -> str:
    if not has_summary or not has_keypoints:
        return "blocked"
    if attempt_count == 0:
        return "ready_for_practice"
    if avg_score < 0.65 or weak_count > 0:
        return "needs_practice"
    if attempt_count >= 2 and avg_score >= 0.82 and stable_mastery_rate >= 0.7:
        return "ready_for_challenge"
    return "on_track"


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    user_id: str | None = None,
    kb_id: str | None = None,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    limit = max(1, min(limit, 20))
    profile = get_or_create_profile(db, resolved_user_id)
    profile_weak_concepts = get_weak_concepts_by_mastery(db, resolved_user_id)
    practice_difficulty = PRACTICE_DIFFICULTY_BY_ABILITY.get(
        profile.ability_level, "medium"
    )
    challenge_difficulty = CHALLENGE_DIFFICULTY_BY_ABILITY.get(
        profile.ability_level, "hard"
    )

    docs = (
        db.query(Document)
        .filter(
            Document.user_id == resolved_user_id,
            Document.kb_id == kb.id,
            Document.status == "ready",
        )
        .order_by(Document.created_at.desc())
        .all()
    )
    if not docs:
        return RecommendationsResponse(kb_id=kb.id, kb_name=kb.name, items=[])

    doc_ids = [doc.id for doc in docs]

    summary_counts = {
        row[0]: int(row[1] or 0)
        for row in db.query(SummaryRecord.doc_id, func.count(SummaryRecord.id))
        .filter(
            SummaryRecord.user_id == resolved_user_id,
            SummaryRecord.doc_id.in_(doc_ids),
        )
        .group_by(SummaryRecord.doc_id)
        .all()
    }
    keypoint_record_counts = {
        row[0]: int(row[1] or 0)
        for row in db.query(KeypointRecord.doc_id, func.count(KeypointRecord.id))
        .filter(
            KeypointRecord.user_id == resolved_user_id,
            KeypointRecord.doc_id.in_(doc_ids),
        )
        .group_by(KeypointRecord.doc_id)
        .all()
    }
    keypoint_v2_counts = {
        row[0]: int(row[1] or 0)
        for row in db.query(Keypoint.doc_id, func.count(Keypoint.id))
        .filter(
            Keypoint.user_id == resolved_user_id,
            Keypoint.doc_id.in_(doc_ids),
        )
        .group_by(Keypoint.doc_id)
        .all()
    }
    quiz_counts = {
        row[0]: int(row[1] or 0)
        for row in db.query(Quiz.doc_id, func.count(Quiz.id))
        .filter(
            Quiz.user_id == resolved_user_id,
            Quiz.doc_id.in_(doc_ids),
        )
        .group_by(Quiz.doc_id)
        .all()
    }
    qa_counts = {
        row[0]: int(row[1] or 0)
        for row in db.query(QARecord.doc_id, func.count(QARecord.id))
        .filter(
            QARecord.user_id == resolved_user_id,
            QARecord.doc_id.in_(doc_ids),
        )
        .group_by(QARecord.doc_id)
        .all()
    }
    attempt_stats = {
        row[0]: {
            "attempt_count": int(row[1] or 0),
            "avg_score": float(row[2] or 0.0),
        }
        for row in db.query(
            Quiz.doc_id,
            func.count(QuizAttempt.id),
            func.avg(QuizAttempt.score),
        )
        .join(QuizAttempt, QuizAttempt.quiz_id == Quiz.id)
        .filter(
            Quiz.user_id == resolved_user_id,
            QuizAttempt.user_id == resolved_user_id,
            Quiz.doc_id.in_(doc_ids),
        )
        .group_by(Quiz.doc_id)
        .all()
    }

    keypoints_by_doc: dict[str, list[dict]] = defaultdict(list)
    for point in list_kb_aggregate_mastery_points(db, resolved_user_id, kb.id):
        for source_doc_id in point.source_doc_ids:
            if source_doc_id not in doc_ids:
                continue
            keypoints_by_doc[source_doc_id].append(
                {
                    "text": str(point.text or "").strip(),
                    "mastery_level": float(point.mastery_level or 0.0),
                    "attempt_count": int(point.attempt_count or 0),
                }
            )

    try:
        (
            learning_path,
            learning_path_edges,
            learning_path_stages,
            learning_path_modules,
            learning_path_summary,
        ) = generate_learning_path(db, resolved_user_id, kb.id, limit=max(20, limit * 4))
    except Exception:
        logger.exception("Failed to generate learning path, returning empty")
        learning_path, learning_path_edges = [], []
        learning_path_stages, learning_path_modules, learning_path_summary = [], [], {}

    learning_focus_by_doc: dict[str, list[str]] = defaultdict(list)
    for item in learning_path:
        if item.priority == "completed":
            continue
        learning_focus_by_doc[item.doc_id].append((item.text or "").strip())

    ranked_items: list[tuple[float, float, RecommendationItem]] = []
    for doc in docs:
        doc_id = doc.id
        has_summary = summary_counts.get(doc_id, 0) > 0
        has_keypoints = (
            keypoint_record_counts.get(doc_id, 0) > 0
            or keypoint_v2_counts.get(doc_id, 0) > 0
        )
        quiz_count = quiz_counts.get(doc_id, 0)
        qa_count = qa_counts.get(doc_id, 0)
        attempt_count = int(attempt_stats.get(doc_id, {}).get("attempt_count", 0))
        avg_score = float(attempt_stats.get(doc_id, {}).get("avg_score", 0.0))

        keypoint_infos = keypoints_by_doc.get(doc_id, [])
        mastery_values = [item["mastery_level"] for item in keypoint_infos]
        mastery_completion = mastery_completion_rate(mastery_values)
        stable_mastery_rate = mastery_ratio(mastery_values, threshold=MASTERY_STABLE)
        weak_keypoints = [
            item
            for item in sorted(keypoint_infos, key=lambda x: x["mastery_level"])
            if is_weak_mastery(item["mastery_level"]) and item["text"]
        ]

        focus_concepts = _unique_nonempty(
            [item["text"] for item in weak_keypoints]
            + learning_focus_by_doc.get(doc_id, [])
            + profile_weak_concepts,
            limit=3,
        )

        status = _build_doc_status(
            has_summary=has_summary,
            has_keypoints=has_keypoints,
            attempt_count=attempt_count,
            avg_score=avg_score,
            weak_count=len(weak_keypoints),
            stable_mastery_rate=stable_mastery_rate,
        )

        summary_component = 1.0 if has_summary else 0.0
        keypoint_component = 1.0 if has_keypoints else 0.0
        quiz_component = _clamp(attempt_count / 2.0, 0.0, 1.0)
        qa_component = _clamp(qa_count / 2.0, 0.0, 1.0)
        # Keep recommendation completion aligned with learning-path completion:
        # both use "mastered keypoint ratio" as the mastery completion signal.
        mastery_component = mastery_completion if has_keypoints else 0.0
        completion_score = _round_score(
            100
            * (
                0.14 * summary_component
                + 0.14 * keypoint_component
                + 0.08 * quiz_component
                + 0.04 * qa_component
                + 0.60 * mastery_component
            )
        )

        urgency_score = 0.0
        if not has_summary:
            urgency_score += 35
        if not has_keypoints:
            urgency_score += 30
        if attempt_count == 0:
            urgency_score += 20
        elif avg_score < 0.65:
            urgency_score += (0.65 - avg_score) * 40
        if weak_keypoints:
            urgency_score += min(15.0, len(weak_keypoints) * 4.0)
        if qa_count == 0 and has_keypoints:
            urgency_score += 5
        if status == "ready_for_challenge":
            urgency_score = min(urgency_score, 30)
        urgency_score = _round_score(max(5.0, urgency_score))

        actions_by_type: dict[str, RecommendationAction] = {}
        if not has_summary:
            _add_action(
                actions_by_type,
                action_type="summary",
                reason="该文档还没有摘要，先建立整体理解。",
                cta="生成摘要",
            )
        if not has_keypoints:
            _add_action(
                actions_by_type,
                action_type="keypoints",
                reason="尚未提取知识点，无法进行精细化推荐。",
                cta="提取要点",
            )
        if has_keypoints:
            if focus_concepts:
                _add_action(
                    actions_by_type,
                    action_type="review",
                    reason="检测到薄弱知识点，建议先复习再训练。",
                    params={"focus_concepts": focus_concepts},
                    cta="开始复习",
                )
            if attempt_count == 0:
                params = {"difficulty": practice_difficulty}
                if focus_concepts:
                    params["focus_concepts"] = focus_concepts[:2]
                _add_action(
                    actions_by_type,
                    action_type="quiz",
                    reason="还未进行测验，建议先做一次掌握度评估。",
                    params=params,
                    cta="开始测验",
                )
            elif avg_score < 0.65:
                params = {
                    "difficulty": "easy" if avg_score < 0.45 else practice_difficulty
                }
                if focus_concepts:
                    params["focus_concepts"] = focus_concepts[:2]
                _add_action(
                    actions_by_type,
                    action_type="quiz",
                    reason="最近测验得分偏低，建议做针对性练习。",
                    params=params,
                    cta="再练一次",
                    priority=88,
                )
            if qa_count == 0 and status != "ready_for_challenge":
                params = {"focus_concepts": focus_concepts[:1]} if focus_concepts else None
                _add_action(
                    actions_by_type,
                    action_type="qa",
                    reason="建议通过问答深化理解，并暴露知识盲点。",
                    params=params,
                    cta="去问答",
                )
            elif focus_concepts and avg_score < 0.75:
                _add_action(
                    actions_by_type,
                    action_type="qa",
                    reason="可针对薄弱点做定向问答，巩固理解。",
                    params={"focus_concepts": focus_concepts[:2]},
                    cta="定向问答",
                    priority=72,
                )

        if (
            has_keypoints
            and attempt_count >= 2
            and avg_score >= 0.82
            and (not mastery_values or stable_mastery_rate >= 0.7)
        ):
            challenge_params = {"difficulty": challenge_difficulty}
            if learning_focus_by_doc.get(doc_id):
                challenge_params["focus_concepts"] = _unique_nonempty(
                    learning_focus_by_doc[doc_id], limit=2
                )
            _add_action(
                actions_by_type,
                action_type="challenge",
                reason="该文档当前表现稳定，可尝试更高难度挑战。",
                params=challenge_params,
                cta="开始挑战",
            )

        if not actions_by_type:
            _add_action(
                actions_by_type,
                action_type="review",
                reason="当前进展平稳，建议按学习路径继续推进。",
                params={"focus_concepts": learning_focus_by_doc.get(doc_id, [])[:1]}
                if learning_focus_by_doc.get(doc_id)
                else None,
                cta="继续学习",
                priority=50,
            )

        actions = sorted(
            actions_by_type.values(),
            key=lambda action: (action.priority, ACTION_PRIORITY.get(action.type, 0)),
            reverse=True,
        )
        primary_action = actions[0] if actions else None

        item = RecommendationItem(
            doc_id=doc_id,
            doc_name=doc.filename,
            actions=actions,
            primary_action=primary_action,
            urgency_score=urgency_score,
            completion_score=completion_score,
            status=status,
            summary=_build_summary_text(status, focus_concepts),
        )
        ranked_items.append(
            (
                urgency_score,
                float(primary_action.priority if primary_action else 0),
                item,
            )
        )

    ranked_items.sort(key=lambda row: (row[0], row[1]), reverse=True)
    items = [row[2] for row in ranked_items[:limit]]

    next_step = None
    if items and items[0].primary_action:
        next_step = RecommendationNextStep(
            doc_id=items[0].doc_id,
            doc_name=items[0].doc_name,
            action=items[0].primary_action,
            reason=items[0].summary,
        )

    return RecommendationsResponse(
        kb_id=kb.id,
        kb_name=kb.name,
        items=items,
        learning_path=learning_path,
        learning_path_edges=learning_path_edges,
        learning_path_stages=learning_path_stages,
        learning_path_modules=learning_path_modules,
        learning_path_summary=learning_path_summary,
        next_step=next_step,
    )
