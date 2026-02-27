"""Tests for adaptive QA prompt behavior."""

import json
import os

from langchain_core.documents import Document

from app.core.paths import ensure_kb_dirs, kb_base_dir
from app.services import qa as qa_service
from app.services.qa import (
    _strip_inline_source_markers,
    build_adaptive_system_prompt,
    build_explain_system_prompt,
    build_sources_and_context,
)


def test_adaptive_system_prompt_differs_by_ability_level():
    """Different ability levels should produce clearly different prompts."""
    beginner_prompt = build_adaptive_system_prompt(ability_level="beginner")
    advanced_prompt = build_adaptive_system_prompt(ability_level="advanced")

    assert beginner_prompt != advanced_prompt
    assert "初学者" in beginner_prompt
    assert "高水平学习者" in advanced_prompt


def test_adaptive_system_prompt_includes_weak_concepts():
    """Weak concepts should be included in system prompt hints."""
    prompt = build_adaptive_system_prompt(
        ability_level="intermediate",
        weak_concepts=["矩阵", "特征值"],
    )

    assert "薄弱知识点" in prompt
    assert "矩阵" in prompt
    assert "特征值" in prompt


def test_explain_system_prompt_requires_fixed_sections():
    prompt = build_explain_system_prompt(ability_level="intermediate")

    assert "讲解模式" in prompt
    assert "## 标题" in prompt
    assert "题意理解" in prompt
    assert "相关知识点" in prompt
    assert "分步解答" in prompt
    assert "易错点" in prompt
    assert "自测问题" in prompt


def test_strip_inline_source_markers_removes_citations_and_page_chunk_markers():
    raw = "答案如下[1][2]。见 p.19 c.177 与 p.3 c.12。"
    cleaned = _strip_inline_source_markers(raw)
    assert "[1]" not in cleaned and "[2]" not in cleaned
    assert "p.19 c.177" not in cleaned
    assert "p.3 c.12" not in cleaned
    assert "答案如下" in cleaned


def test_build_sources_and_context_uses_sidecar_summary_for_image_doc(monkeypatch, tmp_path):
    user_id = "qa_sidecar_user"
    kb_id = "qa_sidecar_kb"
    doc_id = "qa_sidecar_doc"
    monkeypatch.setattr(qa_service.settings, "data_dir", str(tmp_path))

    ensure_kb_dirs(user_id, kb_id)
    sidecar_path = os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": 1,
                "page_count": 1,
                "pages": [
                    {
                        "page": 1,
                        "ordered_blocks": [
                            {"block_id": "p1:t1", "kind": "text", "text": "上文介绍了线性变换。"},
                            {
                                "block_id": "p1:i1",
                                "kind": "image",
                                "caption_text": "图1 线性变换示意图",
                                "nearby_text": "该图展示了矩阵作用后的向量方向变化。",
                            },
                            {"block_id": "p1:t2", "kind": "text", "text": "下文给出矩阵表达式。"},
                        ],
                    }
                ],
                "chunk_manifest": [],
            },
            f,
            ensure_ascii=False,
        )

    docs = [
        Document(
            page_content="[图片块]\n邻近文字: 占位文本",
            metadata={
                "doc_id": doc_id,
                "kb_id": kb_id,
                "source": "sample.pdf",
                "page": 1,
                "modality": "image",
                "block_id": "p1:i1",
            },
        )
    ]

    sources, context = build_sources_and_context(docs, user_id=user_id)

    assert len(sources) == 1
    assert sources[0]["block_id"] == "p1:i1"
    assert "图注: 图1 线性变换示意图" in sources[0]["snippet"]
    assert "[图片块]" not in sources[0]["snippet"]
    assert "邻近正文" in context
