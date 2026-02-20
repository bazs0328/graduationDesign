from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from app.services.parsers.base import ParseRequest
from app.services.parsers.router import ParserRouter


@dataclass
class ExtractionResult:
    text: str
    page_count: int
    pages: List[str]
    encoding: Optional[str] = None
    diagnostics: Optional[dict[str, Any]] = None
    parser_provider: Optional[str] = None
    extract_method: Optional[str] = None
    quality_score: Optional[float] = None


def extract_text(file_path: str, suffix: str) -> ExtractionResult:
    router = ParserRouter()
    result = router.parse(
        ParseRequest(
            file_path=file_path,
            suffix=suffix,
            mode="auto",
            parse_policy="balanced",
            preferred_parser="auto",
        )
    )

    return ExtractionResult(
        text=result.text,
        page_count=result.page_count,
        pages=result.pages,
        encoding=result.encoding,
        diagnostics=result.diagnostics,
        parser_provider=result.parser_provider,
        extract_method=result.extract_method,
        quality_score=result.quality_score,
    )
