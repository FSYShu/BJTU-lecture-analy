"""后端启动入口。

Windows 上 uvicorn --reload / --workers>1 会强制 WindowsSelectorEventLoop，
而 Playwright async API 依赖 asyncio.create_subprocess_exec（仅 ProactorEventLoop
支持），二者不可兼得。故此处显式设 ProactorEventLoop 并单进程启动；
修改代码后需手动重启（Ctrl+C 后重新运行）。
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)