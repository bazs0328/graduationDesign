from app.services.text_noise_guard import clean_fragment, infer_format_hint, is_low_quality


def test_noise_guard_detects_fragmented_noise_sample():
    raw = "shRn\n么\n第四单元\n使"
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".pdf")
    assert is_low_quality(cleaned, mode="balanced", format_hint=".pdf") is True


def test_noise_guard_common_normalization_nfkc_and_invisible_chars():
    raw = "ＡＩ\u200b 学习\x00\n\n"
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".txt")
    assert cleaned == "AI 学习"


def test_noise_guard_normalizes_chinese_context_punctuation():
    raw = "这是中文, 句子! 还有问题? 结束."
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".txt")
    assert cleaned == "这是中文，句子！还有问题？结束。"


def test_noise_guard_repairs_hard_line_breaks_and_hyphenation():
    raw = "This is an exam-\nple sentence.\n下一行，\n继续。"
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".txt")
    assert "example sentence." in cleaned
    assert "下一行，继续。" in cleaned


def test_noise_guard_keeps_markdown_code_block_in_structure_preserving_mode():
    raw = """# 标题

```python
print("hello")
```

正文段落。"""
    cleaned = clean_fragment(raw, mode="structure_preserving", format_hint=".md")
    assert 'print("hello")' in cleaned
    assert "正文段落" in cleaned


def test_noise_guard_removes_short_latin_noise_lines():
    raw = "bAo\nhM\nzhTng\n中文内容"
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".txt")
    assert cleaned == "中文内容"


def test_noise_guard_removes_suspicious_latin_noise_lines_but_keeps_safe_terms():
    raw = """人民教育出版社
daikocicn
z.nyong
Python
AI
DNA
WiFi
作用"""
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".pdf")
    assert "daikocicn" not in cleaned
    assert "z.nyong" not in cleaned
    assert "Python" in cleaned
    assert "AI" in cleaned
    assert "DNA" in cleaned
    assert "WiFi" in cleaned


def test_infer_format_hint_from_filename():
    assert infer_format_hint("notes.pptx") == ".pptx"
