"""
单仓库审计器
"""

import logging
import subprocess
from typing import Optional, List
from pathlib import Path

from audit.core.config_manager import ConfigManager
from audit.core.language_detector import LanguageDetector
from audit.core.file_collector import FileCollector
from audit.core.models import AnalysisResult
from audit.core.change_detector import ChangeDetector
from audit.core.dependency_scanner import DependencyScanner
from audit.analyzers.registry import AnalyzerRegistry


logger = logging.getLogger(__name__)


class Auditor:
    """单仓库审计器"""

    def __init__(self, repo_path: str, branch: Optional[str] = None,
                 incremental: bool = False, language_filter: Optional[str] = None,
                 timeout: int = 600, verbose: bool = False, skip_dependency_scan: bool = False):
        """
        初始化审计器

        Args:
            repo_path: 仓库路径
            branch: 分支/tag/commit
            incremental: 是否增量审计
            language_filter: 语言过滤
            timeout: 超时时间
            verbose: 详细输出
            skip_dependency_scan: 是否跳过依赖扫描
        """
        self.repo_path = Path(repo_path)
        self.branch = branch
        self.incremental = incremental
        self.language_filter = language_filter
        self.timeout = timeout
        self.verbose = verbose
        self.skip_dependency_scan = skip_dependency_scan

        self.config_manager = ConfigManager()
        self.config_manager.load_repo_config(repo_path)
        self.language_detector = LanguageDetector()
        self.file_collector = FileCollector(self.config_manager.merged_config)
        self.analyzer_registry = AnalyzerRegistry()
        self.change_detector = ChangeDetector(repo_path)
        self.dependency_scanner = DependencyScanner()

        if verbose:
            logging.basicConfig(level=logging.INFO)

        # 切换分支（如果指定）
        self.original_branch = None
        if branch:
            self._switch_branch(branch)

    def _switch_branch(self, branch: str):
        """切换到指定分支"""
        try:
            # 记录当前分支
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=10
            )
            if result.returncode == 0:
                self.original_branch = result.stdout.strip()

            # 切换分支
            subprocess.run(
                ["git", "checkout", branch],
                capture_output=True,
                cwd=self.repo_path,
                timeout=30
            )
            logger.info(f"已切换到分支: {branch}")
        except Exception as e:
            logger.warning(f"切换分支失败: {e}")

    def __del__(self):
        """恢复原始分支"""
        if self.original_branch:
            try:
                subprocess.run(
                    ["git", "checkout", self.original_branch],
                    capture_output=True,
                    cwd=self.repo_path,
                    timeout=30
                )
                logger.info(f"已恢复到分支: {self.original_branch}")
            except Exception:
                pass

    def audit(self) -> AnalysisResult:
        """
        执行审计

        Returns:
            分析结果
        """
        logger.info(f"开始审计仓库: {self.repo_path}")

        # 1. 检测语言
        languages = self.language_detector.detect_from_local(str(self.repo_path))
        if not languages:
            logger.warning("未检测到主要语言")
            return self._create_empty_result("unknown", "none")

        # 过滤语言
        if self.language_filter:
            languages = [lang for lang in languages if lang["language"] == self.language_filter]
            if not languages:
                logger.warning(f"未检测到语言: {self.language_filter}")
                return self._create_empty_result(self.language_filter, "none")

        # 选择主要语言
        primary_language = languages[0]["language"]
        logger.info(f"检测到主要语言: {primary_language}")

        # 2. 自动选择分析器
        analyzer_name = self.analyzer_registry.auto_select(primary_language)
        if not analyzer_name:
            logger.warning(f"未找到支持 {primary_language} 的分析器")
            return self._create_empty_result(primary_language, "none")

        logger.info(f"使用分析器: {analyzer_name}")

        # 3. 创建分析器实例
        analyzer = self.analyzer_registry.create_analyzer(
            analyzer_name,
            str(self.repo_path),
            config=self.config_manager.merged_config
        )

        if not analyzer:
            logger.error(f"无法创建分析器: {analyzer_name}")
            return self._create_empty_result(primary_language, analyzer_name)

        # 4. 检查先决条件
        if not analyzer.check_prerequisites():
            logger.error(f"分析器 {analyzer_name} 先决条件不满足")
            return self._create_empty_result(primary_language, analyzer_name)

        # 5. 增量审计处理
        if self.incremental:
            files_to_audit = self._get_incremental_files()
            if files_to_audit is None:
                # 需要全量审计
                logger.info("执行全量审计")
            else:
                logger.info(f"增量审计: {len(files_to_audit)} 个变更文件")
                # TODO: 实现只审计变更文件

        # 6. 执行分析
        try:
            result = analyzer.analyze()
            logger.info(f"代码分析完成: {len(result.issues)} 个问题")

            # 7. 执行依赖扫描（如果未跳过）
            if not self.skip_dependency_scan:
                logger.info("开始依赖漏洞扫描...")
                dep_issues = self.dependency_scanner.scan(str(self.repo_path))
                if dep_issues:
                    logger.info(f"依赖扫描完成: {len(dep_issues)} 个漏洞")
                    result.issues.extend(dep_issues)
                else:
                    logger.info("依赖扫描完成: 未发现漏洞")
            else:
                logger.info("跳过依赖漏洞扫描")

            logger.info(f"审计完成: 共 {len(result.issues)} 个问题")
            return result
        except Exception as e:
            logger.error(f"分析器执行失败: {e}")
            return self._create_empty_result(primary_language, analyzer_name)

    def _get_incremental_files(self) -> Optional[List[Path]]:
        """
        获取增量审计的文件列表

        Returns:
            变更文件列表，如果返回 None 则表示需要全量审计
        """
        # 获取上次审计时间
        last_audit = self.change_detector.get_last_audit_time()
        if not last_audit:
            logger.info("未找到历史审计记录，执行全量审计")
            return None

        # 获取变更文件
        changed_files = self.change_detector.get_changed_files(since=last_audit)
        if not changed_files:
            logger.info("没有文件变更")
            return []

        # 判断是否需要全量审计
        if self.change_detector.should_full_audit(changed_files):
            return None

        # 转换为 Path 对象
        changed_paths = [self.repo_path / f for f in changed_files]

        # 过滤存在的文件
        changed_paths = [p for p in changed_paths if p.exists()]

        return changed_paths

    def _create_empty_result(self, language: str, analyzer: str) -> AnalysisResult:
        """创建空结果"""
        return AnalysisResult(
            repo=str(self.repo_path),
            language=language,
            analyzer=analyzer,
            files_scanned=0,
            lines_scanned=0,
            duration_seconds=0.0
        )
