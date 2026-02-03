# 测试目录结构

后端 pytest 在此目录；前端单元与 E2E 测试在 `web/tests/` 下。

## 目录说明

| 目录/文件 | 说明 |
|-----------|------|
| `backend/` | 后端 pytest 集成测试 |
| `smoke/` | Smoke 测试脚本 |
| `qa_regression.py` | QA 回归测试 |
| `loadtest_qa.sh` | QA 压测脚本 |

## 前端测试（web/tests/）

| 目录 | 说明 |
|------|------|
| `web/tests/unit/` | Vitest 单元测试 |
| `web/tests/e2e/` | Playwright E2E 测试 |
| `web/tests/fixtures/` | E2E 测试用 fixture 文件 |

## 运行方式

- **后端**: `pytest` 或 `python -m pytest`
- **前端单元**: `cd web && npm test`
- **前端 E2E**: `cd web && npm run test:e2e`
- **Smoke**: `bash tests/smoke/dev_smoke.sh`（需后端已启动；可设置 `API_BASE`、`SMOKE_USER_ID`、`SMOKE_DOC_FILE`）
- **Windows 下运行 Smoke**：需在 **Git Bash** 或 **WSL** 中执行上述 bash 脚本；或设置环境变量后在同一环境下运行。
