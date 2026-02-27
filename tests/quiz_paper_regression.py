#!/usr/bin/env python3
import argparse
import json
import re
import sys
import urllib.error
import urllib.request


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body or "{}")


def _normalize_stem(text: str) -> str:
    s = str(text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\W_]+", "", s)
    return s


def main():
    parser = argparse.ArgumentParser(description="Quiz paper regression checks")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--user-id", default="quiz_paper_reg")
    parser.add_argument("--doc-id", default=None)
    parser.add_argument("--kb-id", default=None)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--single", type=int, default=5)
    parser.add_argument("--multiple", type=int, default=2)
    parser.add_argument("--true-false", type=int, default=2)
    parser.add_argument("--fill-blank", type=int, default=1)
    parser.add_argument("--focus-concept", default=None)
    parser.add_argument("--max-duplicate-ratio", type=float, default=0.1)
    parser.add_argument("--min-focus-hit-ratio", type=float, default=0.7)
    args = parser.parse_args()

    if not args.doc_id and not args.kb_id:
        print("Either --doc-id or --kb-id is required", file=sys.stderr)
        return 2

    sections = [
        {
            "section_id": "single_choice_1",
            "type": "single_choice",
            "count": max(0, int(args.single)),
            "score_per_question": 1,
            "difficulty": "medium",
        },
        {
            "section_id": "multiple_choice_1",
            "type": "multiple_choice",
            "count": max(0, int(args.multiple)),
            "score_per_question": 1,
            "difficulty": "medium",
        },
        {
            "section_id": "true_false_1",
            "type": "true_false",
            "count": max(0, int(args.true_false)),
            "score_per_question": 1,
            "difficulty": "medium",
        },
        {
            "section_id": "fill_blank_1",
            "type": "fill_blank",
            "count": max(0, int(args.fill_blank)),
            "score_per_question": 1,
            "difficulty": "medium",
        },
    ]
    sections = [item for item in sections if item["count"] > 0]
    if not sections:
        print("No section count > 0", file=sys.stderr)
        return 2

    payload = {
        "user_id": args.user_id,
        "count": max(1, int(args.count)),
        "auto_adapt": False,
        "difficulty": "medium",
        "paper_blueprint": {
            "title": "Regression Mixed Paper",
            "duration_minutes": 20,
            "sections": sections,
        },
    }
    if args.doc_id:
        payload["doc_id"] = args.doc_id
    if args.kb_id:
        payload["kb_id"] = args.kb_id
    if args.focus_concept:
        payload["focus_concepts"] = [args.focus_concept]

    try:
        result = _post_json(f"{args.api_base}/api/quiz/generate", payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"Request failed: {exc}", file=sys.stderr)
        return 2

    questions = result.get("questions") or []
    if not isinstance(questions, list) or not questions:
        print("No questions returned", file=sys.stderr)
        return 2

    total = len(questions)
    type_counts: dict[str, int] = {}
    stems = [_normalize_stem(item.get("question")) for item in questions if isinstance(item, dict)]
    unique_stems = {s for s in stems if s}
    duplicate_ratio = 1.0 - (len(unique_stems) / max(1, len(stems)))

    for item in questions:
        if not isinstance(item, dict):
            continue
        qtype = str(item.get("type") or "single_choice")
        type_counts[qtype] = type_counts.get(qtype, 0) + 1

    focus_hit_ratio = None
    if args.focus_concept:
        focus_key = _normalize_stem(args.focus_concept)
        hit = 0
        for item in questions:
            if not isinstance(item, dict):
                continue
            concepts = item.get("concepts") or []
            text = " ".join([str(item.get("question") or ""), str(item.get("explanation") or "")])
            concept_hit = any(_normalize_stem(c) == focus_key for c in concepts)
            text_hit = focus_key in _normalize_stem(text)
            if concept_hit or text_hit:
                hit += 1
        focus_hit_ratio = hit / max(1, total)

    output = {
        "quiz_id": result.get("quiz_id"),
        "total": total,
        "type_counts": type_counts,
        "duplicate_ratio": round(duplicate_ratio, 4),
        "focus_hit_ratio": round(focus_hit_ratio, 4) if focus_hit_ratio is not None else None,
        "paper_meta": result.get("paper_meta") or {},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if duplicate_ratio > args.max_duplicate_ratio:
        return 2
    if focus_hit_ratio is not None and focus_hit_ratio < args.min_focus_hit_ratio:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
