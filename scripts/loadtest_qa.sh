#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
USER_ID="${USER_ID:-loadtest}"
KB_NAME="${KB_NAME:-loadtest_kb}"
DOC_COUNT="${DOC_COUNT:-20}"
PARAGRAPHS="${PARAGRAPHS:-400}"
QUERY_COUNT="${QUERY_COUNT:-20}"
TOP_K="${TOP_K:-6}"
FETCH_K="${FETCH_K:-20}"
TMP_DIR="${TMP_DIR:-/tmp/gradtutor_loadtest}"

log() {
  echo "[loadtest] $*"
}

http_status_is_error() {
  local status="$1"
  if [[ -z "$status" ]]; then
    status="000"
  fi
  if [[ "$status" == "000" ]]; then
    return 0
  fi
  if [[ "$status" =~ ^[0-9]+$ ]] && [[ "$status" -ge 400 ]]; then
    return 0
  fi
  return 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

require_cmd curl
require_cmd python3

mkdir -p "$TMP_DIR"

log "Generating ${DOC_COUNT} docs with ${PARAGRAPHS} paragraphs each..."
python3 - <<PY
import os, random, textwrap
out_dir = "$TMP_DIR"
count = int("$DOC_COUNT")
paras = int("$PARAGRAPHS")

topics = [
    "Linear algebra and matrix theory",
    "Probability and stochastic processes",
    "Operating systems and concurrency",
    "Computer networks and protocols",
    "Machine learning fundamentals",
    "Database systems and indexing",
    "Software engineering practices",
    "Algorithms and data structures",
]

os.makedirs(out_dir, exist_ok=True)
for idx in range(1, count + 1):
    random.seed(idx)
    blocks = []
    for i in range(paras):
        topic = random.choice(topics)
        sent = (
            f"{topic}. Paragraph {i} discusses definitions, examples, and implications. "
            f"Key terms: term{idx}_{i%50}, concept{i%30}, theorem{i%20}."
        )
        blocks.append(textwrap.fill(sent, width=100))
    with open(os.path.join(out_dir, f"doc_{idx:02d}.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks))
print(out_dir)
PY

log "Creating or reusing knowledge base: ${KB_NAME}"
kb_resp_file=$(mktemp)
kb_status=$(curl -sS -o "$kb_resp_file" -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${KB_NAME}\",\"user_id\":\"${USER_ID}\"}" \
  "${API_BASE}/api/kb" || true)
kb_json=$(cat "$kb_resp_file")
rm -f "$kb_resp_file"
kb_status="${kb_status:-000}"
if http_status_is_error "$kb_status"; then
  echo "KB request failed (status ${kb_status}): ${kb_json}" >&2
  exit 1
fi

kb_id=$(python3 - <<PY
import json
try:
    obj = json.loads('''${kb_json}''')
    print(obj.get('id',''))
except Exception:
    print('')
PY
)

if [[ -z "$kb_id" ]]; then
  echo "Failed to get kb_id: ${kb_json}" >&2
  exit 1
fi

log "KB id: ${kb_id}"

log "Uploading documents..."
for f in "$TMP_DIR"/*.txt; do
  upload_resp_file=$(mktemp)
  upload_status=$(curl -sS -o "$upload_resp_file" -w "%{http_code}" \
    -F "file=@$f" -F "user_id=${USER_ID}" -F "kb_id=${kb_id}" \
    "${API_BASE}/api/docs/upload" || true)
  upload_resp=$(cat "$upload_resp_file")
  rm -f "$upload_resp_file"
  upload_status="${upload_status:-000}"
  if http_status_is_error "$upload_status"; then
    echo "Upload failed for $f (status ${upload_status}): $upload_resp" >&2
    exit 1
  fi
  echo -n 
  printf "."
  echo -n 
  sleep 0.05
  done

echo ""
log "Upload done."

log "Running ${QUERY_COUNT} QA requests (top_k=${TOP_K}, fetch_k=${FETCH_K})..."
rm -f "$TMP_DIR/durations_ms.txt"
rm -f "$TMP_DIR/errors.txt"

for i in $(seq 1 "$QUERY_COUNT"); do
  question="Explain term${i}_10 and concept${i%30} in ${KB_NAME}."
  payload=$(python3 - <<PY
import json
print(json.dumps({
    "kb_id": "${kb_id}",
    "user_id": "${USER_ID}",
    "question": "${question}",
    "top_k": int("${TOP_K}"),
    "fetch_k": int("${FETCH_K}"),
}))
PY
  )
  start=$(date +%s%N)
  qa_resp_file=$(mktemp)
  qa_status=$(curl -sS -o "$qa_resp_file" -w "%{http_code}" \
    -H "Content-Type: application/json" -d "$payload" "${API_BASE}/api/qa" || true)
  resp=$(cat "$qa_resp_file")
  rm -f "$qa_resp_file"
  qa_status="${qa_status:-000}"
  end=$(date +%s%N)
  dur_ms=$(( (end - start) / 1000000 ))
  echo "$dur_ms" >> "$TMP_DIR/durations_ms.txt"

  if http_status_is_error "$qa_status"; then
    echo "Q$i error (status ${qa_status}): $resp" >> "$TMP_DIR/errors.txt"
  fi
  printf "."
  sleep 0.05
  done

echo ""

python3 - <<PY
import os, statistics
path = "${TMP_DIR}/durations_ms.txt"
with open(path, "r", encoding="utf-8") as f:
    vals = [int(line.strip()) for line in f if line.strip()]
if vals:
    print("[loadtest] QA latency (ms)")
    print("  count:", len(vals))
    print("  min:", min(vals))
    print("  max:", max(vals))
    print("  avg:", round(sum(vals)/len(vals), 2))
    print("  p50:", statistics.median(vals))
    vals_sorted = sorted(vals)
    p90 = vals_sorted[int(len(vals_sorted)*0.9)-1]
    p95 = vals_sorted[int(len(vals_sorted)*0.95)-1]
    print("  p90:", p90)
    print("  p95:", p95)
else:
    print("[loadtest] No QA results")

err_path = "${TMP_DIR}/errors.txt"
if os.path.exists(err_path):
    with open(err_path, "r", encoding="utf-8") as f:
        errors = [line.strip() for line in f if line.strip()]
    if errors:
        print("[loadtest] Errors:")
        for line in errors:
            print("  ", line)
PY

log "Done. Artifacts in ${TMP_DIR}"
