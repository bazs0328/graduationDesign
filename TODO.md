# TODO（DeepTutor 优先）

> 规则：DeepTutor 已有的功能优先级更高；DeepTutor 未覆盖的功能优先级更低。

## DeepTutor 实现思路对照（本项目落点）
| DeepTutor 思路 | 本项目落点（接口/模块） | 说明 |
| --- | --- | --- |
| 知识库与多文档管理 | `/api/kb`、`/api/docs/upload`、`/api/docs`；`backend/app/routers/knowledge_bases.py`、`backend/app/routers/documents.py` | 支持 KB 创建、文档上传、按 user/kb 过滤列表 |
| 文档解析与入库 | `backend/app/services/ingest_tasks.py`、`backend/app/services/ingest.py`、`backend/app/services/text_extraction.py` | 上传后后台解析与切分，落盘到 `backend/data/users/<user_id>/` |
| 混合检索 RAG 问答 | `/api/qa`；`backend/app/services/qa.py`、`backend/app/services/lexical.py`、`backend/app/core/vectorstore.py` | 语义检索 + 关键词检索融合，返回引用片段与来源 |
| 摘要与知识点 | `/api/summary`、`/api/keypoints`；`backend/app/services/summary.py`、`backend/app/services/keypoints.py` | 支持缓存与结构化输出，便于前端展示 |
| 测验生成与评分 | `/api/quiz/generate`、`/api/quiz/submit`；`backend/app/services/quiz.py` | 以 MCQ 为主，返回解析与得分 |
| 会话与进度跟踪 | `/api/chat/sessions`、`/api/chat/sessions/{id}/messages`、`/api/progress`、`/api/activity` | 会话上下文、学习进度统计、活动流 |
| 模型与检索配置 | `backend/.env`、`backend/app/core/config.py` | LLM/Embedding 供应商切换、检索参数与权重配置 |

## P0（DeepTutor 已有且与需求重合）
- [x] 知识库/文档上传与解析
  - 范围：PDF/TXT/MD 上传、KB 创建、增量添加、结构化元数据（页码/来源）
  - 方案：上传只落盘，解析/向量化走后台任务
  - 复杂度权衡：先做文本+PDF，Docx/图片解析延后
  - 预留扩展：保留 `content_list/` 与 `images/` 作为多模态解析产物
  - 验收标准：
    - `POST /api/kb` 可创建 KB，重复名称返回已存在记录
    - `POST /api/docs/upload` 返回 `doc_id`，状态为 `processing/ready`
    - `GET /api/docs?user_id=...` 能看到文档 `status/num_pages/num_chunks`
    - 文档解析完成后 `status=ready`，错误时 `status=error` 且 `error_message` 非空
- [x] 大规模文档知识问答（RAG + 可追溯引用）
  - 范围：KB 级检索过滤 + top_k/fetch_k 可配置
  - 方案：MMR + Hybrid（Dense + BM25），保留 rerank 钩子
  - 复杂度权衡：不做多阶段检索/重排，仅保留接口与配置位
  - 预留扩展：后处理钩子 + 评测入口
  - 验收标准：
    - `POST /api/qa` 返回 `answer` 与 `sources`（含 `source/snippet/doc_id`）
    - `top_k/fetch_k` 参数可调且不报错
    - 若检索不到内容，`answer` 返回明确的“无法找到相关内容”提示
- [ ] 个性化学习交互（会话/进度持久化）
  - 范围：会话与消息记录；按用户/KB 聚合统计
  - 方案：会话绑定 KB/doc，上下文可复用
  - 复杂度权衡：不做个性化推荐，仅做持久化与统计
  - 预留扩展：会话 metadata（策略/难度/推荐来源）
  - 验收标准：
    - `POST /api/chat/sessions` 可创建会话并绑定 `kb_id/doc_id`
    - `POST /api/qa` 带 `session_id` 可写入对话历史
    - `GET /api/chat/sessions/{id}/messages` 可拉取完整对话
    - `GET /api/progress?user_id=...` 返回统计字段齐全
- [ ] 知识点简化与讲解
  - 范围：结构化要点 + 简要讲解 + 来源定位
  - 方案：基于 `content_list/` 或 numbered items 抽取
  - 复杂度权衡：先输出文本要点，不做可视化
  - 预留扩展：层级字段支持后续可视化
  - 验收标准：
    - `POST /api/keypoints` 返回非空 `keypoints` 列表
    - 结构化要点可直接用于前端展示（至少纯文本列表）
    - 对同一文档重复请求可命中缓存（`cached=true`）
- [ ] 练习/测验生成
  - 范围：基于知识点生成题目 + 解析；难度/数量控制
  - 方案：MCQ + 简答为主
  - 复杂度权衡：不做题库检索
  - 预留扩展：题型字段与评分策略扩展
  - 验收标准：
    - `POST /api/quiz/generate` 返回 `quiz_id` 与题目列表
    - 每题含 `question/options/answer_index/explanation`
    - `POST /api/quiz/submit` 返回 `score/correct/total/results/explanations`
- [ ] 模拟真题风格
  - 范围：上传参考试卷 → 风格提示词/模板 → 题目生成
  - 方案：先手动风格提示词
  - 复杂度权衡：不做自动风格学习
  - 预留扩展：style_profile 存储结构
  - 验收标准：
    - 支持传入风格提示词（或模板）生成题目
    - 风格提示词可在请求或配置中切换

## P1（DeepTutor 已有但超出当前范围）
- [ ] 多代理求解（RAG/Web Search/代码执行）与实时推理展示
  - 范围：仅保留工具注册接口
  - 复杂度权衡：不实现 agent 链路
  - 预留扩展：可插拔工具协议与日志结构
- [ ] Deep Research（规划→检索→报告）
  - 范围：任务表 + 状态机骨架
  - 复杂度权衡：只支持手动触发
  - 预留扩展：自动检索能力
- [ ] Idea Generation（多阶段筛选）
  - 范围：流水线配置 + 输入输出协议
  - 复杂度权衡：不实现多阶段筛选
  - 预留扩展：复用知识点结果
- [ ] 个人笔记本/记忆系统
  - 范围：notes 表 + KB/doc 关联
  - 复杂度权衡：仅手动保存
  - 预留扩展：自动归档与总结
- [ ] 知识图谱与向量检索统一底座
  - 范围：graph_storage 目录 + 图谱接口预留
  - 复杂度权衡：不做图谱构建
  - 预留扩展：图谱索引与检索融合
- [ ] 协作写作（Co-writer）
  - 范围：协作文档/版本/评论结构
  - 复杂度权衡：不做实时协作
  - 预留扩展：实时协作编辑

## P2（需求内但权重较低）
- [ ] 细粒度学习画像与自适应难度
  - 范围：user_profile 字段（theta/ability/weak_concepts）
  - 复杂度权衡：先静态指标
  - 预留扩展：自适应策略
- [ ] 数据分析与指标看板
  - 范围：统计视图 + CSV/JSON 导出 API
  - 复杂度权衡：先基础统计
  - 预留扩展：可视化图表
