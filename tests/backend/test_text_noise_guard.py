from app.services.text_noise_guard import clean_fragment, infer_format_hint, is_low_quality


def test_noise_guard_detects_fragmented_noise_sample():
    raw = "shRn\n么\n第四单元\n使"
    cleaned = clean_fragment(raw, mode="balanced", format_hint=".pdf")
    assert is_low_quality(cleaned, mode="balanced", format_hint=".pdf") is True


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


def test_infer_format_hint_from_filename():
    assert infer_format_hint("notes.pptx") == ".pptx"
