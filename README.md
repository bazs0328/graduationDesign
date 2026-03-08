# StudyCompass

StudyCompass 是一个面向高校学生自学场景的 LLM 个性化学习辅助系统原型。
系统围绕“学生自有学习资料”工作，支持上传课件、讲义、笔记等文档，并提供摘要、问答、测验、学习进度跟踪、学习路径和个性化推荐。

项目当前采用：

- 后端：FastAPI + SQLite + Chroma + LangChain
- 前端：Vue 3 + Vite + Pinia
- 大模型接入：DeepSeek / Qwen / DashScope
- 检索方案：向量检索 + 词法检索 + RAG

## 项目定位

本项目不是面向固定教材的单功能问答工具，而是一个围绕学生上传资料构建学习空间的学习助手原型，重点覆盖完整学习闭环：

1. 上传资料并解析
2. 生成摘要和知识点
3. 围绕资料进行问答
4. 生成并提交测验
5. 跟踪学习进度、学习路径和推荐动作

## 当前功能

### 核心学习功能

- 文档上传与解析：支持 `PDF / TXT / MD / DOCX / PPTX`
- 扫描版 PDF OCR 兜底识别
- 文档摘要生成
- 知识点提取与掌握度跟踪
- 基于资料范围的智能问答
- 题目生成、自动评分与错题反馈
- 学习进度、活动流、推荐与学习路径可视化

### 个性化能力

- 用户登录与多用户隔离
- 每个账号独立保存模型接入配置
- 每个账号独立保存高级参数覆盖
- 轻量学习者画像：
  - `ability_level`
  - `theta`
  - `frustration_score`
  - `weak_concepts`
- QA 按学习者能力层级调整讲解策略
- Quiz 支持自适应难度分配
- Progress 页根据掌握度和行为数据生成推荐与学习路径

### 工程能力

- 账号体系与 JWT 登录
- 自动建库、自动补齐 SQLite schema
- 用户级数据隔离
- 后端单测、前端单测、E2E 测试
- Docker 开发方式

## 页面与模块

- `上传`：创建资料库、上传和管理文档
- `摘要`：查看摘要与知识点
- `问答`：基于资料范围进行普通问答或讲解模式问答
- `测验`：生成试卷、提交作答、查看反馈
- `进度`：查看资料库统计、学习活动、推荐、学习路径、画像信息
- `设置中心`：配置模型接入、学习偏好和当前账号高级参数

## 快速开始

### 方式一：后端 Docker + 前端本地开发

这是当前最推荐的启动方式。

#### 1. 准备后端环境变量

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 只用于部署级配置，不需要在这里填写 API Key。

#### 2. 启动后端

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

日常开发如果没有改 Dockerfile 或系统依赖，可以直接：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

后端默认地址：

```text
http://localhost:8000
```

健康检查：

```text
GET /api/health
```

#### 3. 启动前端

```bash
cd web
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

#### 4. 首次使用

1. 打开前端页面
2. 注册账号并登录
3. 进入 `设置中心 -> 模型接入`
4. 为当前账号填写 DeepSeek / Qwen / DashScope 配置
5. 返回 `上传` 页面开始使用

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

建议使用 Node.js 18 及以上版本。

```bash
cd web
npm install
npm run dev
```

## OCR 依赖

Docker 镜像已经内置 OCR 相关系统依赖。
如果你在本地直接运行后端，需要额外安装：

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

### 2. 账号级配置：设置中心

普通用户不需要改 `.env` 填模型密钥。
当前账号的模型和高级参数统一在前端设置页维护：

- `设置中心 -> 模型接入`
- `设置中心 -> 当前账号高级参数`

这些配置会按用户隔离保存，不会共享给其他账号。

### 3. 当前支持的模型提供商

设置页当前支持：

- 对话模型：`DeepSeek`、`Qwen`
- 向量模型：`Qwen`、`DashScope`

项目底层保留了一些历史兼容字段，但当前正式使用路径以上述提供商为主。

## 多用户与数据隔离

系统当前已经具备基础多用户隔离能力：

- 用户通过账号登录访问系统
- 文档、知识库、进度、画像按用户隔离
- 模型接入配置按用户隔离
- 高级参数覆盖按用户隔离
- 后台文档处理任务也会加载对应用户的运行配置

这意味着：

- 用户 A 的 API Key 不会自动继承给用户 B
- 用户 A 的检索/OCR/分块高级参数不会影响用户 B

## 个性化策略说明

当前项目的个性化能力是“轻量画像 + 规则/模型联动”的实现方式，不是复杂知识追踪平台，但已经形成可说明的闭环：

1. 系统根据测验表现更新学习者画像
2. 画像包含能力层级、最近正确率、挫败感、弱项概念等信息
3. QA 会根据画像调整讲解强度与解释粒度
4. Quiz 会根据画像生成难度分配方案
5. Progress 页会结合掌握度与行为记录生成推荐和学习路径

相关实现可参考：

- [backend/app/services/learner_profile.py](backend/app/services/learner_profile.py)
- [backend/app/services/qa.py](backend/app/services/qa.py)
- [backend/app/routers/quiz.py](backend/app/routers/quiz.py)
- [backend/app/routers/recommendations.py](backend/app/routers/recommendations.py)
- [backend/app/routers/profile.py](backend/app/routers/profile.py)

## 数据目录

默认数据目录为 `backend/data`。

常见内容包括：

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
- `users/<user_id>/uploads`：原始上传文件
- `users/<user_id>/text`：解析后的文本
- `users/<user_id>/chroma`：向量库
- `users/<user_id>/lexical`：词法检索缓存

## 测试

### 后端测试

```bash
python3 -m pytest tests/backend -q
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

### E2E

```bash
cd web
npm run test:e2e
```

如果要运行依赖真实 LLM 的完整流程测试：

```bash
cd web
E2E_LLM=1 npm run test:e2e
```

如果后端不在默认地址，可以指定：

```bash
cd web
E2E_API_BASE=http://localhost:8000 npm run test:e2e
```

## 常用开发命令

### 进入后端容器

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

## 项目结构

```text
backend/
  app/
    core/        # 配置、认证、运行时上下文、底层能力
    routers/     # API 路由
    services/    # 业务逻辑
    models.py    # 数据模型
    schemas.py   # Pydantic schema
  scripts/       # 数据清理与迁移脚本
  requirements.txt

web/
  src/
    views/       # 页面
    components/  # UI 组件
    stores/      # Pinia 状态管理
    composables/ # 复用逻辑
    utils/       # 工具函数
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

## 说明

当前 README 以“现在实际能跑的项目行为”为准。
如果你要写论文，建议把系统描述为：

> 一个面向高校学生自有资料、集成 LLM 与 RAG、具备轻量个性化能力的学习辅助系统原型。
