import logging
import time
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
from app.services.learner_profile import (
    get_or_create_profile,
    get_weak_concepts_for_kb,
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
    include_learning_path: bool = True,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    total_started = time.perf_counter()
    docs_query_ms = 0
    counts_query_ms = 0
    learning_path_ms = 0
    rank_ms = 0

    limit = max(1, min(limit, 20))
    profile = get_or_create_profile(db, resolved_user_id)
    profile_weak_concepts = get_weak_concepts_for_kb(db, resolved_user_id, kb.id)
    practice_difficulty = PRACTICE_DIFFICULTY_BY_ABILITY.get(
        profile.ability_level, "medium"
    )
    challenge_difficulty = CHALLENGE_DIFFICULTY_BY_ABILITY.get(
        profile.ability_level, "hard"
    )

    docs_started = time.perf_counter()
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
    docs_query_ms = int((time.perf_counter() - docs_started) * 1000)
    if not docs:
        total_ms = int((time.perf_counter() - total_started) * 1000)
        logger.info(
            "Recommendations timing user_id=%s kb_id=%s total_ms=%d docs_query_ms=%d counts_query_ms=%d learning_path_ms=%d rank_ms=%d items_count=%d learning_path_items_count=%d",
            resolved_user_id,
            kb.id,
            total_ms,
            docs_query_ms,
            counts_query_ms,
            learning_path_ms,
            rank_ms,
            0,
            0,
        )
        return RecommendationsResponse(kb_id=kb.id, kb_name=kb.name, items=[])

    doc_ids = [doc.id for doc in docs]

    counts_started = time.perf_counter()
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

    keypoint_best_by_doc: dict[str, dict[str, dict]] = defaultdict(dict)
    keypoint_rows = (
        db.query(
            Keypoint.doc_id,
            Keypoint.text,
            Keypoint.mastery_level,
            Keypoint.attempt_count,
        )
        .filter(
            Keypoint.user_id == resolved_user_id,
            Keypoint.doc_id.in_(doc_ids),
        )
        .all()
    )
    for row in keypoint_rows:
        source_doc_id = str(row[0] or "")
        text = str(row[1] or "").strip()
        if not source_doc_id or not text:
            continue
        mastery_level = float(row[2] or 0.0)
        attempt_count = int(row[3] or 0)
        existing = keypoint_best_by_doc[source_doc_id].get(text)
        if existing is None:
            keypoint_best_by_doc[source_doc_id][text] = {
                "text": text,
                "mastery_level": mastery_level,
                "attempt_count": attempt_count,
            }
            continue
        if mastery_level < float(existing["mastery_level"]):
            keypoint_best_by_doc[source_doc_id][text] = {
                "text": text,
                "mastery_level": mastery_level,
                "attempt_count": attempt_count,
            }
            continue
        if (
            mastery_level == float(existing["mastery_level"])
            and attempt_count > int(existing["attempt_count"])
        ):
            keypoint_best_by_doc[source_doc_id][text] = {
                "text": text,
                "mastery_level": mastery_level,
                "attempt_count": attempt_count,
            }
    keypoints_by_doc = {
        source_doc_id: list(concept_map.values())
        for source_doc_id, concept_map in keypoint_best_by_doc.items()
    }
    counts_query_ms = int((time.perf_counter() - counts_started) * 1000)

    learning_path_started = time.perf_counter()
    if include_learning_path:
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
    else:
        learning_path, learning_path_edges = [], []
        learning_path_stages, learning_path_modules, learning_path_summary = [], [], {}
    learning_path_ms = int((time.perf_counter() - learning_path_started) * 1000)

    rank_started = time.perf_counter()
    learning_path_text_by_id: dict[str, str] = {}
    blocked_concepts: set[str] = set()
    blocked_unmet_prereqs_by_text: dict[str, list[str]] = {}
    if learning_path:
        concept_unlock_state: dict[str, bool] = {}
        blocked_unmet_prereq_ids_by_text: dict[str, set[str]] = {}
        for path_item in learning_path:
            path_keypoint_id = str(path_item.keypoint_id or "").strip()
            path_text = str(path_item.text or "").strip()
            if path_keypoint_id and path_text:
                learning_path_text_by_id[path_keypoint_id] = path_text
            if not path_text:
                continue

            is_unlocked = bool(path_item.is_unlocked)
            previous_state = concept_unlock_state.get(path_text)
            if previous_state is None:
                concept_unlock_state[path_text] = is_unlocked
            elif is_unlocked:
                # Keep concept actionable as long as one merged source is unlocked.
                concept_unlock_state[path_text] = True

            if not is_unlocked:
                unmet_ids = [
                    str(prereq_id or "").strip()
                    for prereq_id in (path_item.unmet_prerequisite_ids or [])
                    if str(prereq_id or "").strip()
                ]
                if unmet_ids:
                    blocked_unmet_prereq_ids_by_text.setdefault(path_text, set()).update(
                        unmet_ids
                    )

        blocked_concepts = {
            concept for concept, unlocked in concept_unlock_state.items() if not unlocked
        }
        for concept, unmet_ids in blocked_unmet_prereq_ids_by_text.items():
            blocked_unmet_prereqs_by_text[concept] = _unique_nonempty(
                [learning_path_text_by_id.get(prereq_id, "") for prereq_id in sorted(unmet_ids)],
                limit=max(3, len(unmet_ids)),
            )

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
            if is_weak_mastery(item["mastery_level"])
            and item["text"]
            and not (
                int(item.get("attempt_count", 0) or 0) == 0
                and float(item.get("mastery_level", 0.0) or 0.0) <= 0.0
            )
        ]

        blocked_weak_prereqs: list[str] = []
        if blocked_concepts and weak_keypoints:
            actionable_weak_keypoints: list[dict[str, float | int | str]] = []
            for weak_item in weak_keypoints:
                weak_text = str(weak_item.get("text") or "").strip()
                if not weak_text:
                    continue
                if weak_text in blocked_concepts:
                    blocked_weak_prereqs.extend(
                        blocked_unmet_prereqs_by_text.get(weak_text, [])
                    )
                    continue
                actionable_weak_keypoints.append(weak_item)
            weak_keypoints = actionable_weak_keypoints

        filtered_profile_weak_concepts = [
            concept
            for concept in profile_weak_concepts
            if str(concept or "").strip() not in blocked_concepts
        ]
        focus_concepts = _unique_nonempty(
            [item["text"] for item in weak_keypoints] + filtered_profile_weak_concepts,
            limit=3,
        )
        if not focus_concepts and blocked_weak_prereqs:
            focus_concepts = _unique_nonempty(
                blocked_weak_prereqs + filtered_profile_weak_concepts,
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
        # Keep recommendation completion aligned with profile completion:
        # both use weighted mastery completion (mastered=1.0, partial=0.5).
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
                    # For first-time calibration, keep quiz above review to match ready_for_practice guidance.
                    priority=86,
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
                reason="当前进展平稳，建议继续复习巩固。",
                params={"focus_concepts": focus_concepts[:1]} if focus_concepts else None,
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

    rank_ms = int((time.perf_counter() - rank_started) * 1000)
    total_ms = int((time.perf_counter() - total_started) * 1000)
    logger.info(
        "Recommendations timing user_id=%s kb_id=%s total_ms=%d docs_query_ms=%d counts_query_ms=%d learning_path_ms=%d rank_ms=%d items_count=%d learning_path_items_count=%d",
        resolved_user_id,
        kb.id,
        total_ms,
        docs_query_ms,
        counts_query_ms,
        learning_path_ms,
        rank_ms,
        len(items),
        len(learning_path),
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
