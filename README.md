# GradTutor (LLM Personal Learning Assistant)

This project implements a personalized learning assistant inspired by the DeepTutor workflow, adapted to FastAPI + Vue and a local RAG pipeline. It supports document upload, summarization, Q&A, quiz generation, and progress tracking.

## Features
- Document upload and parsing (PDF/TXT/MD, scanned PDF OCR fallback)
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
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### Frontend
```bash
cd web
npm install
npm run dev
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
- `OCR_ENABLED=true|false` (enable OCR fallback for scanned PDFs)
- `OCR_LANGUAGE=chi_sim+eng` (Tesseract language packs)
- `OCR_MIN_TEXT_LENGTH=10` (per-page min chars before OCR fallback)

## OCR Dependencies (Local Development)

Docker images already install OCR dependencies in `backend/Dockerfile`.

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

Frontend can point to a different API via:
```
VITE_API_BASE=http://localhost:8000
```

User scope:
- The UI uses a local `User ID` (stored in localStorage) to separate documents and progress.

## 规范操作流程（Docker 优先）
1) 启动开发环境（统一入口）
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
2) 进入已运行的容器执行命令（避免 `docker compose run` 产生新容器）
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend bash
```
3) 回归测试（在同一容器内执行）
```bash
python3 /app/tests/qa_regression.py \
  --user-id qa_reg --kb-name qa_reg_kb_qwen \
  --doc-count 30 --queries 40 --top-k 5 --fetch-k 20 \
  --mode hybrid --min-recall 0.7
```
4) 配置规范
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
