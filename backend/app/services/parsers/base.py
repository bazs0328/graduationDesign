from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ParseRequest:
    file_path: str
    suffix: str
    mode: str = "auto"  # auto|force_ocr|text_layer|parser_auto
    parse_policy: str = "balanced"  # stable|balanced|aggressive
    preferred_parser: str = "auto"  # auto|native|docling


@dataclass(slots=True)
class PageDiagnostic:
    page_num: int
    char_count: int
    quality_score: float
    flags: list[str] = field(default_factory=list)
    method: str = "text_layer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page_num,
            "chars": self.char_count,
            "quality_score": round(float(self.quality_score), 2),
            "flags": list(self.flags),
            "method": self.method,
        }


@dataclass(slots=True)
class ParseResult:
    text: str
    page_count: int
    pages: list[str]
    parser_provider: str
    extract_method: str
    quality_score: Optional[float] = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    timing_ms: dict[str, float] = field(default_factory=dict)
    encoding: Optional[str] = None
