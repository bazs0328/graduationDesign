# GradTutor (LLM Personal Learning Assistant)

This project implements a personalized learning assistant inspired by the DeepTutor workflow, adapted to FastAPI + Vue and a local RAG pipeline. It supports document upload, summarization, Q&A, quiz generation, and progress tracking.

## Features
- Document upload and parsing (PDF/TXT/MD/DOCX/PPTX, scanned PDF OCR fallback)
- Knowledge summary & keypoint generation (chunk-map-reduce)
- RAG-style Q&A with source snippets
- Auto quiz generation (MCQ) + grading
- Progress tracking (attempts, summaries, keypoints, Q&A)

## Tech Stack
- Backend: FastAPI + SQLite + LangChain + Chroma
- Frontend: Vue 3 (Vite)
- LLM: OpenAI or Gemini (configurable)

## Quick Start

### Backend (Docker, recommended)
```bash
cp backend/.env.example backend/.env
# edit backend/.env with your API key
# first-time start / Dockerfile changed / system deps changed
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# normal daily start (no image rebuild)
# docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

If you only changed Python dependencies in `backend/requirements.txt`, you can incrementally install into the running backend container (no image rebuild). `pip install -r` is incremental by default and only installs missing/changed packages:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend \
  pip install -r /app/requirements.txt
```

Install a single new backend package (quick verification)：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend \
  pip install rapidocr-onnxruntime
```

Note: incremental installs above apply to the current container. If you recreate the container later, rebuild the image (`up --build`) to persist dependency changes in the image.

### Frontend
```bash
cd web
npm install
npm run dev
```

`npm install` is also incremental by default (it installs missing/changed packages only). For a single package:

```bash
cd web
npm install <package-name>
```

Open the UI at http://localhost:5173

## Configuration
Backend settings are in `backend/.env`.

### Minimal setup (recommended)
1) Copy `backend/.env.example` to `backend/.env`.
2) Keep `LLM_PROVIDER=auto` and `EMBEDDING_PROVIDER=auto`.
3) Fill at least one key: `OPENAI_API_KEY` / `QWEN_API_KEY` / `GOOGLE_API_KEY` / `DEEPSEEK_API_KEY`.

### Advanced setup
- Prefer frontend configuration: `设置中心 -> 高级设置与诊断 -> 系统高级参数（可编辑）`.
- Most advanced runtime tuning can now be done in frontend form controls (switch/number/select/text).
- `backend/.env.advanced.example` remains only as a fallback template for headless/server-only deployments.
- Existing `.env` files remain compatible (no mandatory migration).

## OCR Dependencies (Local Development)

Docker images already install OCR dependencies in `backend/Dockerfile`.
Python OCR libraries (`rapidocr-onnxruntime`, `opencv-python-headless`, `numpy`, `pytesseract`, `pdf2image`) are installed via `backend/requirements.txt`.

If you run backend locally (without Docker), install:

- Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng poppler-utils
```
- macOS (Homebrew):
```bash
brew install tesseract poppler
brew install tesseract-lang
```

### Recommended OCR Config (Chinese scanned PDFs / exams)

```env
OCR_ENABLED=true
OCR_ENGINE=rapidocr
OCR_FALLBACK_ENGINES=rapidocr
OCR_TESSERACT_LANGUAGE=chi_sim+eng
OCR_RENDER_DPI=360
OCR_CHECK_PAGES=3
OCR_MIN_TEXT_LENGTH=10
OCR_PREPROCESS_ENABLED=true
OCR_DESKEW_ENABLED=true
OCR_LOW_CONFIDENCE_THRESHOLD=0.78
```

Frontend can point to a different API via:
```
VITE_API_BASE=http://localhost:8000
```

User scope:
- The UI uses a local `User ID` (stored in localStorage) to separate documents and progress.

## 规范操作流程（Docker 优先）
1) 启动开发环境（统一入口）
```bash
# 首次启动 / Dockerfile 变更 / apt 系统依赖变更时
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 日常开发（代码改动、配置改动）通常不需要重建镜像
# docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```
2) 进入已运行的容器执行命令（避免 `docker compose run` 产生新容器）
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend bash
```
3) 增量安装依赖（不重建镜像）
```bash
# 后端（pip install -r 默认增量安装）
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend \
  pip install -r /app/requirements.txt

# 前端（npm install 默认增量安装）
cd web && npm install
```
4) 回归测试（在同一容器内执行）
```bash
python3 /app/tests/qa_regression.py \
  --user-id qa_reg --kb-name qa_reg_kb_qwen \
  --doc-count 30 --queries 40 --top-k 5 --fetch-k 20 \
  --mode hybrid --min-recall 0.7
```
5) 配置规范
- 只保留 `backend/.env`，根目录不再放 `.env`
- LLM/Embedding 配置统一在 `backend/.env`

## API (Quiz)
- **POST /api/quiz/generate**: Generates MCQ quiz. Requires at least one of:
  - `doc_id` — generate from document content (existing behavior).
  - `reference_questions` — generate questions in the same style/difficulty as the given text (paste or from reference exam).
  - `style_prompt` — generate questions matching a style/template description (e.g. exam-style wording).
- Optional: `count`, `difficulty`, `user_id`. When `doc_id` is omitted, pass `reference_questions` and/or `style_prompt` for mimic-style generation. Submit with **POST /api/quiz/submit** as before.
- **POST /api/quiz/parse-reference**: Accepts a PDF file (multipart), returns `{ "text": "..." }` (extracted plain text). Use the returned `text` as `reference_questions` in **POST /api/quiz/generate** for reference-exam style generation. Does not persist the file.

## Notes
- Uploaded files are stored per user in `backend/data/users/<user_id>/uploads`.
- Parsed text is stored in `backend/data/users/<user_id>/text`.
- Vector store persists in `backend/data/users/<user_id>/chroma`.
- Lexical BM25 cache persists in `backend/data/users/<user_id>/lexical/<kb_id>.jsonl` and now stores optional `tokens` + `tokenizer_version`.
- For custom lexicon files:
  - Global: `data/lexical/stopwords.txt`, `data/lexical/userdict.txt`
  - KB-level: `backend/data/users/<user_id>/kb/<kb_id>/rag_storage/lexicon/stopwords.txt` and `.../userdict.txt`
- To backfill historical lexical rows with the new token fields:
  - `python3 backend/scripts/backfill_lexical_tokens.py` (dry-run)
  - `python3 backend/scripts/backfill_lexical_tokens.py --execute`
- Runtime now uses text-only retrieval/source preview; image retrieval/preview endpoints are removed.
- To purge historical image artifacts and old image metadata:
  - `python3 backend/scripts/purge_image_data.py --dry-run`
  - `python3 backend/scripts/purge_image_data.py --execute`
- If you ran an older schema, remove `backend/data/app.db` to recreate tables.
- New activity feed endpoint: `GET /api/activity?user_id=...`

## Regression (Docker)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  python3 /app/tests/qa_regression.py \
  --user-id qa_reg --kb-name qa_reg_kb_qwen \
  --doc-count 30 --queries 40 --top-k 5 --fetch-k 20 \
  --mode hybrid --min-recall 0.7
```
"# graduationDesign" 
