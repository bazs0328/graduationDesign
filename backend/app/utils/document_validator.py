import mimetypes
import os
import re
from typing import ClassVar


class DocumentValidator:
    """Upload validation utilities (size, extension, safe filename)."""

    MAX_FILE_SIZE: ClassVar[int] = 50 * 1024 * 1024
    MAX_PDF_SIZE: ClassVar[int] = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".pdf", ".txt", ".md", ".docx", ".pptx"}
    ALLOWED_MIME_TYPES: ClassVar[set[str]] = {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    STRICT_MIME_EXTENSIONS: ClassVar[set[str]] = {".pdf", ".docx", ".pptx"}

    @staticmethod
    def validate_upload_safety(
        filename: str,
        file_size: int | None = None,
        allowed_extensions: set[str] | None = None,
        content_type: str | None = None,
    ) -> str:
        """Validate filename/extension and size; return safe filename."""
        safe_name = os.path.basename(filename)
        safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name)
        safe_name = re.sub(r"[<>:\"/\\|?*]", "_", safe_name)

        if not safe_name or safe_name in (".", "..") or safe_name.strip("_") == "":
            raise ValueError("Invalid filename")

        _, ext = os.path.splitext(safe_name.lower())
        exts_to_check = allowed_extensions or DocumentValidator.ALLOWED_EXTENSIONS
        if ext not in exts_to_check:
            raise ValueError(f"Unsupported file type: {ext}")

        if file_size is not None:
            if file_size > DocumentValidator.MAX_FILE_SIZE:
                raise ValueError("File too large")
            if ext == ".pdf" and file_size > DocumentValidator.MAX_PDF_SIZE:
                raise ValueError("PDF file too large")

        guessed_mime, _ = mimetypes.guess_type(safe_name)
        if guessed_mime and guessed_mime not in DocumentValidator.ALLOWED_MIME_TYPES:
            raise ValueError("MIME type validation failed")

        if content_type:
            if content_type not in DocumentValidator.ALLOWED_MIME_TYPES:
                if content_type != "application/octet-stream":
                    raise ValueError("MIME type validation failed")
            elif (
                ext in DocumentValidator.STRICT_MIME_EXTENSIONS
                and guessed_mime
                and content_type != guessed_mime
            ):
                raise ValueError("MIME type validation failed")

        return safe_name
