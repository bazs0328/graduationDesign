#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
if isinstance(points, list) and points:
    print("ok")
else:
    print("missing_keypoints")
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
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"count\":3,\"difficulty\":\"easy\"}" \
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
    opts = q.get("options") if isinstance(q, dict) else None
    if not isinstance(opts, list) or len(opts) != 4:
        print("invalid_options")
        raise SystemExit(0)
print("ok")
PY
)
if [[ "$quiz_ok" != "ok" ]]; then
  fail "Quiz malformed: ${quiz_json}"
fi

log "Submitting quiz..."
submit_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"quiz_id\":\"${quiz_id}\",\"user_id\":\"${USER_ID}\",\"answers\":[0,0,0]}" \
  "${API_BASE}/api/quiz/submit" || true)
if [[ "$submit_json" == *"detail"* ]]; then
  fail "Quiz submit failed: ${submit_json}"
fi

log "Fetching progress..."
progress_json=$(curl -sS "${API_BASE}/api/progress?user_id=${USER_ID}" || true)
if [[ "$progress_json" == *"detail"* ]]; then
  fail "Progress failed: ${progress_json}"
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
    print("ok")
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

log "Smoke test complete."
