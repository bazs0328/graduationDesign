import json
import re


def extract_json_block(text: str) -> str:
    # Find first JSON array or object block
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        return array_match.group(0)
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        return obj_match.group(0)
    raise ValueError("No JSON block found")


def safe_json_loads(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = extract_json_block(text)
        return json.loads(cleaned)
