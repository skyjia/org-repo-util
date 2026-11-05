"""全局配置：路径常量、超时、评分权重（对应 ANALYSIS-DESIGN.md §3/§7）"""

from pathlib import Path

# ---------- 路径 ----------
# analysis/core/config.py -> analysis -> org-repo-util
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = PROJECT_ROOT / "analysis"

STATE_DIR = ANALYSIS_ROOT / "state"
TASKS_DIR = STATE_DIR / "tasks"
WORKTREES_DIR = STATE_DIR / "worktrees"
DAEMON_PID_FILE = STATE_DIR / "daemon.pid"
DAEMON_LOG_FILE = STATE_DIR / "daemon.log"

REPOS_DIR = PROJECT_ROOT / "repos"
REPORTS_DIR = PROJECT_ROOT / "reports"

WEB_STATIC_DIR = ANALYSIS_ROOT / "web" / "static"

# ---------- daemon ----------
DAEMON_POLL_INTERVAL = 1.0      # 队列轮询间隔（秒）
DAEMON_IDLE_TTL = 1800          # 空闲自动退出（秒，默认 30min）

# ---------- 子任务超时与重试（REQ 第 7 章已决策） ----------
DET_SUBTASK_TIMEOUT = 300       # 确定性采集子任务：5 分钟
AI_SUBTASK_TIMEOUT = 1800       # AI 子任务：30 分钟
SUBTASK_MAX_ATTEMPTS = 2        # 首次执行 + 自动重试一次

# ---------- Web ----------
WEB_HOST = "127.0.0.1"          # 仅本机（REQ §4.3）
WEB_PORT = 8765

# ---------- 评分（REQ §3.11 已决策权重） ----------
SCORE_WEIGHTS = {
    "security": 15,
    "quality": 15,
    "business_knowledge": 15,
    "tests": 12,
    "architecture": 12,
    "docs": 10,
    "dependencies": 9,
    "structure": 6,
    "performance": 6,
}

# (最低分阈值, 等级)，从高到低匹配
GRADE_THRESHOLDS = [
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
    (0, "F"),
]

SCHEMA_VERSION = "1.0"
GENERATOR_NAME = "org-repo-util/analysis"


def ensure_dirs() -> None:
    """确保运行时目录存在（幂等）"""
    for d in (STATE_DIR, TASKS_DIR, WORKTREES_DIR):
        d.mkdir(parents=True, exist_ok=True)
