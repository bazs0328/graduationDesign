# StudyCompass

StudyCompass 是一个面向高校学生自学场景的 LLM 个性化学习辅助系统原型。系统围绕“学生自有学习资料”工作，支持上传课件、讲义、笔记等文档，并将其转化为摘要、问答、测验、进度跟踪、学习路径与推荐动作，覆盖从资料导入到复盘巩固的完整学习闭环。

## 核心能力

- 文档上传与解析：支持 `PDF / TXT / MD / DOCX / PPTX`
- 扫描版 PDF OCR 兜底识别
- 单文档摘要与知识点提取
- 基于资料范围的问答与分步讲解
- 题目生成、自动评分、错题反馈与针对性再练
- 学习进度、活动流、知识点掌握度、推荐与学习路径展示
- 用户登录、JWT 鉴权、多用户数据隔离
- 当前账号独立保存模型接入配置和高级参数覆盖

## 技术栈

- 后端：FastAPI + SQLAlchemy + SQLite + Chroma + LangChain
- 前端：Vue 3 + Vite + Pinia + Tailwind CSS 4
- 检索：向量检索 + BM25 词法检索 + Hybrid RAG
- 文档处理：PyMuPDF / pdfplumber / python-docx / python-pptx / RapidOCR / Tesseract
- 测试：pytest + Vitest + Playwright

## 典型使用流程

1. 在 `上传` 页面创建资料库并上传学习资料
2. 在 `摘要` 页面生成摘要和知识点
3. 在 `问答` 页面围绕资料进行普通问答或讲解模式问答
4. 在 `测验` 页面生成题目并提交作答
5. 在 `进度` 页面查看活动、掌握度、推荐和学习路径
6. 在 `设置中心` 页面维护当前账号的模型接入、学习偏好和高级诊断配置

## 快速开始

### 推荐方式：后端 Docker + 前端本地开发

这是当前最推荐的开发方式。

### 前置要求

- Docker 与 Docker Compose
- Node.js 18 及以上版本

### 1. 准备后端部署级配置

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 只用于部署级配置，不需要在这里填写模型 API Key。

### 2. 启动后端

首次启动或改过 `backend/Dockerfile` / 系统依赖时：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

日常开发可直接：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

默认地址：

- 后端 API：`http://localhost:8000`
- 健康检查：`http://localhost:8000/api/health`
- Swagger 文档：`http://localhost:8000/docs`

### 3. 启动前端

```bash
cd web
npm install
npm run dev
```

默认地址：

- 前端：`http://localhost:5173`

如果后端不在默认地址，可以显式指定：

```bash
cd web
VITE_API_BASE=http://localhost:8000 npm run dev
```

### 4. 首次使用

1. 打开前端页面并注册账号
2. 登录后进入 `设置中心 -> 模型接入`
3. 为当前账号填写对话模型和向量模型配置
4. 返回 `上传` 页面创建资料库并上传文档

## 本地开发（不使用 Docker）

### 后端

建议使用 Python 3.11。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd web
npm install
npm run dev
```

### WSL 说明

如果项目位于 `/mnt/*` 挂载盘下，前端开发服务器已经自动启用 polling 以减少 Vite 热更新失效问题。

## OCR 与本地系统依赖

Docker 镜像已经内置 OCR 相关系统依赖。如果直接在本地运行后端，需要额外安装：

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng poppler-utils
```

### macOS

```bash
brew install tesseract poppler
brew install tesseract-lang
```

## 配置说明

### 1. 部署级配置：`backend/.env`

`backend/.env` 只建议放部署层配置，例如：

- `APP_NAME`
- `DATA_DIR`
- `AUTH_SECRET_KEY`
- `AUTH_TOKEN_TTL_HOURS`
- `AUTH_REQUIRE_LOGIN`
- `AUTH_ALLOW_LEGACY_USER_ID`

默认模板见 [backend/.env.example](backend/.env.example)。

默认情况下：

- `AUTH_REQUIRE_LOGIN=true`
- `AUTH_ALLOW_LEGACY_USER_ID=false`

也就是除 `/api/auth/*` 和 `/api/health` 外，其余 API 默认都要求登录。

### 2. 账号级配置：设置中心

普通用户不需要修改 `.env` 填模型密钥。当前账号的模型和高级参数统一在前端设置页维护：

- `设置中心 -> 模型接入`
- `设置中心 -> 学习偏好`
- `设置中心 -> 高级诊断`

这些配置会按用户隔离保存，不会共享给其他账号。

### 3. 当前主路径支持的模型提供商

设置页当前主路径支持：

- 对话模型：`DeepSeek`、`Qwen`
- 向量模型：`Qwen`、`DashScope`

后端仍保留部分历史兼容字段，但当前推荐使用路径以上述提供商为主。

## 多用户与个性化能力

系统当前已经具备基础多用户隔离与轻量个性化闭环：

- 用户通过账号登录访问系统
- 文档、知识库、进度、画像、模型配置按用户隔离
- 后台文档处理任务会加载对应用户的运行时配置
- 学习者画像包含 `ability_level`、`theta`、`frustration_score`、`weak_concepts`
- QA 会根据画像调整讲解粒度与风格
- Quiz 会根据画像进行自适应难度分配
- Progress 会结合掌握度和行为记录生成推荐与学习路径

相关实现可参考：

- [backend/app/services/learner_profile.py](backend/app/services/learner_profile.py)
- [backend/app/services/qa.py](backend/app/services/qa.py)
- [backend/app/routers/quiz.py](backend/app/routers/quiz.py)
- [backend/app/routers/recommendations.py](backend/app/routers/recommendations.py)
- [backend/app/routers/profile.py](backend/app/routers/profile.py)

## 测试

### 测试目录约定

- `backend/tests/`：后端 pytest 测试
- `web/tests/unit/`：前端 Vitest 单元测试
- `web/tests/e2e/`：前端 Playwright E2E 测试
- `tests/`：项目级脚本，如 smoke、回归、压测脚本

### 后端测试

在仓库根目录运行：

```bash
python3 -m pytest backend/tests -q
```

如果是在后端开发容器中运行，由于容器工作目录是 `/app`，命令应为：

```bash
pytest tests -q
```

### 前端单元测试

```bash
cd web
npm test
```

### 前端构建

```bash
cd web
npm run build
```

### 前端 E2E

```bash
cd web
npm run test:e2e
```

常用 E2E 环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://localhost:5173` | Playwright 访问的前端地址 |
| `E2E_API_BASE` | `http://localhost:8000` | E2E 用于检查和调用的后端地址 |
| `E2E_LLM` | `0` | 设为 `1` 时运行依赖真实模型的完整流程 |
| `E2E_USERNAME` | 空 | 指定已有测试账号用户名 |
| `E2E_PASSWORD` | `e2e-password-123` | 指定测试账号密码 |

示例：

```bash
cd web
E2E_API_BASE=http://localhost:8000 E2E_LLM=1 npm run test:e2e
```

### 项目级脚本

```bash
bash tests/smoke/dev_smoke.sh
python3 tests/qa_regression.py
python3 tests/quiz_paper_regression.py
bash tests/loadtest_qa.sh
```

这些脚本主要用于 smoke、回归和压测，不属于 `pytest` / `vitest` / `playwright` 的标准测试发现目录。

## 常用开发命令

### 进入后端开发容器

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend bash
```

### 容器内增量安装后端依赖

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend \
  pip install -r /app/requirements.txt
```

### 前端增量安装依赖

```bash
cd web
npm install
```

## 数据目录

默认数据目录为 `backend/data`。常见内容包括：

```text
backend/data/
  app.db
  system_bootstrap.json
  users/<user_id>/
    uploads/
    text/
    chroma/
    lexical/
    kb/
```

其中：

- `app.db`：SQLite 数据库
- `system_bootstrap.json`：系统启动期初始化信息
- `users/<user_id>/uploads`：原始上传文件
- `users/<user_id>/text`：解析后的文本
- `users/<user_id>/chroma`：向量库
- `users/<user_id>/lexical`：词法检索缓存
- `users/<user_id>/kb`：资料库相关元数据

## 项目结构

```text
backend/
  app/
    core/          # 配置、认证、运行时上下文、底层能力
    routers/       # API 路由
    services/      # 业务逻辑
    utils/         # 通用工具
    models.py      # SQLAlchemy 模型
    schemas.py     # Pydantic schema
    main.py        # FastAPI 入口
  scripts/         # 数据清理、迁移、辅助脚本
  tests/           # 后端 pytest
  requirements.txt
  Dockerfile

web/
  src/
    views/         # 页面
    components/    # 组件
    composables/   # 复用逻辑
    stores/        # Pinia 状态管理
    router/        # 前端路由
    utils/         # 工具函数
    styles/        # 样式入口
  tests/
    unit/          # Vitest
    e2e/           # Playwright
  scripts/         # 前端辅助脚本

tests/
  smoke/           # smoke 脚本
  *.py / *.sh      # 回归、压测等项目级脚本
```

## 适用边界

本项目当前更适合作为：

- 毕业设计原型
- 本地部署的课程学习辅助系统
- 面向学生自学场景的 LLM + RAG 教学应用演示系统

它已经具备较完整的功能闭环，但仍然不是生产级教学平台。若继续扩展，可以优先考虑：

- 更完整的实验数据与效果评估
- 更细粒度的学习者画像
- 更强的知识图谱或知识追踪能力
- 更严格的权限与运维体系
