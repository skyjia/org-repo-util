"""collect.overview — 仓库概述（REQ §3.1）：gh api + git，API 失败降级 export 快照/纯 git

M7：优先复用 repos/<org>-summary.json（fish export --languages 产物）作为语言分布
数据源与 API 降级快照，节省 gh api 调用并支持离线。
"""

from __future__ import annotations

import json
import subprocess

from analysis.collectors.base import Collector, collector, not_found
from analysis.core import config


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _summary_entry(org: str, repo: str) -> dict | None:
    """读取 export 快照中该仓库条目（含 primary_language + languages 比重分布）"""
    p = config.REPOS_DIR / f"{org}-summary.json"
    if not p.exists():
        return None
    try:
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("name") == repo:
                return r
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _gh_api(endpoint: str) -> dict | None:
    try:
        proc = _run(["gh", "api", endpoint], timeout=60)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def _git(repo, *args) -> str:
    proc = _run(["git", "-C", str(repo), *args])
    return proc.stdout.strip() if proc.returncode == 0 else ""


@collector
class OverviewCollector(Collector):
    name = "overview"

    def collect(self, ctx) -> dict:
        repo = ctx.repo_path
        out: dict = {
            "name": ctx.repo,
            "org": ctx.org,
            "analysis_baseline": {"commit_sha": ctx.commit_sha, "ref": ctx.task.ref},
        }

        # ---- git 本地数据（始终可得） ----
        first_commit_date = _git(repo, "log", "--reverse", "--pretty=%aI", "--")
        out["git"] = {
            "first_commit_at": first_commit_date.splitlines()[0] if first_commit_date else None,
            "last_commit_at": _git(repo, "log", "-1", "--pretty=%aI") or None,
            "total_commits": int(_git(repo, "rev-list", "--count", "HEAD") or 0),
            "branches": _git(repo, "branch", "--format=%(refname:short)").splitlines(),
            "current_branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "tag_count": len(_git(repo, "tag").splitlines()),
            "recent_tags": _git(repo, "tag", "--sort=-creatordate").splitlines()[:10],
        }

        # ---- GitHub API（REQ §2.2-3；失败降级 export 快照/纯 git，REQ 第 7 章） ----
        entry = _summary_entry(ctx.org, ctx.repo)
        api = _gh_api(f"repos/{ctx.org}/{ctx.repo}")
        if api:
            out["github"] = {
                "found": True,
                "description": api.get("description"),
                "owner": (api.get("owner") or {}).get("login"),
                "created_at": api.get("created_at"),
                "updated_at": api.get("updated_at"),
                "pushed_at": api.get("pushed_at"),
                "size_kb": api.get("size"),
                "primary_language": api.get("language"),
                "default_branch": api.get("default_branch"),
                "visibility": api.get("visibility"),
                "archived": api.get("archived"),
                "fork": api.get("fork"),
                "homepage": api.get("homepage"),
            }
            # 创建时间交叉验证（REQ §3.1）
            created, first = api.get("created_at"), out["git"]["first_commit_at"]
            if created and first and created[:10] != first[:10]:
                out["_meta_crosscheck"] = {
                    "created_at_mismatch": True,
                    "github_created_at": created,
                    "git_first_commit_at": first,
                    "note": "GitHub 创建时间与本地首次 commit 时间不一致（可能经历过迁移/重建）",
                }
            # 语言分布：优先 export 快照（--languages 产物，免二次 API 调用），API 兜底
            if entry and entry.get("languages"):
                out["languages"] = entry["languages"]
                out["languages_source"] = f"repos/{ctx.org}-summary.json（export 快照）"
            else:
                langs = _gh_api(f"repos/{ctx.org}/{ctx.repo}/languages")
                out["languages"] = langs if langs else not_found(
                    "语言构成", "gh api languages 未返回数据，可检查仓库是否为空或 gh 权限")
                out["languages_source"] = "gh api"
            if not out["github"]["primary_language"] and entry:
                out["github"]["primary_language"] = entry.get("primary_language")
        elif entry:
            out["github"] = {
                "found": "snapshot",
                "source": f"repos/{ctx.org}-summary.json（export 快照，可能滞后；gh api 不可达）",
                "description": entry.get("description"),
                "created_at": None,
                "pushed_at": entry.get("pushed_at"),
                "size_kb": entry.get("size"),
                "primary_language": entry.get("primary_language"),
                "archived": entry.get("archived"),
                "visibility": entry.get("visibility"),
            }
            out["languages"] = entry.get("languages") or not_found(
                "语言构成", "快照中无 languages 数据（export 时未加 --languages）")
            out["languages_source"] = "export 快照"
        else:
            out["github"] = not_found(
                "GitHub 元数据",
                "gh 未认证或 API 不可达且无 export 快照：运行 gh auth login 或 "
                "fish src/main.fish export --org <org> --languages；"
                "本次分析已降级为纯本地 git 数据")
            out["languages"] = {"found": False, "note": "依赖 GitHub API，未获取（可由 structure 采集的本地统计替代）"}

        return out
