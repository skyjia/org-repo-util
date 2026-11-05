"""AI 子任务 handler（ANALYSIS-DESIGN.md §6.2）

流程：读取前序采集产物 → 裁剪注入 prompt 模板 → claude headless 执行
→ JSON 提取 + jsonschema 校验 → 附 _ai_meta 落盘。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
from jinja2 import Environment, FileSystemLoader

from analysis.ai.engine import AIEngine
from analysis.core import config
from analysis.core.models import now_iso
from analysis.core.registry import register

AI_DIR = Path(__file__).parent
_jinja = Environment(loader=FileSystemLoader(str(AI_DIR / "prompts")))
ENGINE = AIEngine()

# engine subprocess 超时早于 orchestrator SIGALRM，保证超时走可重试异常路径
_ENGINE_GRACE = 60
_TRIM_LIMIT = 6000


def _prompt_version(name: str) -> str:
    tpl = (AI_DIR / "prompts" / f"{name}.md.j2").read_bytes()
    return hashlib.md5(tpl).hexdigest()[:8]


def _trim(obj, limit: int = _TRIM_LIMIT) -> str:
    """采集数据序列化为字符串并截断（控制 prompt 体积）"""
    if obj is None:
        return "null（前序采集缺失，结论中请如实标注数据缺失）"
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[:limit] + f"\n…（已截断，原始 {len(text)} 字符）"
    return text


def _validate(name: str, data: dict) -> None:
    schema = json.loads((AI_DIR / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)   # 校验失败抛 ValidationError → orchestrator 重试


def _run_ai(ctx, template: str, **variables) -> dict:
    ctx.log(f"AI 子任务启动: {template}（claude headless，只读工具白名单）")
    prompt = _jinja.get_template(f"{template}.md.j2").render(
        org=ctx.org, repo=ctx.repo, commit_sha=ctx.commit_sha, **variables)
    data = ENGINE.run(prompt, ctx.repo_path,
                      timeout=config.AI_SUBTASK_TIMEOUT - _ENGINE_GRACE)
    _validate(template, data)
    ctx.log(f"AI 子任务完成: {template}（输出通过 schema 校验）")
    data["_ai_meta"] = {
        "engine": "claude-code-headless",
        "prompt_version": _prompt_version(template),
        "generated_at": now_iso(),
        "nondeterministic": True,
        "note": "AI 生成内容，相同输入下不保证完全可复现（REQ §4.4）",
    }
    return data


@register("ai.architecture")
def ai_architecture(ctx) -> dict:
    return _run_ai(
        ctx, "architecture",
        structure_summary=_trim(ctx.read_dependency_output("collect.structure")),
        deps_summary=_trim(ctx.read_dependency_output("collect.dependencies"), 8000),
        git_summary=_trim(ctx.read_dependency_output("collect.git_context"), 4000))


@register("ai.business_knowledge")
def ai_business_knowledge(ctx) -> dict:
    return _run_ai(
        ctx, "business_knowledge",
        structure_summary=_trim(ctx.read_dependency_output("collect.structure"), 4000),
        docs_summary=_trim(ctx.read_dependency_output("collect.docs"), 4000),
        git_summary=_trim(ctx.read_dependency_output("collect.git_context"), 8000))


@register("ai.conclusions")
def ai_conclusions(ctx) -> dict:
    return _run_ai(
        ctx, "conclusions",
        structure_summary=_trim(ctx.read_dependency_output("collect.structure"), 3000),
        deps_summary=_trim(ctx.read_dependency_output("collect.dependencies"), 4000),
        quality_summary=_trim(ctx.read_dependency_output("collect.quality"), 5000),
        security_summary=_trim(ctx.read_dependency_output("collect.security"), 5000),
        performance_summary=_trim(ctx.read_dependency_output("collect.performance"), 4000),
        docs_summary=_trim(ctx.read_dependency_output("collect.docs"), 3500),
        tests_summary=_trim(ctx.read_dependency_output("collect.tests"), 3500))


@register("ai.summary")
def ai_summary(ctx) -> dict:
    return _run_ai(
        ctx, "summary",
        scoring_summary=_trim(ctx.read_dependency_output("scoring"), 4000),
        conclusions_summary=_trim(ctx.read_dependency_output("ai.conclusions"), 8000),
        architecture_summary=_trim(ctx.read_dependency_output("ai.architecture"), 4000),
        business_summary=_trim(ctx.read_dependency_output("ai.business_knowledge"), 5000),
        overview_summary=_trim(ctx.read_dependency_output("collect.overview"), 3000))
