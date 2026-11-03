"""
变更检测器 - 检测仓库变更以支持增量审计
"""

import subprocess
import json
from typing import List, Optional, Set, Dict, Any
from pathlib import Path
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class ChangeDetector:
    """变更检测器"""

    def __init__(self, repo_path: str):
        """
        初始化变更检测器

        Args:
            repo_path: 仓库路径
        """
        self.repo_path = Path(repo_path)

    def get_last_audit_time(self) -> Optional[datetime]:
        """
        获取上次审计时间

        Returns:
            上次审计时间，如果没有则返回 None
        """
        from audit.core.report_storage import ReportStorage

        storage = ReportStorage()

        # 解析 org/repo
        parts = self.repo_path.parts
        if len(parts) >= 3 and parts[0] == "repos":
            org, repo = parts[1], parts[2]
        elif len(parts) >= 2:
            org, repo = parts[-2], parts[-1]
        else:
            org, repo = "unknown", self.repo_path.name

        # 查询索引
        reports = storage.list_reports(org=org, repo=repo)
        if reports:
            # 返回最新的报告时间
            latest = reports[0]
            try:
                return datetime.fromisoformat(latest['created_at'])
            except (KeyError, ValueError):
                pass

        return None

    def get_changed_files(self, since: Optional[datetime] = None) -> List[str]:
        """
        获取变更文件列表

        Args:
            since: 起始时间，如果为 None 则返回所有未提交变更

        Returns:
            变更文件路径列表
        """
        changed_files = set()

        # 1. 获取未提交的变更（working directory）
        changed_files.update(self._get_uncommitted_changes())

        # 2. 获取自上次审计以来的提交
        if since:
            changed_files.update(self._get_commits_since(since))

        return list(changed_files)

    def _get_uncommitted_changes(self) -> Set[str]:
        """获取未提交的变更"""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30
            )

            if result.returncode != 0:
                return set()

            changed = set()
            for line in result.stdout.split("\n"):
                if not line.strip():
                    continue
                # 格式：XY filename
                # X: staged, Y: unstaged
                status = line[:2]
                filename = line[3:]

                # 忽略删除的文件
                if status not in [" D", "D "]:
                    # 处理重命名
                    if " -> " in filename:
                        filename = filename.split(" -> ")[-1]
                    changed.add(filename.strip())

            return changed

        except Exception as e:
            logger.warning(f"获取未提交变更失败: {e}")
            return set()

    def _get_commits_since(self, since: datetime) -> Set[str]:
        """获取自指定时间以来的提交变更"""
        try:
            # 格式化时间为 git 可识别的格式
            since_str = since.strftime("%Y-%m-%d %H:%M:%S")

            result = subprocess.run(
                ["git", "log", f"--since={since_str}", "--name-only", "--pretty=format:"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30
            )

            if result.returncode != 0:
                return set()

            changed = set()
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line:
                    changed.add(line)

            return changed

        except Exception as e:
            logger.warning(f"获取提交变更失败: {e}")
            return set()

    def detect_config_changes(self, changed_files: List[str]) -> bool:
        """
        检测配置文件是否变更

        Args:
            changed_files: 变更文件列表

        Returns:
            配置文件是否变更
        """
        config_patterns = [
            ".audit-config.yaml",
            ".eslintrc",
            ".golangci",
            ".editorconfig",
            "package.json",
            "go.mod",
            "*.csproj",
            "*.sln",
        ]

        for file in changed_files:
            for pattern in config_patterns:
                if pattern.startswith("*"):
                    if file.endswith(pattern[1:]):
                        return True
                elif file == pattern or file.startswith(pattern):
                    return True

        return False

    def should_full_audit(self, changed_files: List[str]) -> bool:
        """
        判断是否需要全量审计

        Args:
            changed_files: 变更文件列表

        Returns:
            是否需要全量审计
        """
        # 配置文件变更，需要全量审计
        if self.detect_config_changes(changed_files):
            logger.info("检测到配置文件变更，执行全量审计")
            return True

        # 变更文件过多（超过 50%），全量审计更高效
        total_files = self._count_total_files()
        if total_files > 0 and len(changed_files) > total_files * 0.5:
            logger.info(f"变更文件过多 ({len(changed_files)}/{total_files})，执行全量审计")
            return True

        return False

    def _count_total_files(self) -> int:
        """统计仓库总文件数"""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30
            )

            if result.returncode != 0:
                return 0

            return len([l for l in result.stdout.split("\n") if l.strip()])

        except Exception:
            return 0
