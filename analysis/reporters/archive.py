"""report.archive 子任务：归档 HTML + JSON（REQ 第 5 章 / DESIGN §10）"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from analysis.core import config
from analysis.core.registry import SPECS_BY_NAME, register
from analysis.reporters.json_report import build_report


def archive_dir(org: str, repo: str) -> Path:
    return config.REPORTS_DIR / org / repo / "analysis"


def _update_latest(out_dir: Path, ts: str) -> None:
    """latest.html / latest.json 符号链接（沿用 audit symlink 模式）"""
    for ext in ("html", "json"):
        link = out_dir / f"latest.{ext}"
        target = f"{ts}.{ext}"
        try:
            link.unlink(missing_ok=True)
            link.symlink_to(target)
        except OSError:
            pass  # 链接失败不影响归档主产物


@register("report.archive")
def archive_handler(ctx) -> dict:
    # 收集全部子任务产物
    outputs = {}
    for name, spec in SPECS_BY_NAME.items():
        if spec.output_file:
            outputs[name] = ctx.read_dependency_output(name)

    task = ctx.task
    report = build_report(task, outputs)

    ts = datetime.fromisoformat(task.created_at).strftime("%Y%m%d_%H%M%S")
    out_dir = archive_dir(task.org, task.repo)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{ts}.json"
    html_path = out_dir / f"{ts}.html"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    from analysis.reporters.html_report import render_html
    warnings = render_html(report, html_path)

    _update_latest(out_dir, ts)

    # 回填 task.report：直接改 ctx.task（与 orchestrator 持有同一对象），
    # 由 orchestrator 在子任务完成后统一落盘——避免自行 save 被后续保存覆盖
    task.report = {"html": str(html_path), "json": str(json_path)}
    ctx.log(f"归档完成: {html_path}")

    return {
        "html": str(html_path),
        "json": str(json_path),
        "html_size_bytes": html_path.stat().st_size,
        "warnings": warnings,
    }
