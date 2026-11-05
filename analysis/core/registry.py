"""子任务注册表（对应 ANALYSIS-DESIGN.md §3.1）

15 个子任务：9 个确定性采集（det）+ 4 个 AI（ai）+ scoring（det）+ report.archive（det）。
handler 由各模块实现后通过 @register 注册；未注册时：
- mock 模式 → sleep 模拟（M1 联调）
- 正常模式 → SubtaskNotImplemented（子任务 failed，可 retry）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from analysis.core import config


class SubtaskNotImplemented(Exception):
    pass


@dataclass(frozen=True)
class SubtaskSpec:
    name: str
    type: str                              # "det" | "ai"
    deps: tuple[str, ...] = ()
    timeout: int = config.DET_SUBTASK_TIMEOUT
    output_file: str = ""                  # 相对任务目录的产物路径
    always_run: bool = False               # 上游失败仍执行（REQ 第 7 章容错）
    description: str = ""


# DAG 定义（顺序即默认展示顺序；执行顺序由拓扑排序决定）
_BASE_SPECS: tuple[SubtaskSpec, ...] = (
    SubtaskSpec("collect.overview", "det", (),
                output_file="collected/overview.json",
                description="仓库概述元数据（gh api + git，REQ §3.1）"),
    SubtaskSpec("collect.structure", "det", (),
                output_file="collected/structure.json",
                description="代码结构：行数/目录统计（REQ §3.2）"),
    SubtaskSpec("collect.git_context", "det", (),
                output_file="collected/git_context.json",
                description="commit 消息摘要（供 AI 还原，不含作者信息）"),
    SubtaskSpec("collect.dependencies", "det", ("collect.structure",),
                output_file="collected/dependencies.json",
                description="依赖清单与依赖图（REQ §3.3）"),
    SubtaskSpec("collect.quality", "det", ("collect.structure",),
                output_file="collected/quality.json",
                description="代码质量：audit lint 桥接 + 复杂度（REQ §3.4）"),
    SubtaskSpec("collect.security", "det", ("collect.dependencies",),
                output_file="collected/security.json",
                description="安全：audit 桥接 + OSV + 启发式（REQ §3.5）"),
    SubtaskSpec("collect.performance", "det", ("collect.structure",),
                output_file="collected/performance.json",
                description="静态性能反模式（REQ §3.6）"),
    SubtaskSpec("collect.docs", "det", ("collect.structure",),
                output_file="collected/docs.json",
                description="文档与注释统计（REQ §3.7）"),
    SubtaskSpec("collect.tests", "det", ("collect.structure",),
                output_file="collected/tests.json",
                description="测试清点与静态评估（REQ §3.8）"),

    SubtaskSpec("ai.architecture", "ai",
                ("collect.structure", "collect.dependencies", "collect.git_context"),
                timeout=config.AI_SUBTASK_TIMEOUT,
                output_file="ai/architecture.json",
                description="架构分析（AI，REQ §3.9）"),
    SubtaskSpec("ai.business_knowledge", "ai",
                ("collect.structure", "collect.git_context", "collect.docs"),
                timeout=config.AI_SUBTASK_TIMEOUT,
                output_file="ai/business_knowledge.json",
                description="业务知识还原与接手就绪度（AI，REQ §3.10）"),
    SubtaskSpec("ai.conclusions", "ai",
                ("collect.overview", "collect.structure", "collect.dependencies",
                 "collect.quality", "collect.security", "collect.performance",
                 "collect.docs", "collect.tests"),
                timeout=config.AI_SUBTASK_TIMEOUT,
                output_file="ai/conclusions.json",
                description="各维度结论与改进建议（AI，REQ §4.4）"),

    SubtaskSpec("scoring", "det", ("ai.architecture", "ai.business_knowledge"),
                output_file="collected/scoring.json",
                description="健康度评分（REQ §3.11）"),
    SubtaskSpec("ai.summary", "ai", ("scoring", "ai.conclusions"),
                timeout=config.AI_SUBTASK_TIMEOUT,
                output_file="ai/summary.json", always_run=True,
                description="执行摘要与问题清单（AI，REQ §3.11）"),

)

# report.archive 依赖全部前序子任务
SUBTASK_SPECS: tuple[SubtaskSpec, ...] = _BASE_SPECS + (
    SubtaskSpec("report.archive", "det", tuple(s.name for s in _BASE_SPECS),
                output_file="", always_run=True,
                description="归档 HTML + JSON 报告（REQ 第 5 章）"),
)

SPECS_BY_NAME: dict[str, SubtaskSpec] = {s.name: s for s in SUBTASK_SPECS}

# ---------- handler 注册 ----------
Handler = Callable[[Any], dict]           # handler(ctx) -> 可 JSON 序列化结果
HANDLERS: dict[str, Handler] = {}


def register(name: str) -> Callable[[Handler], Handler]:
    """装饰器：注册子任务 handler"""
    if name not in SPECS_BY_NAME:
        raise KeyError(f"未声明的子任务: {name}")

    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return deco


# mock 模式下仍真实执行的子任务（评分 + 归档链路需要端到端验证）
MOCK_PASSTHROUGH = frozenset({"scoring", "report.archive"})


def resolve_handler(name: str, mock: bool = False) -> Handler:
    """解析 handler。

    mock 语义（流水线联调）：
    - mock=True：除 MOCK_PASSTHROUGH（scoring/report.archive 走真实链路）外，
      全部子任务以 sleep 模拟——用于不触发真实采集与 AI 调用的端到端联调；
    - mock=False：使用注册 handler；未注册抛 SubtaskNotImplemented。
    测试注入：单元测试直接向 HANDLERS 注入 handler 且 task.mock=False。
    """
    if mock and name not in MOCK_PASSTHROUGH:
        def _mock_handler(ctx) -> dict:
            spec = SPECS_BY_NAME[name]
            time.sleep(1.5 if spec.type == "ai" else 0.5)
            return {"_mock": True, "subtask": name, "type": spec.type}
        return _mock_handler
    if name in HANDLERS:
        return HANDLERS[name]
    if mock:  # passthrough 子任务未注册时回退模拟
        def _mock_pt(ctx) -> dict:
            return {"_mock": True, "subtask": name}
        return _mock_pt
    raise SubtaskNotImplemented(f"子任务 handler 未实现: {name}")


def topo_order() -> list[str]:
    """Kahn 拓扑排序（稳定：同层按声明顺序）"""
    indegree = {s.name: len(s.deps) for s in SUBTASK_SPECS}
    children: dict[str, list[str]] = {s.name: [] for s in SUBTASK_SPECS}
    for s in SUBTASK_SPECS:
        for dep in s.deps:
            children[dep].append(s.name)

    ready = [s.name for s in SUBTASK_SPECS if indegree[s.name] == 0]
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for child in children[name]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(order) != len(SUBTASK_SPECS):
        raise ValueError("子任务 DAG 存在环")
    return order
