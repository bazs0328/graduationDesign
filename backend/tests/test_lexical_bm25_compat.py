import json
from pathlib import Path

from app.services import lexical as lexical_service
from app.services import lexical_analyzer as analyzer
from app.services.lexical import bm25_search


def _lexical_file(tmp_path: Path, user_id: str, kb_id: str) -> Path:
    path = tmp_path / "users" / user_id / "lexical" / f"{kb_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_entries(path: Path, entries: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )


def _configure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(lexical_service.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(lexical_service.settings, "lexical_stopwords_enabled", True)
    monkeypatch.setattr(lexical_service.settings, "lexical_tokenizer_version", "v2")
    monkeypatch.setattr(analyzer.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(analyzer.settings, "lexical_stopwords_enabled", True)
    monkeypatch.setattr(analyzer.settings, "lexical_tokenizer_version", "v2")
    analyzer._ANALYZER_CACHE.clear()


def test_bm25_search_supports_legacy_entries_without_tokens(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    path = _lexical_file(tmp_path, user_id="u1", kb_id="kb1")
    _write_entries(
        path,
        [
            {
                "text": "矩阵分解用于求解线性方程组",
                "metadata": {"doc_id": "legacy-doc", "kb_id": "kb1", "source": "a.txt"},
            }
        ],
    )

    results = bm25_search("u1", "kb1", "矩阵分解", top_k=1)

    assert len(results) == 1
    assert results[0][0].metadata.get("doc_id") == "legacy-doc"


def test_bm25_search_prefers_stored_tokens_when_version_matches(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    path = _lexical_file(tmp_path, user_id="u1", kb_id="kb1")
    _write_entries(
        path,
        [
            {
                "text": "这一段文本本身没有关键词",
                "metadata": {"doc_id": "doc-new", "kb_id": "kb1", "source": "b.txt"},
                "tokens": ["特征值", "分解"],
                "tokenizer_version": "v2",
            },
            {
                "text": "无关内容",
                "metadata": {"doc_id": "doc-other", "kb_id": "kb1", "source": "c.txt"},
                "tokens": ["无关", "内容"],
                "tokenizer_version": "v2",
            },
        ],
    )

    results = bm25_search("u1", "kb1", "特征值 分解", top_k=1)

    assert len(results) == 1
    assert results[0][0].metadata.get("doc_id") == "doc-new"


def test_bm25_search_refalls_to_text_when_tokenizer_version_mismatch(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    path = _lexical_file(tmp_path, user_id="u1", kb_id="kb1")
    _write_entries(
        path,
        [
            {
                "text": "向量空间理论强调基与维度",
                "metadata": {"doc_id": "doc-stale", "kb_id": "kb1", "source": "d.txt"},
                "tokens": ["噪声词"],
                "tokenizer_version": "v1",
            }
        ],
    )

    results = bm25_search("u1", "kb1", "向量 空间", top_k=1)

    assert len(results) == 1
    assert results[0][0].metadata.get("doc_id") == "doc-stale"

