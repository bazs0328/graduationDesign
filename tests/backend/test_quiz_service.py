"""Tests for quiz service quality guardrails."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.quiz import _apply_quality_guardrails, _build_context, generate_quiz


def test_quality_guardrails_filter_invalid_duplicates_and_concept_overload():
    raw_questions = [
        {
            "question": "什么是矩阵？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解释1",
            "concepts": ["矩阵"],
        },
        {
            "question": "什么是矩阵？ ",  # exact duplicate after normalization
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解释2",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵的定义是？",
            "options": ["A", "A", "C", "D"],  # invalid duplicate options
            "answer_index": 0,
            "explanation": "解释3",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵的秩表示什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 2,
            "explanation": "解释4",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵乘法满足什么条件？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 3,
            "explanation": "解释5",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵转置有什么性质？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解释6",
            "concepts": ["矩阵"],
        },
        {
            "question": "特征值的定义是什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解释7",
            "concepts": ["特征值"],
        },
    ]

    kept, report = _apply_quality_guardrails(
        raw_questions,
        target_count=5,
        focus_concepts=None,
    )

    assert len(kept) >= 3
    assert report["dropped_duplicate_exact"] >= 1
    assert report["dropped_invalid"] >= 1
    assert report["dropped_concept_overload"] >= 1
    assert any(q["question"] == "特征值的定义是什么？" for q in kept)


def test_quality_guardrails_filters_fragmented_stem_and_explanation():
    raw_questions = [
        {
            "question": "图\n中\n矩\n阵\n变\n换",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "正常解析",
            "concepts": ["矩阵变换"],
        },
        {
            "question": "矩阵的秩表示什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "秩\n是\n描\n述\n线\n性\n无\n关",
            "concepts": ["矩阵秩"],
        },
        {
            "question": "矩阵可逆的充要条件是什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 2,
            "explanation": "行列式不为零时矩阵可逆。",
            "concepts": ["矩阵可逆性"],
        },
    ]

    kept, report = _apply_quality_guardrails(raw_questions, target_count=5)

    assert len(kept) == 1
    assert kept[0]["question"] == "矩阵可逆的充要条件是什么？"
    assert report["dropped_invalid"] >= 2
    assert report["invalid_reasons"].get("fragmented_question", 0) >= 1
    assert report["invalid_reasons"].get("fragmented_explanation", 0) >= 1


def test_quality_guardrails_filters_focus_mismatch_questions():
    raw_questions = [
        {
            "question": "牛顿第二定律中，合力与加速度的关系是什么？",
            "options": ["成正比", "成反比", "无关", "无法判断"],
            "answer_index": 0,
            "explanation": "根据 F=ma，在质量一定时合力与加速度成正比。",
            "concepts": ["牛顿第二定律"],
        },
        {
            "question": "光合作用的主要产物是什么？",
            "options": ["氧气和葡萄糖", "二氧化碳", "氮气", "水"],
            "answer_index": 0,
            "explanation": "绿色植物通过光合作用生成有机物并释放氧气。",
            "concepts": ["光合作用"],
        },
    ]

    kept, report = _apply_quality_guardrails(
        raw_questions,
        target_count=5,
        focus_concepts=["牛顿第二定律"],
    )

    assert len(kept) == 1
    assert kept[0]["question"].startswith("牛顿第二定律")
    assert report["dropped_focus_mismatch"] >= 1


def test_generate_quiz_resamples_once_when_guardrails_reduce_count():
    first_round = [
        {
            "question": "题目1",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解析1",
            "concepts": ["概念A"],
        },
        {
            "question": "题目1",  # duplicate
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解析2",
            "concepts": ["概念A"],
        },
        {
            "question": "题目3",
            "options": ["A", "B", "C"],  # invalid options length
            "answer_index": 1,
            "explanation": "解析3",
            "concepts": ["概念B"],
        },
    ]
    second_round = [
        {
            "question": "题目2",
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解析2",
            "concepts": ["概念B"],
        },
        {
            "question": "题目3",
            "options": ["A", "B", "C", "D"],
            "answer_index": 2,
            "explanation": "解析3",
            "concepts": ["概念C"],
        },
    ]

    llm = Mock()
    llm.invoke.side_effect = [
        SimpleNamespace(content=json.dumps(first_round, ensure_ascii=False)),
        SimpleNamespace(content=json.dumps(second_round, ensure_ascii=False)),
    ]

    with (
        patch("app.services.quiz._build_context", return_value=("mock context", ["kp-1"])),
        patch("app.services.quiz.get_llm", return_value=llm),
    ):
        questions = generate_quiz(
            user_id="u1",
            doc_id=None,
            kb_id="kb-1",
            count=3,
            difficulty="medium",
        )

    assert len(questions) == 3
    assert llm.invoke.call_count == 2
    stems = [q["question"] for q in questions]
    assert stems == ["题目1", "题目2", "题目3"]
    assert all("keypoint_ids" not in q for q in questions)


def test_build_context_scales_k_with_question_count_and_caps_context_length():
    docs = [
        SimpleNamespace(
            page_content=(f"chunk-{idx} " + ("x" * 3000)),
            metadata={"keypoint_id": f"kp-{idx}"},
        )
        for idx in range(40)
    ]

    vectorstore = Mock()

    def _similarity_search(query, k, filter):
        assert filter == {"kb_id": "kb-1"}
        return docs[:k]

    vectorstore.similarity_search.side_effect = _similarity_search

    with patch("app.services.quiz.get_vectorstore", return_value=vectorstore):
        context, keypoint_ids = _build_context(
            user_id="u1",
            doc_id=None,
            kb_id="kb-1",
            reference_questions=None,
            focus_concepts=["概念A", "概念B"],
            target_count=10,
        )

    call_kwargs = vectorstore.similarity_search.call_args.kwargs
    assert call_kwargs["k"] > 6
    assert call_kwargs["k"] <= 24
    assert len(keypoint_ids) == call_kwargs["k"]
    assert len(context) <= 16000


def test_build_context_uses_per_focus_seed_search_when_multiple_focus_concepts():
    focus_a_doc = SimpleNamespace(
        page_content="牛顿第二定律相关内容",
        metadata={"keypoint_id": "kp-a", "doc_id": "doc-1", "chunk": 1, "page": 1},
    )
    focus_b_doc = SimpleNamespace(
        page_content="受力分析相关内容",
        metadata={"keypoint_id": "kp-b", "doc_id": "doc-1", "chunk": 2, "page": 1},
    )
    fallback_doc = SimpleNamespace(
        page_content="混合检索补充内容",
        metadata={"keypoint_id": "kp-c", "doc_id": "doc-1", "chunk": 3, "page": 1},
    )

    vectorstore = Mock()

    def _similarity_search(query, k, filter):
        assert filter == {"kb_id": "kb-1"}
        if query == "牛顿第二定律":
            return [focus_a_doc]
        if query == "受力分析":
            return [focus_b_doc]
        return [fallback_doc]

    vectorstore.similarity_search.side_effect = _similarity_search

    with (
        patch("app.services.quiz.get_vectorstore", return_value=vectorstore),
        patch("app.services.quiz.settings.quiz_context_reconstruct_enabled", False),
    ):
        context, keypoint_ids = _build_context(
            user_id="u1",
            doc_id=None,
            kb_id="kb-1",
            reference_questions=None,
            focus_concepts=["牛顿第二定律", "受力分析"],
            target_count=2,
        )

    queried = [call.kwargs["query"] if "query" in call.kwargs else call.args[0] for call in vectorstore.similarity_search.call_args_list]
    assert "牛顿第二定律" in queried
    assert "受力分析" in queried
    assert "牛顿第二定律相关内容" in context
    assert "受力分析相关内容" in context
    assert set(keypoint_ids) >= {"kp-a", "kp-b"}


def test_generate_quiz_attaches_image_for_figure_question_when_image_hit_exists():
    llm = Mock()
    llm.invoke.return_value = SimpleNamespace(
        content=json.dumps(
            [
                {
                    "question": "如图所示，矩阵变换后的图形关于哪个轴对称？",
                    "options": ["x轴", "y轴", "原点", "都不是"],
                    "answer_index": 1,
                    "explanation": "根据图形位置可判断关于 y 轴对称。",
                    "concepts": ["矩阵变换"],
                }
            ],
            ensure_ascii=False,
        )
    )
    image_hit_doc = SimpleNamespace(
        page_content="[图片块]\\n图注: 图1 变换示意图",
        metadata={
            "doc_id": "doc-1",
            "kb_id": "kb-1",
            "page": 2,
            "chunk": 8,
            "caption": "图1 变换示意图",
            "bbox": "[0,0,100,100]",
        },
    )

    with (
        patch("app.services.quiz._build_context", return_value=("mock context", ["kp-1"])),
        patch("app.services.quiz.get_llm", return_value=llm),
        patch("app.services.quiz.query_image_documents", return_value=[(image_hit_doc, 0.9)]),
    ):
        questions = generate_quiz(
            user_id="u1",
            doc_id="doc-1",
            kb_id=None,
            count=1,
            difficulty="medium",
        )

    assert len(questions) == 1
    image = questions[0].get("image")
    assert image
    assert image["url"] == "/api/docs/doc-1/image?page=2&chunk=8"
    assert image["caption"] == "图1 变换示意图"


def test_generate_quiz_reranks_image_hits_by_figure_caption_match():
    llm = Mock()
    llm.invoke.return_value = SimpleNamespace(
        content=json.dumps(
            [
                {
                    "question": "根据图1判断，图形经过变换后关于哪个轴对称？",
                    "options": ["x轴", "y轴", "原点", "都不是"],
                    "answer_index": 1,
                    "explanation": "图1中显示变换后的图形关于 y 轴对称。",
                    "concepts": ["矩阵变换"],
                }
            ],
            ensure_ascii=False,
        )
    )
    wrong_high_score = SimpleNamespace(
        page_content="[图片块]\n图注: 图2 错误示意图",
        metadata={
            "doc_id": "doc-1",
            "kb_id": "kb-1",
            "page": 2,
            "chunk": 7,
            "caption": "图2 错误示意图",
            "bbox": "[0,0,100,100]",
        },
    )
    right_lower_score = SimpleNamespace(
        page_content="[图片块]\n图注: 图1 关于y轴对称示意图",
        metadata={
            "doc_id": "doc-1",
            "kb_id": "kb-1",
            "page": 2,
            "chunk": 8,
            "caption": "图1 关于y轴对称示意图",
            "bbox": "[0,0,100,100]",
        },
    )

    with (
        patch("app.services.quiz._build_context", return_value=("mock context", ["kp-1"])),
        patch("app.services.quiz.get_llm", return_value=llm),
        patch(
            "app.services.quiz.query_image_documents",
            return_value=[(wrong_high_score, 0.92), (right_lower_score, 0.45)],
        ) as image_query_mock,
    ):
        questions = generate_quiz(
            user_id="u1",
            doc_id="doc-1",
            kb_id=None,
            count=1,
            difficulty="medium",
        )

    image = questions[0].get("image")
    assert image
    assert image["caption"] == "图1 关于y轴对称示意图"
    assert image_query_mock.call_args.kwargs["top_k"] >= 2
