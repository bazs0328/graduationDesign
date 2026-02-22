from app.utils.document_validator import DocumentValidator


def test_validate_upload_safety_accepts_docx_and_pptx():
    docx_name = DocumentValidator.validate_upload_safety(
        "notes.docx",
        file_size=1024,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    pptx_name = DocumentValidator.validate_upload_safety(
        "slides.pptx",
        file_size=2048,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    assert docx_name == "notes.docx"
    assert pptx_name == "slides.pptx"


def test_validate_upload_safety_rejects_legacy_office_formats():
    for filename, content_type in (
        ("legacy.doc", "application/msword"),
        ("legacy.ppt", "application/vnd.ms-powerpoint"),
    ):
        try:
            DocumentValidator.validate_upload_safety(
                filename,
                file_size=512,
                content_type=content_type,
            )
        except ValueError as exc:
            assert "Unsupported file type" in str(exc)
        else:
            raise AssertionError(f"{filename} should be rejected")


def test_validate_upload_safety_rejects_docx_mime_mismatch():
    try:
        DocumentValidator.validate_upload_safety(
            "notes.docx",
            file_size=1024,
            content_type="text/plain",
        )
    except ValueError as exc:
        assert "MIME type validation failed" in str(exc)
    else:
        raise AssertionError("MIME mismatch should be rejected")


def test_validate_upload_safety_accepts_octet_stream_for_docx():
    safe_name = DocumentValidator.validate_upload_safety(
        "notes.docx",
        file_size=1024,
        content_type="application/octet-stream",
    )
    assert safe_name == "notes.docx"
