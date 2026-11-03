"""
批量审计器 - 审计组织下所有仓库
"""

from typing import Optional, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from audit.core.config_manager import ConfigManager
from audit.core.repo_scanner import RepoScanner
from audit.core.auditor import Auditor
from audit.core.models import AnalysisResult
from audit.core.result_aggregator import ResultAggregator


logger = logging.getLogger(__name__)


class BatchAuditor:
    """批量审计器"""

    def __init__(self, org_name: str, pattern: Optional[str] = None,
                 skip_archived: bool = True, language_filter: Optional[str] = None,
                 parallel: int = 1, timeout: int = 600, verbose: bool = False):
        """
        初始化批量审计器

        Args:
            org_name: 组织名称
            pattern: 仓库名过滤模式
            skip_archived: 是否跳过 archived 仓库
            language_filter: 语言过滤
            parallel: 并行数量
            timeout: 单仓库超时
            verbose: 详细输出
        """
        self.org_name = org_name
        self.pattern = pattern
        self.skip_archived = skip_archived
        self.language_filter = language_filter
        self.parallel = parallel
        self.timeout = timeout
        self.verbose = verbose

        self.repo_scanner = RepoScanner()
        self.aggregator = ResultAggregator()

        if verbose:
            logging.basicConfig(level=logging.INFO)

    def audit(self) -> List[AnalysisResult]:
        """
        执行批量审计

        Returns:
            分析结果列表
        """
        # 1. 扫描仓库列表
        repos = self._scan_repos()
        if not repos:
            logger.warning(f"未找到符合条件的仓库: {self.org_name}")
            return []

        logger.info(f"找到 {len(repos)} 个仓库待审计")

        # 2. 并行执行审计
        results = self._audit_repos(repos)

        logger.info(f"审计完成: {len(results)} 个仓库")
        return results

    def _scan_repos(self) -> List[Path]:
        """扫描仓库列表"""
        # 扫描本地仓库
        repos_dir = Path("repos") / self.org_name

        if not repos_dir.exists():
            logger.warning(f"仓库目录不存在: {repos_dir}")
            return []

        repos = []
        for repo_dir in repos_dir.iterdir():
            if not repo_dir.is_dir():
                continue

            # 模式过滤
            if self.pattern:
                import fnmatch
                if not fnmatch.fnmatch(repo_dir.name, self.pattern):
                    continue

            repos.append(repo_dir)

        return repos

    def _audit_repos(self, repos: List[Path]) -> List[AnalysisResult]:
        """并行审计仓库"""
        results = []

        if self.parallel <= 1:
            # 串行执行
            for repo in repos:
                result = self._audit_single_repo(repo)
                results.append(result)
        else:
            # 并行执行
            with ThreadPoolExecutor(max_workers=self.parallel) as executor:
                future_to_repo = {
                    executor.submit(self._audit_single_repo, repo): repo
                    for repo in repos
                }

                for future in as_completed(future_to_repo):
                    repo = future_to_repo[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"审计 {repo.name} 失败: {e}")
                        results.append(AnalysisResult(
                            repo=repo.name,
                            language="unknown",
                            analyzer="unknown",
                            error=str(e)
                        ))

        return results

    def _audit_single_repo(self, repo_path: Path) -> AnalysisResult:
        """审计单个仓库"""
        logger.info(f"审计仓库: {repo_path.name}")

        try:
            auditor = Auditor(
                repo_path=str(repo_path),
                language_filter=self.language_filter,
                timeout=self.timeout,
                verbose=self.verbose
            )
            return auditor.audit()
        except Exception as e:
            logger.error(f"审计 {repo_path.name} 失败: {e}")
            return AnalysisResult(
                repo=repo_path.name,
                language="unknown",
                analyzer="unknown",
                error=str(e)
            )
