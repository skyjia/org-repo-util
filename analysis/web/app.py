"""FastAPI 应用（按需启动、用完即退；仅绑定 127.0.0.1，REQ §4.3）"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from analysis.core import config
from analysis.web.api import router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="仓库全面分析", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.include_router(router)
    # 归档报告静态服务（分析完成后从 Web 直接打开）
    if config.REPORTS_DIR.exists():
        app.mount("/reports", StaticFiles(directory=str(config.REPORTS_DIR)), name="reports")
    # 前端（mount 必须最后，避免吞掉 /api 路由）
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


def _port_busy(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((config.WEB_HOST, port)) == 0


def run_web(port: int = config.WEB_PORT, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    from analysis import __version__
    if _port_busy(port):
        raise RuntimeError(
            f"端口 {port} 已被占用——可能有旧 Web 服务进程在运行。"
            f"后端代码不热更新：请先结束旧进程（pkill -f 'analyze ui'）再启动，"
            f"或用 --port 换端口。当前代码版本 v{__version__}")

    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{config.WEB_HOST}:{port}")).start()

    print(f"🌐 Web 界面 v{__version__}: http://{config.WEB_HOST}:{port}"
          f"（ctrl-c 退出；退出不影响后台分析任务）")
    uvicorn.run(create_app(), host=config.WEB_HOST, port=port, log_level="warning")
