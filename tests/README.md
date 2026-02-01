# 测试目录结构

所有测试相关文件集中在此目录（前端单元测试因 Vitest 需在 web 项目内，位于 `web/tests/unit/`）。

## 目录说明

| 目录/文件 | 说明 |
|-----------|------|
| `backend/` | 后端 pytest 集成测试 |
| `frontend/e2e/` | Playwright E2E 测试（需在 web 下运行 `npm run test:e2e`） |
| `frontend/fixtures/` | E2E 测试用 fixture 文件 |
| `smoke/` | Smoke 测试脚本 |
| `qa_regression.py` | QA 回归测试 |
| `loadtest_qa.sh` | QA 压测脚本 |

## 前端单元测试

Vitest 单元测试位于 `web/tests/unit/`，在 web 下运行 `npm test`。

## 运行方式

- **后端**: `pytest` 或 `python -m pytest`
- **前端单元**: `cd web && npm test`
- **前端 E2E**: `cd web && npm run test:e2e`
- **Smoke**: `bash tests/smoke/dev_smoke.sh`
