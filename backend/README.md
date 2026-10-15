# 交大课录智析 · 后端

FastAPI 后端，承载课程回放解析流水线与全部业务接口。

## 启动

```bash
cd backend
uv sync                              # 安装锁定依赖（首次）
uv run python scripts/init_db.py     # 初始化 SQLite 表
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

## 依赖管理

- 依赖定义在 `pyproject.toml`，精确版本由 `uv.lock` 锁定。
- 新增依赖：`uv add <pkg>`（会更新 `uv.lock`，需提交）。
- **不要**使用 `requirements.txt`，保证多电脑一致。

## 测试

```bash
uv run pytest
uv run ruff check app
uv run mypy app
```

## 目录

- `app/main.py`：FastAPI 入口
- `app/pipeline/`：解析流水线（下载→音频→ASR→大模型→持久化）
- `app/integrations/`：硅基流动 ASR/LLM / 课程平台对接
- `app/api/v1/`：REST 路由
- `app/db/models/`：ORM 模型（见 docs/03-data-model.md）

详细架构见根目录 `docs/`。