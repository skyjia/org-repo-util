"""
批量审计器 - 审计组织下所有仓库
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
import logging
import time

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
                 parallel: int = 1, timeout: int = 600, verbose: bool = False,
                 incremental: bool = False):
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
            incremental: 是否增量审计
        """
        self.org_name = org_name
        self.pattern = pattern
        self.skip_archived = skip_archived
        self.language_filter = language_filter
        self.parallel = parallel
        self.timeout = timeout
        self.verbose = verbose
        self.incremental = incremental

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

        # 3. 输出统计
        self._print_summary(results)

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
        for repo_dir in sorted(repos_dir.iterdir()):
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
        start_time = time.time()

        if self.parallel <= 1:
            # 串行执行
            for i, repo in enumerate(repos, 1):
                logger.info(f"[{i}/{len(repos)}] 审计仓库: {repo.name}")
                result = self._audit_single_repo(repo)
                results.append(result)
        else:
            # 并行执行
            logger.info(f"使用 {self.parallel} 个并行线程")
            with ThreadPoolExecutor(max_workers=self.parallel) as executor:
                future_to_repo = {
                    executor.submit(self._audit_single_repo, repo): repo
                    for repo in repos
                }

                completed = 0
                for future in as_completed(future_to_repo):
                    repo = future_to_repo[future]
                    completed += 1
                    try:
                        result = future.result(timeout=self.timeout)
                        results.append(result)
                        status = "✅" if not result.error else "❌"
                        logger.info(
                            f"[{completed}/{len(repos)}] {status} {repo.name}: "
                            f"{len(result.issues)} 个问题"
                        )
                    except FuturesTimeout:
                        logger.error(f"[{completed}/{len(repos)}] ⏱️ {repo.name}: 超时")
                        results.append(AnalysisResult(
                            repo=repo.name,
                            language="unknown",
                            analyzer="unknown",
                            error=f"审计超时（{self.timeout}秒）"
                        ))
                    except Exception as e:
                        logger.error(f"[{completed}/{len(repos)}] ❌ {repo.name}: {e}")
                        results.append(AnalysisResult(
                            repo=repo.name,
                            language="unknown",
                            analyzer="unknown",
                            error=str(e)
                        ))

        duration = time.time() - start_time
        logger.info(f"总耗时: {duration:.2f}s")

        return results

    def _audit_single_repo(self, repo_path: Path) -> AnalysisResult:
        """审计单个仓库"""
        try:
            auditor = Auditor(
                repo_path=str(repo_path),
                language_filter=self.language_filter,
                timeout=self.timeout,
                verbose=self.verbose,
                incremental=self.incremental
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

    def _print_summary(self, results: List[AnalysisResult]):
        """打印摘要"""
        total = len(results)
        success = sum(1 for r in results if not r.error)
        failed = total - success
        total_issues = sum(len(r.issues) for r in results)
        total_files = sum(r.files_scanned for r in results)

        logger.info(
            f"摘要: {success} 成功 / {failed} 失败, "
            f"{total_files} 文件, {total_issues} 问题"
        )

        if failed > 0:
            logger.info("失败的仓库:")
            for r in results:
                if r.error:
                    logger.info(f"  ❌ {r.repo}: {r.error}")
