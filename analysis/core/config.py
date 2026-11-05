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

# ---------- 中断恢复与重试退避（REQ v6 第 7 章） ----------
HEARTBEAT_INTERVAL = 10         # daemon 心跳写入间隔（秒）
RETRY_DELAY_DET = 5             # 确定性子任务重试前退避（秒，容忍网络瞬断）
RETRY_DELAY_AI = 30             # AI 子任务重试前退避（秒）

# ---------- 多语言支持（M7，2026-11-05 用户确认决策） ----------
NO_CODE_THRESHOLD = 100         # 生产代码行低于此值 → 空仓库守护：跳过全部 AI 子任务
RUFF_SELECT = "E,F,W,S,B"       # ruff 规则集（S=bandit 安全规则，供 security 维度复用）
RUFF_TIMEOUT = 240
SHELLCHECK_TIMEOUT = 240
SHELLCHECK_MAX_FILES = 300      # shell 文件送检上限
FORK_POLICY_REJECT = True       # fork 仓库 start 预检拒绝（用户决策：完全不分析）

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
