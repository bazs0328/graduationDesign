import re

from app.services.index_text_cleaning import clean_text_for_indexing


def test_clean_text_for_indexing_removes_pinyin_annotation_noise():
    raw_text = """家jiQ
中zhTng
需xO
要ySo
一yK
些xiE
圆yuWn
形xIng
的de
杯bEi
垫diSn
。我wG
们men
能nRng
制zhK
作zuH
圆yuWn
形xIng
杯bEi
垫diSn
吗ma
？"""

    cleaned = clean_text_for_indexing(raw_text)

    assert cleaned == "家中需要一些圆形的杯垫。我们能制作圆形杯垫吗？"
    assert re.search(r"[A-Za-z]", cleaned) is None


def test_clean_text_for_indexing_keeps_normal_chinese_text():
    raw_text = "这是普通中文段落。\n\n第二段也正常。"
    assert clean_text_for_indexing(raw_text) == raw_text


def test_clean_text_for_indexing_keeps_common_english_terms():
    raw_text = "我们用 Python 制作一个 AI 小程序，并连接 WiFi。"
    cleaned = clean_text_for_indexing(raw_text)
    assert "Python" in cleaned
    assert "AI" in cleaned
    assert "WiFi" in cleaned


def test_clean_text_for_indexing_removes_short_latin_noise_lines():
    raw_text = "bAo\nhM\nzhTng\n中文内容"
    assert clean_text_for_indexing(raw_text) == "中文内容"


def test_clean_text_for_indexing_does_not_clean_when_pair_ratio_is_low():
    raw_text = "我们学习拼音示例时提到家jiQ，但不应该触发全段清洗。"
    cleaned = clean_text_for_indexing(raw_text)
    assert "家jiQ" in cleaned
