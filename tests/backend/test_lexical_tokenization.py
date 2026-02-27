from pathlib import Path

from app.services import lexical_analyzer as analyzer


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _configure_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(analyzer.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(analyzer.settings, "lexical_stopwords_enabled", True)
    monkeypatch.setattr(
        analyzer.settings,
        "lexical_stopwords_global_path",
        str(tmp_path / "lexical" / "stopwords.txt"),
    )
    monkeypatch.setattr(
        analyzer.settings,
        "lexical_userdict_global_path",
        str(tmp_path / "lexical" / "userdict.txt"),
    )
    monkeypatch.setattr(
        analyzer.settings,
        "lexical_stopwords_kb_rel_path",
        "rag_storage/lexicon/stopwords.txt",
    )
    monkeypatch.setattr(
        analyzer.settings,
        "lexical_userdict_kb_rel_path",
        "rag_storage/lexicon/userdict.txt",
    )
    monkeypatch.setattr(analyzer.settings, "lexical_tokenizer_version", "v2")
    analyzer._ANALYZER_CACHE.clear()


def test_tokenize_for_index_uses_global_userdict(monkeypatch, tmp_path):
    _configure_defaults(monkeypatch, tmp_path)
    _write(tmp_path / "lexical" / "userdict.txt", "机器学习 100000 n\n")

    tokens = analyzer.tokenize_for_index("机器学习模型", user_id="u1", kb_id="kb1")

    assert "机器学习" in tokens
    assert "模型" in tokens


def test_tokenize_for_index_applies_global_and_kb_stopwords(monkeypatch, tmp_path):
    _configure_defaults(monkeypatch, tmp_path)
    _write(tmp_path / "lexical" / "stopwords.txt", "以及\n")
    _write(
        tmp_path / "users" / "u1" / "kb" / "kb1" / "rag_storage" / "lexicon" / "stopwords.txt",
        "矩阵\n",
    )

    tokens = analyzer.tokenize_for_index("我们学习矩阵以及向量空间", user_id="u1", kb_id="kb1")

    assert "矩阵" not in tokens
    assert "以及" not in tokens
    assert "向量" in tokens


def test_tokenize_for_query_falls_back_when_stopword_filter_removes_all(monkeypatch, tmp_path):
    _configure_defaults(monkeypatch, tmp_path)
    _write(tmp_path / "lexical" / "stopwords.txt", "我们\n")

    tokens = analyzer.tokenize_for_query("我们", user_id="u1", kb_id="kb1")

    assert tokens == ["我们"]


def test_tokenize_for_index_keeps_mixed_language_terms(monkeypatch, tmp_path):
    _configure_defaults(monkeypatch, tmp_path)

    tokens = analyzer.tokenize_for_index(
        "我们使用 Python 和 AI 进行 NLP 实验",
        user_id="u1",
        kb_id="kb1",
    )

    assert "python" in tokens
    assert "ai" in tokens
    assert "nlp" in tokens


def test_analyzer_cache_rebuilds_when_stopword_file_changes(monkeypatch, tmp_path):
    _configure_defaults(monkeypatch, tmp_path)
    stopwords_path = tmp_path / "lexical" / "stopwords.txt"
    _write(stopwords_path, "向量\n")

    tokens_v1 = analyzer.tokenize_for_index("向量 空间", user_id="u1", kb_id="kb1")
    assert "向量" not in tokens_v1

    _write(stopwords_path, "空间\n额外\n")
    tokens_v2 = analyzer.tokenize_for_index("向量 空间", user_id="u1", kb_id="kb1")
    assert "向量" in tokens_v2
    assert "空间" not in tokens_v2

