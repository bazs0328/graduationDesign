#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
USER_ID="${SMOKE_USER_ID:-smoke}"
DOC_FILE="${SMOKE_DOC_FILE:-/tmp/smoke_doc.txt}"

log() {
  echo "[smoke] $*"
}

fail() {
  echo "[smoke] ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_cmd curl
require_cmd python3

log "API base: ${API_BASE}"

log "Checking health..."
health=$(curl -sS "${API_BASE}/api/health" || true)
if [[ "$health" != *"ok"* ]]; then
  fail "Health check failed: ${health}"
fi

AUTH_USERNAME="${SMOKE_AUTH_USERNAME:-smoke_auth_user}"
AUTH_PASSWORD="${SMOKE_AUTH_PASSWORD:-smoke_pass}"

log "Auth: register..."
register_resp=$(curl -sS -w "\n%{http_code}" -H "Content-Type: application/json" \
  -d "{\"username\":\"${AUTH_USERNAME}\",\"password\":\"${AUTH_PASSWORD}\",\"name\":\"Smoke Auth\"}" \
  "${API_BASE}/api/auth/register" 2>/dev/null || true)
register_code=$(echo "$register_resp" | tail -1)
register_body=$(echo "$register_resp" | sed '$d')

if [[ "$register_code" == "200" || "$register_code" == "201" ]]; then
  AUTH_USER_ID=$(REGISTER_BODY="${register_body}" python3 - <<'PY'
import json, os
data = os.environ.get("REGISTER_BODY", "{}")
try:
    obj = json.loads(data)
    print(obj.get("user_id", ""))
except Exception:
    print("")
PY
)
  if [[ -z "$AUTH_USER_ID" ]]; then
    fail "Auth register response missing user_id: ${register_body}"
  fi
  log "Auth: registered user_id=${AUTH_USER_ID}"
elif [[ "$register_code" == "409" ]]; then
  log "Auth: user already exists, logging in..."
  login_resp=$(curl -sS -H "Content-Type: application/json" \
    -d "{\"username\":\"${AUTH_USERNAME}\",\"password\":\"${AUTH_PASSWORD}\"}" \
    "${API_BASE}/api/auth/login" 2>/dev/null || true)
  if [[ "$login_resp" == *"detail"* ]] && [[ "$login_resp" != *"user_id"* ]]; then
    fail "Auth login failed: ${login_resp}"
  fi
  AUTH_USER_ID=$(LOGIN_BODY="${login_resp}" python3 - <<'PY'
import json, os
data = os.environ.get("LOGIN_BODY", "{}")
try:
    obj = json.loads(data)
    print(obj.get("user_id", ""))
except Exception:
    print("")
PY
)
  if [[ -z "$AUTH_USER_ID" ]]; then
    fail "Auth login response missing user_id: ${login_resp}"
  fi
  log "Auth: logged in user_id=${AUTH_USER_ID}"
else
  fail "Auth register unexpected: ${register_code} ${register_body}"
fi

log "Auth: GET /me..."
me_resp=$(curl -sS "${API_BASE}/api/auth/me?user_id=${AUTH_USER_ID}" || true)
if [[ "$me_resp" == *"detail"* ]] && [[ "$me_resp" != *"user_id"* ]]; then
  fail "Auth me failed: ${me_resp}"
fi
me_ok=$(ME_BODY="${me_resp}" AUTH_USER_ID="${AUTH_USER_ID}" python3 - <<'PY'
import json, os
data = os.environ.get("ME_BODY", "{}")
uid = os.environ.get("AUTH_USER_ID", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
if obj.get("user_id") != uid:
    print("user_id_mismatch")
    raise SystemExit(0)
if "username" not in obj:
    print("missing_username")
    raise SystemExit(0)
print("ok")
PY
)
if [[ "$me_ok" != "ok" ]]; then
  fail "Auth me malformed: ${me_resp}"
fi
log "Auth: me OK"

log "Preparing smoke document..."
cat <<'DOC' > "${DOC_FILE}"
Linear algebra studies vectors, matrices, and linear transformations.
A matrix is a rectangular array of numbers. The determinant can indicate whether a matrix is invertible.
Eigenvalues and eigenvectors reveal important properties of linear transformations.
DOC

log "Uploading document..."
upload_json=$(curl -sS -F "file=@${DOC_FILE}" -F "user_id=${USER_ID}" "${API_BASE}/api/docs/upload" || true)
doc_id=""
if [[ "$upload_json" == *"Duplicate document already uploaded"* ]]; then
  log "Duplicate detected; reusing existing document."
  docs_json=$(curl -sS "${API_BASE}/api/docs?user_id=${USER_ID}" || true)
  doc_id=$(UPLOAD_JSON="${docs_json}" DOC_NAME="$(basename "${DOC_FILE}")" python3 - <<'PY'
import json, os
data = os.environ.get("UPLOAD_JSON", "")
name = os.environ.get("DOC_NAME", "")
doc_id = ""
try:
    items = json.loads(data)
    if isinstance(items, list):
        for item in items:
            if item.get("filename") == name:
                doc_id = item.get("id", "")
                break
        if not doc_id and items:
            doc_id = items[0].get("id", "")
except Exception:
    doc_id = ""
print(doc_id)
PY
  )
elif [[ "$upload_json" == *"detail"* ]]; then
  fail "Upload failed: ${upload_json}"
else
  doc_id=$(UPLOAD_JSON="${upload_json}" python3 - <<'PY'
import json, os
data = os.environ.get("UPLOAD_JSON", "")
doc_id = ""
try:
    obj = json.loads(data)
    doc_id = obj.get("id", "")
except Exception:
    doc_id = ""
print(doc_id)
PY
  )
fi

if [[ -z "$doc_id" ]]; then
  fail "Upload did not return doc_id: ${upload_json}"
fi
log "doc_id=${doc_id}"

log "Waiting for document to be ready..."
ready_status=$(DOC_ID="${doc_id}" USER_ID="${USER_ID}" API_BASE="${API_BASE}" python3 - <<'PY'
import json
import os
import time
import urllib.request

doc_id = os.environ.get("DOC_ID")
user_id = os.environ.get("USER_ID")
api_base = os.environ.get("API_BASE")

status = ""
error_message = ""
for _ in range(30):
    try:
        with urllib.request.urlopen(f"{api_base}/api/docs?user_id={user_id}") as resp:
            docs = json.load(resp)
    except Exception:
        docs = []
    for doc in docs:
        if doc.get("id") == doc_id:
            status = doc.get("status") or ""
            error_message = doc.get("error_message") or ""
            break
    if status == "ready":
        print("ready")
        raise SystemExit(0)
    if status == "error":
        print(f"error:{error_message}")
        raise SystemExit(0)
    time.sleep(2)

print(f"timeout:{status}")
PY
)

if [[ "$ready_status" == "ready" ]]; then
  log "Document is ready."
elif [[ "$ready_status" == error:* ]]; then
  fail "Document processing failed: ${ready_status#error:}"
else
  fail "Document did not become ready in time: ${ready_status#timeout:}"
fi

log "Generating summary..."
summary_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\"}" \
  "${API_BASE}/api/summary" || true)
if [[ "$summary_json" == *"detail"* ]]; then
  fail "Summary failed: ${summary_json}"
fi
summary_ok=$(SUMMARY_JSON="${summary_json}" python3 - <<'PY'
import json, os
data = os.environ.get("SUMMARY_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)

summary = obj.get("summary")
if isinstance(summary, str) and summary.strip():
    print("ok")
else:
    print("missing_summary")
PY
)
if [[ "$summary_ok" != "ok" ]]; then
  fail "Summary malformed: ${summary_json}"
fi

log "Generating keypoints..."
keypoints_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\"}" \
  "${API_BASE}/api/keypoints" || true)
if [[ "$keypoints_json" == *"detail"* ]]; then
  fail "Keypoints failed: ${keypoints_json}"
fi
keypoints_ok=$(KEYPOINTS_JSON="${keypoints_json}" python3 - <<'PY'
import json, os
data = os.environ.get("KEYPOINTS_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)

points = obj.get("keypoints")
if not isinstance(points, list) or not points:
    print("missing_keypoints")
else:
    def has_text(p):
        if isinstance(p, str):
            return bool(p.strip())
        if isinstance(p, dict):
            return bool((p.get("text") or "").strip())
        return False
    valid = all(has_text(p) for p in points)
    print("ok" if valid else "missing_keypoints")
PY
)
if [[ "$keypoints_ok" != "ok" ]]; then
  fail "Keypoints malformed: ${keypoints_json}"
fi

log "Asking QA..."
qa_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"question\":\"What is a matrix?\"}" \
  "${API_BASE}/api/qa" || true)
if [[ "$qa_json" == *"detail"* || "$qa_json" == "Internal Server Error" ]]; then
  fail "QA failed: ${qa_json}"
fi
qa_ok=$(QA_JSON="${qa_json}" python3 - <<'PY'
import json, os
data = os.environ.get("QA_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)

answer = obj.get("answer")
sources = obj.get("sources")
if isinstance(answer, str) and answer.strip() and isinstance(sources, list) and len(sources) > 0:
    print("ok")
else:
    print("missing_answer_or_sources")
PY
)
if [[ "$qa_ok" != "ok" ]]; then
  fail "QA malformed: ${qa_json}"
fi

log "Generating quiz..."
quiz_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"count\":4,\"difficulty\":\"medium\",\"auto_adapt\":false,\"paper_blueprint\":{\"title\":\"Smoke Mixed Paper\",\"duration_minutes\":20,\"sections\":[{\"section_id\":\"single_choice_1\",\"type\":\"single_choice\",\"count\":1,\"score_per_question\":1,\"difficulty\":\"easy\"},{\"section_id\":\"multiple_choice_1\",\"type\":\"multiple_choice\",\"count\":1,\"score_per_question\":1,\"difficulty\":\"easy\"},{\"section_id\":\"true_false_1\",\"type\":\"true_false\",\"count\":1,\"score_per_question\":1,\"difficulty\":\"easy\"},{\"section_id\":\"fill_blank_1\",\"type\":\"fill_blank\",\"count\":1,\"score_per_question\":1,\"difficulty\":\"easy\"}]}}" \
  "${API_BASE}/api/quiz/generate" || true)
if [[ "$quiz_json" == *"detail"* ]]; then
  fail "Quiz generation failed: ${quiz_json}"
fi

quiz_id=$(python3 - <<PY
import json,sys
try:
    obj=json.loads('''${quiz_json}''')
    print(obj.get('quiz_id',''))
except Exception:
    print('')
PY
)

if [[ -z "$quiz_id" ]]; then
  fail "Quiz generation did not return quiz_id: ${quiz_json}"
fi
log "quiz_id=${quiz_id}"
quiz_ok=$(QUIZ_JSON="${quiz_json}" python3 - <<'PY'
import json, os
data = os.environ.get("QUIZ_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
questions = obj.get("questions")
if not isinstance(questions, list) or not questions:
    print("missing_questions")
    raise SystemExit(0)
for q in questions:
    if not isinstance(q, dict):
        print("invalid_question")
        raise SystemExit(0)
    if not str(q.get("question_id") or "").strip():
        print("missing_question_id")
        raise SystemExit(0)
    qtype = str(q.get("type") or "")
    if qtype not in {"single_choice", "multiple_choice", "true_false", "fill_blank"}:
        print("invalid_type")
        raise SystemExit(0)
    if qtype in {"single_choice", "multiple_choice"}:
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            print("invalid_options")
            raise SystemExit(0)
    if qtype == "true_false":
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) < 2:
            print("invalid_true_false_options")
            raise SystemExit(0)
    if qtype == "fill_blank":
        blanks = q.get("answer_blanks") or q.get("answer")
        if not isinstance(blanks, list) or len(blanks) == 0:
            print("invalid_fill_blank_answer")
            raise SystemExit(0)
    if "score" not in q or "section_id" not in q:
        print("missing_paper_fields")
        raise SystemExit(0)
print("ok")
PY
)
if [[ "$quiz_ok" != "ok" ]]; then
  fail "Quiz malformed: ${quiz_json}"
fi

log "Submitting quiz..."
submit_payload=$(QUIZ_JSON="${quiz_json}" QUIZ_ID="${quiz_id}" USER_ID="${USER_ID}" python3 - <<'PY'
import json, os
quiz = json.loads(os.environ.get("QUIZ_JSON", "{}"))
quiz_id = os.environ.get("QUIZ_ID", "")
user_id = os.environ.get("USER_ID", "")
answers = []
for idx, q in enumerate(quiz.get("questions") or []):
    qid = str(q.get("question_id") or f"q-{idx+1}")
    qtype = str(q.get("type") or "single_choice")
    if qtype == "multiple_choice":
        value = q.get("answer_indexes") or q.get("answer") or []
    elif qtype == "true_false":
        value = q.get("answer_bool")
        if value is None:
            value = bool(q.get("answer"))
    elif qtype == "fill_blank":
        value = q.get("answer_blanks") or q.get("answer") or []
    else:
        value = q.get("answer_index")
        if value is None:
            value = q.get("answer")
    answers.append({"question_id": qid, "answer": value})
print(json.dumps({"quiz_id": quiz_id, "user_id": user_id, "answers": answers}, ensure_ascii=False))
PY
)

submit_json=$(curl -sS -H "Content-Type: application/json" \
  -d "${submit_payload}" \
  "${API_BASE}/api/quiz/submit" || true)
if [[ "$submit_json" == *"detail"* ]]; then
  fail "Quiz submit failed: ${submit_json}"
fi

log "Quiz mimic (style_prompt)..."
mimic_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"count\":2,\"difficulty\":\"medium\",\"style_prompt\":\"Exam-style multiple choice.\"}" \
  "${API_BASE}/api/quiz/generate" || true)
if [[ "$mimic_json" == *"detail"* ]]; then
  fail "Quiz mimic (style_prompt) failed: ${mimic_json}"
fi
mimic_quiz_id=$(python3 - <<PY
import json,sys
try:
    obj=json.loads('''${mimic_json}''')
    print(obj.get('quiz_id',''))
except Exception:
    print('')
PY
)
if [[ -z "$mimic_quiz_id" ]]; then
  fail "Quiz mimic did not return quiz_id: ${mimic_json}"
fi
log "mimic quiz_id=${mimic_quiz_id}"

log "Quiz parse-reference (reject non-PDF)..."
parse_ref_resp=$(curl -sS -w "\n%{http_code}" -X POST \
  -F "file=@${DOC_FILE};filename=ref.txt" \
  "${API_BASE}/api/quiz/parse-reference" 2>/dev/null || true)
parse_ref_code=$(echo "$parse_ref_resp" | tail -1)
if [[ "$parse_ref_code" != "400" ]]; then
  fail "parse-reference should reject non-PDF with 400, got: ${parse_ref_code}"
fi
log "parse-reference correctly rejected non-PDF (400)"

log "Fetching progress..."
progress_json=$(curl -sS "${API_BASE}/api/progress?user_id=${USER_ID}" || true)
if [[ "$progress_json" == *"detail"* ]]; then
  fail "Progress failed: ${progress_json}"
fi

log "Fetching profile..."
profile_json=$(curl -sS "${API_BASE}/api/profile?user_id=${USER_ID}" || true)
if [[ "$profile_json" == *"detail"* ]]; then
  fail "Profile failed: ${profile_json}"
fi
profile_ok=$(PROFILE_JSON="${profile_json}" python3 - <<'PY'
import json, os
data = os.environ.get("PROFILE_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
required = ("ability_level", "recent_accuracy", "frustration_score", "weak_concepts", "theta", "total_attempts")
for k in required:
    if k not in obj:
        print(f"missing_{k}")
        raise SystemExit(0)
if not isinstance(obj.get("weak_concepts"), list):
    print("weak_concepts_not_list")
    raise SystemExit(0)
print("ok")
PY
)
if [[ "$profile_ok" != "ok" ]]; then
  fail "Profile malformed: ${profile_json}"
fi

log "Fetching difficulty-plan..."
diffplan_json=$(curl -sS "${API_BASE}/api/profile/difficulty-plan?user_id=${USER_ID}" || true)
if [[ "$diffplan_json" == *"detail"* ]]; then
  fail "Difficulty-plan failed: ${diffplan_json}"
fi
diffplan_ok=$(DIFFPLAN_JSON="${diffplan_json}" python3 - <<'PY'
import json, os
data = os.environ.get("DIFFPLAN_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
for k in ("easy", "medium", "hard"):
    if k not in obj or not isinstance(obj[k], (int, float)):
        print(f"missing_or_invalid_{k}")
        raise SystemExit(0)
print("ok")
PY
)
if [[ "$diffplan_ok" != "ok" ]]; then
  fail "Difficulty-plan malformed: ${diffplan_json}"
fi

log "Fetching activity..."
activity_json=$(curl -sS "${API_BASE}/api/activity?user_id=${USER_ID}&limit=10" || true)
activity_ok=$(ACTIVITY_JSON="${activity_json}" python3 - <<'PY'
import json, os
data = os.environ.get("ACTIVITY_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)

if isinstance(obj, dict) and "detail" in obj:
    print("error")
elif isinstance(obj, dict) and "items" in obj:
    print("ok")
else:
    print("missing_items")
PY
)
if [[ "$activity_ok" != "ok" ]]; then
  fail "Activity failed: ${activity_json}"
fi

log "Getting or creating KB..."
kb_json=$(curl -sS "${API_BASE}/api/kb?user_id=${USER_ID}" || true)
KB_ID=""
if [[ "$kb_json" == *"detail"* ]]; then
  fail "KB list failed: ${kb_json}"
fi
KB_ID=$(KB_JSON="${kb_json}" python3 - <<'PY'
import json, os
data = os.environ.get("KB_JSON", "")
try:
    items = json.loads(data)
except Exception:
    print("")
    raise SystemExit(0)
if isinstance(items, list) and items:
    print(items[0].get("id", ""))
else:
    print("")
PY
)
if [[ -z "$KB_ID" ]]; then
  log "No KB found; creating smoke_kb..."
  create_kb_json=$(curl -sS -H "Content-Type: application/json" \
    -d "{\"name\":\"smoke_kb\",\"user_id\":\"${USER_ID}\"}" \
    "${API_BASE}/api/kb" || true)
  if [[ "$create_kb_json" == *"detail"* ]] && [[ "$create_kb_json" != *"id"* ]]; then
    fail "Create KB failed: ${create_kb_json}"
  fi
  KB_ID=$(KB_JSON="${create_kb_json}" python3 - <<'PY'
import json, os
data = os.environ.get("KB_JSON", "")
try:
    obj = json.loads(data)
    print(obj.get("id", ""))
except Exception:
    print("")
PY
)
fi
if [[ -z "$KB_ID" ]]; then
  fail "Could not get or create KB"
fi
log "kb_id=${KB_ID}"

log "Creating chat session..."
session_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"doc_id\":\"${doc_id}\"}" \
  "${API_BASE}/api/chat/sessions" || true)
if [[ "$session_json" == *"detail"* ]] && [[ "$session_json" != *"id"* ]]; then
  fail "Create session failed: ${session_json}"
fi
session_id=$(SESSION_JSON="${session_json}" python3 - <<'PY'
import json, os
data = os.environ.get("SESSION_JSON", "")
try:
    obj = json.loads(data)
    print(obj.get("id", ""))
except Exception:
    print("")
PY
)
if [[ -z "$session_id" ]]; then
  fail "Create session did not return session_id: ${session_json}"
fi
log "session_id=${session_id}"

log "QA with session_id (persist sources)..."
qa_session_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"session_id\":\"${session_id}\",\"question\":\"What is a matrix?\"}" \
  "${API_BASE}/api/qa" || true)
if [[ "$qa_session_json" == *"detail"* || "$qa_session_json" == "Internal Server Error" ]]; then
  fail "QA with session failed: ${qa_session_json}"
fi
qa_session_ok=$(QA_SESSION_JSON="${qa_session_json}" python3 - <<'PY'
import json, os
data = os.environ.get("QA_SESSION_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
answer = obj.get("answer")
sources = obj.get("sources")
if isinstance(answer, str) and answer.strip() and isinstance(sources, list) and len(sources) > 0:
    print("ok")
else:
    print("missing_answer_or_sources")
PY
)
if [[ "$qa_session_ok" != "ok" ]]; then
  fail "QA with session malformed: ${qa_session_json}"
fi

log "Fetching session messages..."
messages_json=$(curl -sS "${API_BASE}/api/chat/sessions/${session_id}/messages?user_id=${USER_ID}" || true)
messages_ok=$(MESSAGES_JSON="${messages_json}" python3 - <<'PY'
import json, os
data = os.environ.get("MESSAGES_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
if isinstance(obj, dict) and "detail" in obj:
    print("error")
elif isinstance(obj, list):
    if not obj:
        print("empty_list")
    else:
        has_assistant_with_sources = False
        for m in obj:
            if m.get("role") == "assistant" and m.get("sources"):
                if isinstance(m["sources"], list) and len(m["sources"]) > 0:
                    has_assistant_with_sources = True
                    break
        if has_assistant_with_sources:
            print("ok")
        else:
            print("no_assistant_sources")
else:
    print("not_list")
PY
)
if [[ "$messages_ok" != "ok" ]]; then
  fail "Get messages failed: ${messages_json}"
fi

log "Fetching recommendations..."
rec_json=$(curl -sS "${API_BASE}/api/recommendations?user_id=${USER_ID}&kb_id=${KB_ID}&limit=5" || true)
if [[ "$rec_json" == *"detail"* ]] && [[ "$rec_json" != *"items"* ]]; then
  fail "Recommendations failed: ${rec_json}"
fi
rec_ok=$(REC_JSON="${rec_json}" python3 - <<'PY'
import json, os
data = os.environ.get("REC_JSON", "")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
if isinstance(obj, dict) and "detail" in obj and "items" not in obj:
    print("error")
elif isinstance(obj, dict) and "items" in obj:
    print("ok")
else:
    print("missing_items")
PY
)
if [[ "$rec_ok" != "ok" ]]; then
  fail "Recommendations malformed: ${rec_json}"
fi

log "Negative case: QA without doc_id or kb_id returns 400..."
qa_neg1_http=$(curl -sS -o /tmp/smoke_qa_neg1.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"question\":\"What is a matrix?\"}" \
  "${API_BASE}/api/qa" || echo "000")
qa_neg1_body=$(cat /tmp/smoke_qa_neg1.json 2>/dev/null || echo "{}")
if [[ "$qa_neg1_http" != "400" ]]; then
  fail "QA without doc_id/kb_id expected 400, got ${qa_neg1_http}: ${qa_neg1_body}"
fi
qa_neg1_ok=$(QA_NEG1="${qa_neg1_body}" python3 - <<'PY'
import json, os
data = os.environ.get("QA_NEG1", "{}")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
if isinstance(obj, dict) and obj.get("detail"):
    print("ok")
else:
    print("no_detail")
PY
)
if [[ "$qa_neg1_ok" != "ok" ]]; then
  fail "QA 400 response missing detail: ${qa_neg1_body}"
fi

log "Negative case: QA with invalid session_id returns 404..."
qa_neg2_http=$(curl -sS -o /tmp/smoke_qa_neg2.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"session_id\":\"00000000-0000-0000-0000-000000000000\",\"question\":\"What is a matrix?\"}" \
  "${API_BASE}/api/qa" || echo "000")
qa_neg2_body=$(cat /tmp/smoke_qa_neg2.json 2>/dev/null || echo "{}")
if [[ "$qa_neg2_http" != "404" ]]; then
  fail "QA with invalid session_id expected 404, got ${qa_neg2_http}: ${qa_neg2_body}"
fi
qa_neg2_ok=$(QA_NEG2="${qa_neg2_body}" python3 - <<'PY'
import json, os
data = os.environ.get("QA_NEG2", "{}")
try:
    obj = json.loads(data)
except Exception:
    print("invalid_json")
    raise SystemExit(0)
if isinstance(obj, dict) and obj.get("detail"):
    print("ok")
else:
    print("no_detail")
PY
)
if [[ "$qa_neg2_ok" != "ok" ]]; then
  fail "QA 404 response missing detail: ${qa_neg2_body}"
fi

log "Smoke test complete."
