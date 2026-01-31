# GradTutor (LLM Personal Learning Assistant)

This project implements a personalized learning assistant inspired by the DeepTutor workflow, adapted to FastAPI + Vue and a local RAG pipeline. It supports document upload, summarization, Q&A, quiz generation, and progress tracking.

## Features
- Document upload and parsing (PDF/TXT/MD)
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
- `LLM_PROVIDER=openai` or `gemini` or `deepseek`
- `EMBEDDING_PROVIDER=openai|gemini|deepseek|bgem3`
- `OPENAI_API_KEY=...`
- `GOOGLE_API_KEY=...`
- `DEEPSEEK_API_KEY=...` (DeepSeek is OpenAI-compatible; see `.env.example` for base_url)
- DeepSeek embedding is optional; if not provided, embeddings fall back to OpenAI when `OPENAI_API_KEY` is set.
 - `BGE_M3_MODEL=BAAI/bge-m3` and `EMBEDDINGS_DEVICE=cpu` for local BGE-M3 embeddings

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
python3 /app/scripts/qa_regression.py \
  --user-id qa_reg --kb-name qa_reg_kb_bge \
  --doc-count 30 --queries 40 --top-k 5 --fetch-k 20 \
  --mode hybrid --min-recall 0.7
```
4) 配置规范
- 只保留 `backend/.env`，根目录不再放 `.env`
- LLM/Embedding 配置统一在 `backend/.env`

## Notes
- Uploaded files are stored per user in `backend/data/users/<user_id>/uploads`.
- Parsed text is stored in `backend/data/users/<user_id>/text`.
- Vector store persists in `backend/data/users/<user_id>/chroma`.
- If you ran an older schema, remove `backend/data/app.db` to recreate tables.
- New activity feed endpoint: `GET /api/activity?user_id=...`

## Regression (Docker)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  python3 /app/scripts/qa_regression.py \
  --user-id qa_reg --kb-name qa_reg_kb_bge \
  --doc-count 30 --queries 40 --top-k 5 --fetch-k 20 \
  --mode hybrid --min-recall 0.7
```
"# graduationDesign" 
