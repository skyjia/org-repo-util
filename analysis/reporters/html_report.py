"""自包含 HTML 报告渲染（REQ §5.2：JS 库内联、离线可打开、单文件可分享）

vendor 资源（web/static/vendor/）缺失时回退 CDN 引用并输出 warning（非自包含降级）。
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from analysis.core import config

TEMPLATE_DIR = Path(__file__).parent / "templates"
VENDOR_DIR = config.WEB_STATIC_DIR / "vendor"

VENDOR_FILES = {
    "echarts_js": ("echarts.min.js", "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"),
    "mermaid_js": ("mermaid.min.js", "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"),
}


def _load_vendor() -> tuple[dict, list[str]]:
    warnings = []
    assets = {}
    for key, (fname, cdn) in VENDOR_FILES.items():
        p = VENDOR_DIR / fname
        if p.exists():
            assets[key] = p.read_text(encoding="utf-8")
        else:
            assets[key] = None
            assets[f"{key}_cdn"] = cdn
            warnings.append(f"vendor 资源缺失 {fname}，回退 CDN 引用（报告非完全自包含）")
    return assets, warnings


def render_html(report: dict, out_path: Path) -> list[str]:
    """渲染归档 HTML，返回 warnings"""
    assets, warnings = _load_vendor()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"], default_for_string=True),
    )
    template = env.get_template("report.html.j2")

    # 内嵌 JSON：防 </script> 提前闭合
    data_json = json.dumps(report, ensure_ascii=False, default=str).replace("</", "<\\/")

    html = template.render(report=report, data_json=data_json, **assets)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return warnings
