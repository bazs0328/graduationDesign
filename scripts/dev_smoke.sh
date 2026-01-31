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

log "Generating summary..."
summary_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\"}" \
  "${API_BASE}/api/summary" || true)
if [[ "$summary_json" == *"detail"* ]]; then
  fail "Summary failed: ${summary_json}"
fi

log "Generating keypoints..."
keypoints_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\"}" \
  "${API_BASE}/api/keypoints" || true)
if [[ "$keypoints_json" == *"detail"* ]]; then
  fail "Keypoints failed: ${keypoints_json}"
fi

log "Asking QA..."
qa_json=$(curl -sS -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"${doc_id}\",\"user_id\":\"${USER_ID}\",\"question\":\"What is a matrix?\"}" \
  "${API_BASE}/api/qa" || true)
if [[ "$qa_json" == *"detail"* || "$qa_json" == "Internal Server Error" ]]; then
  fail "QA failed: ${qa_json}"
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

log "Smoke test complete."
