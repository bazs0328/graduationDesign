# AGENTS

本仓库为 GradTutor（FastAPI + Vue）。本文件用于指导协作开发，确保变更安全、可复现、贴合项目目标。

## 项目需求（补充版）
题目：集成大型语言模型（LLM）的个性化学习辅助系统的设计与实现。

题目描述：利用当前热门的大型语言模型（如 GPT、Gemini 等）的 API，构建一个智能学习辅助工具。系统根据用户上传的学习资料（如 PDF 课件、笔记），自动生成知识点摘要、模拟测验题，并提供交互式的智能问答机器人。

核心技术：
- 后端：Python（FastAPI/Flask）
- 前端：React / Vue.js
- 核心服务：大型语言模型 API（OpenAI、Google 等）
- 数据处理：LangChain、文本向量化与检索技术

主要功能模块：
- 文档上传与解析
- 知识点摘要生成
- 智能问答
- 自动组卷与测验
- 用户学习进度跟踪

## 参考实现：DeepTutor（实现思路对齐）
- 参考仓库：`https://github.com/HKUDS/DeepTutor`（仅作设计与流程参考，不要求 1:1 复刻）
- 参考重点：
  - 知识库驱动：基于上传资料构建个人知识库，用于检索与生成。
  - RAG 混合检索：强调语义检索与关键词检索的混合策略，以提升召回与鲁棒性。
  - 结构化输出：摘要、要点、问答、测验都应结构化返回，便于前端可视化与进度统计。
  - 练习/测验生成：区分“知识库定制题”和“模拟/仿真题”的生成逻辑。
  - 记忆与引用：保留会话状态与引用信息，便于追踪与复用。
  - 分层框架：UI 层、智能体模块、工具集成层、知识与记忆层等分层设计，便于扩展。

## 快速地图
- backend/：FastAPI 应用、SQLite、LLM/RAG 逻辑
  - app/routers：API 路由
  - app/models.py：SQLAlchemy 模型
  - app/schemas.py：Pydantic 模型
  - app/core：配置、提供商、路径、向量库
  - data/：SQLite + 用户数据（uploads/text/chroma）
- web/：Vue 3 + Vite 前端
- scripts/：smoke / regression / load test 工具

## 启动方式
1) cp backend/.env.example backend/.env 并填写 API Key
2) docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
3) cd web && npm install && npm run dev

## 后端开发约定
- 后端优先用 Docker 运行与调试：
  - docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend bash
- API 路由放在 backend/app/routers，且需在 backend/app/main.py 注册。
- 请求/响应模型放在 backend/app/schemas.py。
- 数据库为 SQLite：backend/data/app.db。
  - 新增字段需同步修改 backend/app/models.py 与 backend/app/db.py:ensure_schema。
- 用户数据目录：backend/data/users/<user_id>/。

## 前端开发约定
- API Base 由 VITE_API_BASE 决定，默认 http://localhost:8000（见 web/src/api.js）。
- 前端请求使用 web/src/api.js 的 apiGet/apiPost 以统一错误处理。

## 测试与检查
- scripts/dev_smoke.sh（需要后端已启动，API_BASE 可配置）。
- web：npm run test（vitest）。
- scripts/qa_regression.py（在后端容器内运行，耗时较长且可能产生成本）。
- scripts/loadtest_qa.sh（压力测试，生成大量文档）。

## 约定与规范
- 环境变量仅使用 backend/.env；新增变量需同步到 backend/.env.example。
- 禁止提交密钥或 backend/data/ 下的生成数据。
- 变更尽量小步、可回滚，遵循现有代码风格与分层结构。
