# TODO（需求五模块 + DeepTutor 重合复现）

> **目标**：在满足毕设需求的前提下，尽可能复现 DeepTutor 与需求重合的部分。  
> **优先级**：需求五模块 > DeepTutor 重合增强 > DeepTutor 独有扩展。  
> **状态**：带 [x] 的项表示接口与主流程已实现并通过 smoke/回归；部分 P0 需按验收补强或对齐 DeepTutor。

## 项目需求与模块映射

| 需求模块 | 需求要点 | DeepTutor 重合点 | 本项目落点 |
| --- | --- | --- | --- |
| 1. 文档上传与解析 | PDF/笔记上传、解析入库 | 知识库管理、文档添加、解析与切分 | KB + 上传 + 后台解析 + 向量+BM25 |
| 2. 知识点摘要生成 | 自动生成知识点摘要 | 单文档摘要 + 结构化要点/讲解（Guide 知识简化） | summary + keypoints，增强为结构化+讲解+来源 |
| 3. 智能问答 | 交互式智能问答机器人 | RAG 问答 + 引用来源 + 会话上下文 | RAG QA + sources + 会话持久化与多轮历史 |
| 4. 自动组卷与测验 | 模拟测验题 | Custom 出题（基于知识库）+ Mimic（模拟真题风格） | 按文档出题 + 提交评分；补充模拟真题线 |
| 5. 用户学习进度跟踪 | 学习进度跟踪 | 进度统计、活动流、会话/测验记录 | progress + activity + 会话/测验落库 |

## DeepTutor 实现思路对照（本项目落点）

| DeepTutor 能力/模块 | DeepTutor 源码落点 | 本项目落点（接口/模块） | 说明 |
| --- | --- | --- | --- |
| 知识库与多文档管理 | knowledge/manager.py, add_documents | `/api/kb`、`/api/docs/upload`、`/api/docs`；routers/knowledge_bases.py、documents.py | KB 创建、文档上传、按 user/kb 过滤；本项目增加 user 维度 |
| 文档解析与入库 | knowledge/initializer, add_documents；extract_numbered_items | services/ingest_tasks.py、ingest.py、text_extraction.py | 上传后后台解析与切分，向量+BM25；预留编号条目抽取 |
| 混合检索 RAG | services/rag（hybrid=graph+vector） | `/api/qa`；services/qa.py、lexical.py、core/vectorstore.py | 本项目为 dense+BM25 混合；DeepTutor 为 graph+vector，均属 RAG 混合+可追溯引用 |
| 结构化输出 | 各 Agent 产出 JSON/约定结构 | schemas.py；summary/keypoints/qa/quiz 响应结构 | 摘要/要点/问答/测验均结构化，便于前端与缓存 |
| 摘要与知识点 | guide/summary_agent、locate_agent（学习计划） | `/api/summary`、`/api/keypoints`；services/summary.py、keypoints.py | 单文档摘要+要点；增强为要点带讲解+来源 |
| 测验生成与评分 | agents/question（Custom）；tools/question/exam_mimic（Mimic） | `/api/quiz/generate`、`/api/quiz/submit`；services/quiz.py | MCQ+解析+得分；补充模拟真题（参考试卷/风格） |
| 会话与进度跟踪 | solve/citation_memory；notebook/records | `/api/chat/sessions`、`/api/chat/sessions/{id}/messages`、`/api/progress`、`/api/activity` | 会话绑定 kb/doc，消息含 sources；进度与活动流 |
| 模型与检索配置 | config/main.yaml、agents.yaml | backend/.env、core/config.py | LLM/Embedding 切换，检索参数与权重 |

---

## P0（需求五模块 + DeepTutor 重合必做/建议做）

### 1. 文档上传与解析
- [x] **知识库/文档上传与解析**
  - 范围：PDF/TXT/MD 上传、KB 创建、增量添加、结构化元数据（页码/来源）
  - 方案：上传只落盘，解析/向量化走后台任务
  - 预留扩展：Docx/图片解析延后；**编号条目抽取**（Definition/Theorem 等，对标 DeepTutor extract_numbered_items）为可选扩展
  - 验收标准：
    - `POST /api/kb` 可创建 KB，重复名称返回已存在记录
    - `POST /api/docs/upload` 返回 `doc_id`，状态为 `processing`/`ready`
    - `GET /api/docs?user_id=...` 能看到文档 `status`/`num_pages`/`num_chunks`
    - 解析完成后 `status=ready`，错误时 `status=error` 且 `error_message` 非空

### 2. 知识点摘要生成
- [x] **单文档摘要**
  - 范围：按文档生成摘要，支持缓存与强制刷新
  - 验收标准：`POST /api/summary` 返回 `summary` 与 `cached`；重复请求可命中缓存
- [x] **单文档要点列表（keypoints）**
  - 范围：按文档抽取要点列表，支持缓存
  - 验收标准：`POST /api/keypoints` 返回非空 `keypoints` 列表与 `cached`
- [x] **知识点摘要增强（结构化+讲解+来源）**
  - 范围：在要点基础上增加**简短讲解或步骤**、**来源定位**（doc_id/page/chunk 或段落），对标 DeepTutor 知识简化
  - 方案：keypoints 响应扩展为每项含 `text`、可选 `explanation`、可选 `source`/`page`/`chunk`；或单独接口，先文本形态
  - 验收标准：
    - 知识点摘要可直接用于前端展示（至少纯文本列表，可选讲解与来源）
    - 对同一文档重复请求可命中缓存（`cached=true`）

### 3. 智能问答
- [x] **RAG 问答 + 可追溯引用**
  - 范围：KB/文档级检索，top_k/fetch_k 可配置，返回 answer 与 sources
  - 方案：Hybrid（Dense + BM25），MMR 可选
  - 验收标准：
    - `POST /api/qa` 返回 `answer` 与 `sources`（含 `source`/`snippet`/`doc_id`）
    - 检索不到时 `answer` 为明确“无法找到相关内容”提示
- [x] **会话与进度持久化**
  - 范围：会话绑定 kb/doc，消息存储与拉取，进度与活动统计
  - 验收标准：
    - `POST /api/chat/sessions` 可创建会话并绑定 `kb_id`/`doc_id`
    - `GET /api/chat/sessions/{id}/messages` 可拉取完整对话
    - `GET /api/progress?user_id=...` 返回统计字段齐全（含 by_kb）
- [x] **问答会话增强（sources 持久化 + 多轮历史）**
  - 范围：带 `session_id` 的问答将当轮 **answer + sources** 写入该会话；拉取消息时返回每条消息的 **sources**；生成回答时使用**最近 N 轮对话**作为 history
  - 验收标准：
    - `POST /api/qa` 带 `session_id` 时，对应会话新增消息且包含 sources
    - `GET /api/chat/sessions/{id}/messages` 中每条消息可含 `sources`
    - 多轮对话时 LLM 上下文包含历史轮次

### 4. 自动组卷与测验
- [x] **练习/测验生成与提交**
  - 范围：基于文档生成 MCQ、难度/数量可配，提交后返回得分与解析
  - 验收标准：
    - `POST /api/quiz/generate` 返回 `quiz_id` 与题目列表，每题含 `question`/`options`/`answer_index`/`explanation`
    - `POST /api/quiz/submit` 返回 `score`/`correct`/`total`/`results`/`explanations`
- [x] **模拟真题风格（对标 DeepTutor Mimic）**
  - 范围：参考试卷/题目或风格描述 → 生成**风格与难度相近**的题目
  - 方案：支持上传参考试卷 PDF 或传入题目文本/风格提示词；解析或抽取参考题后，按参考题生成新题（保持题型与难度，改情境或数字）
  - 验收标准：
    - 支持传入**风格提示词或模板**生成题目，和/或
    - 支持**参考试卷/题目**输入，生成与参考风格/难度相近的题目列表

### 5. 用户学习进度跟踪
- [x] **进度与活动流**
  - 范围：按用户/KB 的统计、活动流（上传/摘要/要点/问答/测验）
  - 验收标准：`GET /api/progress` 返回完整结构且含 `by_kb`；`GET /api/activity` 返回活动流列表（items）。
- [x] **个性化推荐（按 KB）**
  - 范围：基于文档完成度生成下一步动作
  - 验收标准：`GET /api/recommendations?user_id=...&kb_id=...` 返回每文档 `actions`

---

## P1（DeepTutor 已有但超出需求五模块）

- [ ] **多代理求解**（DeepTutor 对应：Problem Solving & Assessment）
  - 范围：RAG/Web Search/代码执行等工具与多 Agent 链路；仅保留工具注册接口也可
  - 预留扩展：可插拔工具协议与日志结构
- [ ] **Deep Research**（DeepTutor 对应：Research & Learning）
  - 范围：规划→检索→报告；任务表 + 状态机骨架，可仅手动触发
  - 预留扩展：自动检索能力
- [ ] **Idea Generation**（DeepTutor 对应：IdeaGen）
  - 范围：流水线配置与输入输出协议，可不实现多阶段筛选
  - 预留扩展：复用知识点结果
- [ ] **个人笔记本/记忆系统**（DeepTutor 对应：Personal Notebook）
  - 范围：notebook 列表 + 记录类型（solve/question/research/co_writer/chat），会话/解题/出题等可归档到笔记本
  - 预留扩展：notes 表 + KB/doc 关联，自动归档与总结
- [ ] **知识图谱与向量检索统一底座**（DeepTutor 对应：Knowledge Graph + Vector）
  - 范围：graph_storage 或图谱接口预留，可不做图谱构建
  - 预留扩展：图谱索引与检索融合
- [ ] **协作写作**（DeepTutor 对应：Co-Writer）
  - 范围：协作文档/版本/评论结构，可不做实时协作
  - 预留扩展：实时协作编辑
- [ ] **（高级）题目生成**（DeepTutor 对应：Question 模块进阶）
  - 范围：多轮检索/与知识库或难度挂钩、RelevanceAnalyzer 式分类，与 P0 基础出题区分

---

## P2（需求内权重较低 / 可选）

- [ ] **细粒度学习画像与自适应难度**
  - 范围：user_profile 字段（theta/ability/weak_concepts）；先静态指标
  - 预留扩展：自适应策略；对标 DeepTutor 个性化出题
- [ ] **数据分析与指标看板**
  - 范围：统计视图 + CSV/JSON 导出 API
  - 预留扩展：可视化图表