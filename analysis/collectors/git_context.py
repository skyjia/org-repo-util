"""collect.git_context — commit 消息摘要（供 AI 业务还原；REQ §1.2：不含作者信息）"""

from __future__ import annotations

import subprocess
from collections import Counter

from analysis.collectors.base import Collector, collector


def _git(repo, *args, timeout: int = 120) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=timeout)
    return proc.stdout if proc.returncode == 0 else ""


@collector
class GitContextCollector(Collector):
    name = "git_context"

    def collect(self, ctx) -> dict:
        repo = ctx.repo_path
        US = "\x1f"  # 单元分隔符

        # 近 500 条 commit：hash + 日期 + 消息（**不取作者**，REQ §1.2 / 设计决策 D5）
        raw = _git(repo, "log", f"--pretty=%h{US}%ad{US}%s", "--date=short", "-n", "500")
        commits = []
        for line in raw.splitlines():
            parts = line.split(US)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})

        # 年度 commit 分布（仓库级演进信息，非人员统计）
        years_raw = _git(repo, "log", "--pretty=%ad", "--date=format:%Y")
        year_dist = dict(sorted(Counter(l for l in years_raw.splitlines() if l).items()))

        first_raw = _git(repo, "log", "--reverse", f"--pretty=%ad{US}%s", "--date=short")
        first_line = first_raw.splitlines()[0] if first_raw else ""
        first_parts = first_line.split(US) if first_line else []

        # 消息中的高频词（粗提业务词汇，供 AI 参考；过滤常规动词/工具词）
        stop = {
            "fix", "feat", "add", "update", "merge", "branch", "commit", "the", "and",
            "for", "with", "from", "into", "wip", "tmp", "test", "chore", "docs",
            "refactor", "style", "perf", "build", "ci", "revert", "merge branch",
            "to", "of", "in", "on", "a", "an", "is", "are", "remove", "deleted",
            "修改", "更新", "合并", "提交", "修复", "新增", "添加", "调整", "优化",
        }
        words = Counter()
        for c in commits:
            msg = c["message"].lower()
            # 去掉 conventional commit 前缀
            for sep in (":", "："):
                if sep in msg[:20]:
                    msg = msg.split(sep, 1)[1]
                    break
            for w in msg.replace(",", " ").replace(".", " ").split():
                w = w.strip("()[]{}#!*")
                if len(w) > 2 and w not in stop and not w.isdigit():
                    words[w] += 1

        return {
            "total_commits_analyzed": len(commits),
            "first_commit": {
                "date": first_parts[0] if len(first_parts) == 2 else None,
                "message": first_parts[1] if len(first_parts) == 2 else None,
            },
            "commits_per_year": year_dist,
            "recent_commits": commits[:100],          # AI 注入用（近 100 条）
            "older_commit_messages": [c["message"] for c in commits[100:300]],
            "frequent_message_words": words.most_common(40),
            "tags": _git(repo, "tag", "--sort=-creatordate").splitlines()[:30],
            "privacy_note": "按 REQ §1.2 不采集作者/贡献者信息，本产物仅含仓库级演进数据",
        }
