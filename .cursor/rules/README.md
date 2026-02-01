# Cursor Rules 说明

本目录包含 GradTutor 项目使用的 Cursor 规则（`.mdc`），用于约束 AI 助手行为与编码风格。

## 规则来源与分类

### 项目专属（优先遵循）

| 规则 | 说明 |
|------|------|
| project-context | 项目目标、TODO 优先级、目录结构 |
| backend-conventions | 后端分层、API、DB 约定 |
| frontend-conventions | 前端 api.js、错误处理、与需求模块对应 |
| git-task-branch | feat 分支流程、合并与清理 |

### araguaci/cursor-skills 提炼

| 规则 | 说明 | 作用范围 |
|------|------|----------|
| python-fastapi | FastAPI、PEP、async、测试 | backend/**/*.py, tests/**/*.py |
| vue-web | Vue 3、Composition API、a11y | web/**/*.{vue,js,css} |
| testing | pytest、vitest、Playwright、smoke | tests/**/* |

### DVC2/cursor_prompts

| 规则 | 说明 |
|------|------|
| memory-management | 上下文分层、智能修剪 |
| session-coordinator | 会话延续、上下文传递 |
| development-journal | 决策与流程记录 |
| ADR | 架构决策记录自动化 |
| debugging | 调试效率、工具调用优化 |
| efficiency | 减少工具调用、资源使用 |
| commonsense | 常见错误避免、最佳实践 |
| terminal | 终端操作规范 |
| javascript | JS ES2022+ 规范 |
| typescript | TS 类型与模式 |
| audit | 代码质量与审计 |

## 参考来源

- **cursor_prompts/**：DVC2/cursor_prompts（已克隆）
- **cursor-skills/**：araguaci/cursor-skills（已克隆）
