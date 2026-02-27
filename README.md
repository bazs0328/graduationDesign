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
Backend settings are in `backend/.env`:
- `LLM_PROVIDER=openai` or `gemini` or `deepseek` or `qwen`
- `EMBEDDING_PROVIDER=openai|gemini|deepseek|qwen|dashscope`
- `OPENAI_API_KEY=...`
- `GOOGLE_API_KEY=...`
- `DEEPSEEK_API_KEY=...` (DeepSeek is OpenAI-compatible; see `.env.example` for base_url)
- `QWEN_API_KEY=...` (Qwen is OpenAI-compatible; see `.env.example` for base_url)
- `DASHSCOPE_EMBEDDING_MODEL=...` (DashScope SDK embedding using `QWEN_API_KEY`, e.g. `qwen3-vl-embedding`)
- DeepSeek embedding is optional; if not provided, embeddings fall back to OpenAI when `OPENAI_API_KEY` is set.
- `INDEX_TEXT_CLEANUP_ENABLED=true|false` (enable index cleanup before chunking)
- `INDEX_TEXT_CLEANUP_MODE=conservative` (PDF-oriented cleanup mode)
- `INDEX_TEXT_CLEANUP_NON_PDF_MODE=structure_preserving` (non-PDF cleanup mode; keeps markdown/code structure)
- `NOISE_FILTER_LEVEL=balanced|conservative|aggressive|structure_preserving` (shared noise filter level for QA/Preview/Quiz)
- `NOISE_DROP_LOW_QUALITY_HITS=true|false` (drop low-quality retrieval hits before building sources/context)
- `OCR_ENABLED=true|false` (enable OCR fallback for scanned PDFs)
- `OCR_ENGINE=rapidocr|tesseract|cloud` (primary OCR engine, `cloud` reserved for future)
- `OCR_FALLBACK_ENGINES=rapidocr` (comma-separated OCR fallback chain, de-duplicated; default is no Tesseract fallback)
- `OCR_LANGUAGE=chi_sim+eng` (Tesseract language packs)
- `OCR_TESSERACT_LANGUAGE=chi_sim+eng` (optional; overrides `OCR_LANGUAGE` for Tesseract only)
- `OCR_MIN_TEXT_LENGTH=10` (per-page min chars before OCR fallback)
- `OCR_RENDER_DPI=360` (PDF render DPI for OCR pages)
- `OCR_CHECK_PAGES=3` (how many leading pages to inspect for scanned-PDF detection)
- `OCR_PREPROCESS_ENABLED=true|false` (grayscale/denoise/binarize before OCR)
- `OCR_DESKEW_ENABLED=true|false` (light deskew during OCR preprocessing)
- `OCR_LOW_CONFIDENCE_THRESHOLD=0.78` (fallback to next OCR engine when confidence is low)
- To re-enable Tesseract fallback manually: set `OCR_FALLBACK_ENGINES=rapidocr,tesseract` (and keep Tesseract installed).

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
