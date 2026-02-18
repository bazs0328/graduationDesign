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
- [x] **细粒度学习画像与自适应难度**
  - 范围：user_profile 字段（theta/ability/weak_concepts）；自适应策略与过难回调；对标 DeepTutor 个性化出题
  - 验收标准：画像落库可查；测验根据画像自动调难度；过难回调生效；前端展示画像与推荐

---

## 前端整体重构（P1 前）

- [x] **前端整体重构与 UI 美化**
  - 范围：参考 `tmp/DeepTutor/web` 的架构与视觉，对 `web/` 前端进行重构；Vue Router + Tailwind v4 + 侧栏布局，多视图（Home / Upload / Summary / Q&A / Quiz / Progress）；色调与视觉效果参考 DeepTutor，默认亮色、活力蓝主色、渐变 Hero、卡片与侧栏优化。
  - 验收标准：结构清晰、视觉统一、关键流程可用；界面亮丽美观。

---

## 个性化体验增强（毕设展示亮点）

> **目标**：强化"个性化"的可感知度，提升毕设答辩时的展示效果。
> **优先级**：P0.5 为高价值且实现可行的改进；P1.5 为时间充裕时可做的增强。

### P0.5（高展示价值，强烈推荐）

- [x] **学习画像可视化增强**
  - 范围：将当前文本/数字形式的画像升级为可视化图表
  - 方案：
    - 在 `LearnerProfileCard.vue` 中增加 ECharts/Chart.js 雷达图
    - 展示维度：理解力（recent_accuracy）、稳定性（1 - frustration）、活跃度（total_attempts）、进步趋势（theta 变化）
    - 薄弱知识点以标签云或高亮列表展示
  - 验收标准：
    - 雷达图展示至少 4 个能力维度
    - 挫败感指标有直观的进度条/仪表盘
    - 薄弱知识点可点击跳转到相关学习入口
  - 展示价值：⭐⭐⭐⭐⭐（直观体现"个性化画像"）

- [x] **知识点掌握度追踪与可视化**
  - 范围：按文档/KB 追踪各知识点的掌握程度，以图谱或树状结构展示
  - 方案：
    - 后端：在 keypoints 或新表中增加 `mastery_level` 字段（0-1），测验后根据对应知识点的答题情况更新
    - 前端：知识点列表带掌握度着色（绿=掌握/黄=部分/红=待学习），或用节点图展示关联
  - 验收标准：
    - 知识点列表/图谱有掌握度可视化
    - 点击未掌握知识点可跳转到测验/问答入口
    - `GET /api/keypoints` 响应含 `mastery_level`（可选）
  - 展示价值：⭐⭐⭐⭐⭐（直观体现"知识掌握追踪"）

- [x] **测验反馈增强与能力变化展示**
  - 范围：测验提交后展示能力值变化动画、错题归类、针对性练习推荐
  - 方案：
    - 后端：`/api/quiz/submit` 响应增加 `profile_delta`（theta/ability/frustration 变化量）
    - 前端：提交后展示 "能力值 +0.1 ↑" 动画，错题按知识点分组
  - 验收标准：
    - 提交测验后有能力变化的视觉反馈（数字动画/图标）
    - 错题按知识点归类展示
    - 提供"针对薄弱点再练"按钮，点击自动生成针对性测验
  - 展示价值：⭐⭐⭐⭐（直观体现"自适应反馈"）

- [x] **自适应问答深度**
  - 范围：根据学习者 `ability_level` 调整问答回复的深度、用词与风格
  - 方案：
    - 后端：`qa.py` 在生成 prompt 时注入学习者画像信息
    - beginner：用简单易懂的语言，避免专业术语，多举例子
    - intermediate：正常深度，适当使用术语并解释
    - advanced：可使用专业术语，提供深入分析和扩展阅读建议
  - 验收标准：
    - 同一问题对不同水平学习者回复风格有明显差异
    - 初学者回答避免过多术语；高手回答可引用更多扩展内容
    - 可通过切换用户/重置画像验证差异
  - 展示价值：⭐⭐⭐⭐（体现"问答个性化"）

- [x] **跨文档学习路径推荐**
  - 范围：基于知识点依赖关系与掌握度，推荐跨文档的学习顺序
  - 方案：
    - 后端：`/api/recommendations` 增加 `learning_path` 字段，包含建议学习顺序
    - 前端：展示 "建议先学习 A 文档的 X 知识点，再学习 B 文档的 Y"
  - 验收标准：
    - 推荐接口返回 `learning_path`（有序列表）
    - 前端展示学习路径卡片或流程图
    - 点击路径节点可跳转到对应学习入口
  - 展示价值：⭐⭐⭐⭐（体现"学习规划个性化"）

### P1.5（可选增强，时间充裕时）

- [ ] **引导式学习模块**（参考 DeepTutor Guide）
  - 范围：知识点定位 → 交互式讲解页面 → 学习完成总结
  - 方案：
    - 分析文档生成 3-5 个递进知识点学习计划
    - 每个知识点生成可交互的讲解内容
    - 学习完成后生成个性化总结
  - 验收标准：
    - `POST /api/guide/start` 启动引导式学习
    - 前端展示知识点进度条与当前学习内容
    - 完成后展示掌握度评估与建议

- [ ] **学习目标与计划设定**
  - 范围：用户可设定学习目标（如"一周内掌握微积分基础"），系统基于目标规划学习计划
  - 方案：
    - 新增 `learning_goals` 表（user_id, goal_text, target_date, progress）
    - 根据目标与当前画像生成每日学习任务
  - 验收标准：
    - 用户可创建/编辑学习目标
    - 系统生成每日任务清单
    - 展示目标完成进度

- [ ] **学习时间统计与趋势**
  - 范围：记录每日/周学习时长，展示活跃度曲线
  - 方案：
    - 活动记录增加 `duration` 字段
    - `GET /api/progress` 增加 `daily_stats` / `weekly_stats`
  - 验收标准：
    - 前端展示学习时间热力图或折线图
    - 显示"本周学习 X 小时，较上周 +Y%"

- [ ] **成就与激励系统**
  - 范围：完成学习里程碑获得徽章/成就
  - 方案：
    - 新增 `achievements` 表（user_id, type, earned_at）
    - 定义成就类型：首次上传、首次测验、连续学习 7 天、正确率达 90% 等
  - 验收标准：
    - 触发成就时有弹窗/通知
    - Progress 页面展示已获得成就徽章

---

## 用户体验优化（答辩演示流畅度）

> **目标**：功能已齐备，补齐"用起来顺畅"的最后一层皮；核心问题 = **反馈少**（成功无提示、失败无反馈、加载无状态、跳转无上下文）。  
> **优先级**：UX-P0 做一次全站受益 > UX-P1 关键交互打磨 > UX-P2 细节锦上添花。

### UX-P0（全局基础设施，做一次全站受益）

- [x] **全局 Toast / Notification 组件**
  - 现状：操作成功无反馈；错误靠 `console.error` 或混在内容区（`summary.value = '错误：' + err.message`）；问答报错混在聊天气泡里
  - 方案：封装全局 Toast 组件（success / error / warning / info），通过 `provide/inject` 或 Pinia 暴露 `showToast()` 给全站使用
  - 验收标准：
    - 上传成功、创建 KB、生成摘要、提交测验等操作均有 Toast 反馈
    - API 错误统一拦截并弹出 error Toast，不再混入内容区
    - Toast 自动消失（3-5 秒），error 类型可手动关闭

- [ ] **统一 Loading 状态组件**
  - 现状：各页面 loading 风格不统一（spinner / 文字 / 动画 / 无），部分操作无 loading（如 `refreshKbs()`）
  - 方案：封装可复用 Loading 组件（全屏遮罩 / 内联 spinner / 骨架屏三种模式），替换各页面零散实现
  - 验收标准：
    - 所有异步操作期间有统一视觉的 loading 指示
    - 长时操作（摘要生成、测验生成）有全屏或区域 loading 遮罩
    - 首次进入页面有骨架屏或 spinner（替代空白等待）

- [ ] **引入 Pinia 全局状态管理**
  - 现状：无状态管理，各页面独立获取 KB 列表 / 用户信息 / 文档列表；页面跳转后状态丢失；数据重复请求且不同步
  - 方案：
    - `stores/user.js` — 登录态、用户信息、画像
    - `stores/kb.js` — KB 列表、当前选中 KB、文档列表
    - `stores/ui.js` — 主题偏好、侧栏折叠等 UI 状态
  - 验收标准：
    - KB / 文档列表全站共享，任一页面修改后其他页面自动同步
    - 用户信息登录后仅拉取一次，全站可访问
    - 页面跳转不丢失已选 KB / 文档上下文

### UX-P1（关键交互打磨，演示流畅度）

- [ ] **页面间上下文传递**
  - 现状：跳转时不传参（如 Summary → Quiz 不带 `doc_id`），用户到新页面需重新选择
  - 方案：
    - 路由跳转时携带 `query` 参数（`doc_id` / `kb_id`）
    - 目标页面 `onMounted` 读取 query 并自动选中对应项
    - 结合 Pinia store，优先使用全局已选状态
  - 验收标准：
    - Summary 页"去做测验"→ Quiz 页自动选中当前文档
    - Quiz 页"去问答"→ QA 页自动选中当前 KB 与文档
    - Progress 页点击 KB 统计 → 跳转到对应 KB 的文档列表

- [ ] **空状态引导优化**
  - 现状：多个页面空数据时仅显示"暂无"，新用户不知下一步该做什么
  - 方案：统一空状态组件（图标 + 说明文字 + 行动按钮），按场景定制：
    - 无 KB：「还没有知识库，创建第一个开始学习」+ 创建按钮
    - 无文档：「上传第一份学习资料」+ 上传按钮
    - 无摘要/知识点：「选择文档生成摘要」
    - 无测验记录：「来一次测验检验学习效果」
  - 验收标准：
    - 所有列表 / 内容区的空状态有引导文案和跳转按钮
    - 新注册用户首次进入各页面均能明确知道下一步操作

- [ ] **危险操作二次确认**
  - 现状：清空对话、删除文档等操作无确认，演示时易误触
  - 方案：封装 ConfirmDialog 组件（或用 `window.confirm` 过渡），对清空 / 删除 / 重置类操作添加确认
  - 验收标准：
    - 清空对话、删除文档、重置画像等操作均弹出确认
    - 确认框文案明确说明操作后果（"此操作不可撤销"）

- [ ] **操作成功反馈补全**
  - 现状：创建 KB、上传文档、生成摘要等成功后仅刷新数据，无明确提示
  - 方案：结合 Toast 系统，在关键操作成功后弹出提示并（可选）自动跳转
  - 验收标准：
    - 所有「创建 / 上传 / 生成 / 提交」操作成功后有 Toast 反馈
    - 部分操作成功后可自动跳转到下一步（如上传成功→提示"去生成摘要"）

### UX-P2（细节打磨，锦上添花）

- [ ] **表单验证增强**
  - 范围：登录/注册页的实时校验（用户名长度、密码强度、确认密码一致性）；上传页的文件类型/大小前端校验
  - 验收标准：输入时实时显示校验状态；不合规时按钮禁用并显示原因

- [ ] **文件上传进度显示**
  - 范围：大 PDF 上传时展示进度条（使用 `XMLHttpRequest` 或 `fetch` + `ReadableStream` 获取上传进度）
  - 验收标准：上传过程中有进度百分比和进度条；上传完成后切换为"解析中"状态

- [ ] **响应式布局适配**
  - 范围：QA 侧栏（固定 `w-72`）在小屏下的折叠；Quiz 网格布局在窄屏下改为单列；投影仪 / 低分辨率兼容
  - 验收标准：1024px 及以上正常展示；768px 以下侧栏自动收起、关键内容不溢出

- [ ] **主题偏好持久化**
  - 范围：暗色/亮色切换结果写入 `localStorage`，刷新后保持
  - 验收标准：切换主题 → 刷新页面 → 主题不变

- [ ] **输入防抖与请求优化**
  - 范围：QA 提问输入防抖（避免意外连续提交）；搜索/筛选输入防抖（300ms）
  - 验收标准：快速连续点击提交只发送一次请求；搜索框停止输入后才触发检索

- [ ] **长列表分页 / 虚拟滚动**
  - 范围：文档列表、活动流、消息历史等长列表的分页或虚拟滚动
  - 验收标准：列表超过一定条数时分页或懒加载；滚动流畅不卡顿

---

## 项目差异化亮点（答辩可强调）

| 特性 | DeepTutor | 本项目 | 说明 |
| --- | --- | --- | --- |
| 学习画像持久化 | 会话级 | ✅ 用户级持久化（SQLite） | 画像跨会话保留 |
| 自适应难度算法 | 未见明确实现 | ✅ 基于 IRT/frustration 的难度计划 | `generate_difficulty_plan` |
| 挫败感检测与回调 | 无 | ✅ 连续低分触发难度降级 | `frustration_score` 机制 |
| 轻量部署 | 依赖较多 | ✅ SQLite + Chroma 单机可跑 | 无需外部数据库 |
| 用户维度隔离 | 单用户 | ✅ 多用户 KB/文档/画像隔离 | `user_id` 贯穿全链路 |

---

## P2（DeepTutor 已有但超出需求五模块）

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

## P3（需求内权重较低 / 可选）

- [ ] **数据分析与指标看板**
  - 范围：统计视图 + CSV/JSON 导出 API
  - 预留扩展：可视化图表