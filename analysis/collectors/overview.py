"""collect.overview — 仓库概述（REQ §3.1）：gh api + git，API 失败降级纯 git"""

from __future__ import annotations

import json
import subprocess

from analysis.collectors.base import Collector, collector, not_found


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


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

        # ---- GitHub API（REQ §2.2-3；失败降级并标注，REQ 第 7 章） ----
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
            langs = _gh_api(f"repos/{ctx.org}/{ctx.repo}/languages")
            out["languages"] = langs if langs else not_found(
                "语言构成", "gh api languages 未返回数据，可检查仓库是否为空或 gh 权限")
        else:
            out["github"] = not_found(
                "GitHub 元数据",
                "gh 未认证或 API 不可达：运行 gh auth login；仓库描述/创建时间/大小等平台数据未获取，"
                "本次分析已降级为纯本地 git 数据")
            out["languages"] = {"found": False, "note": "依赖 GitHub API，未获取（可由 structure 采集的本地统计替代）"}

        return out
