from app.services.parsers.native_pdf_parser import _clean_page, _page_quality


def test_page_quality_detects_garbled_tokens_and_spacing():
    text = "zDn ySng xuR kE xuR\n科 学 家 是 怎 样 研 究 问 题 的"
    score, flags = _page_quality(text, min_text_length=10)
    assert score < 70
    assert "han_spaced" in flags or "weird_tokens" in flags


def test_clean_page_merges_cjk_spacing():
    text = "科 学 家 在 研 究"
    cleaned = _clean_page(text, ["han_spaced"])
    assert "科学家在研究" in cleaned


def test_page_quality_prefers_clean_chinese():
    text = "科学家是怎样研究问题的？我们怎样像科学家那样学习科学？"
    score, flags = _page_quality(text, min_text_length=10)
    assert score >= 80
    assert "han_spaced" not in flags
