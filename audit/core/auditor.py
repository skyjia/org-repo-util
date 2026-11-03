"""
单仓库审计器
"""

import logging
from typing import Optional
from pathlib import Path

from audit.core.config_manager import ConfigManager
from audit.core.language_detector import LanguageDetector
from audit.core.file_collector import FileCollector
from audit.core.models import AnalysisResult
from audit.analyzers.registry import AnalyzerRegistry


logger = logging.getLogger(__name__)


class Auditor:
    """单仓库审计器"""

    def __init__(self, repo_path: str, branch: Optional[str] = None,
                 incremental: bool = False, language_filter: Optional[str] = None,
                 timeout: int = 600, verbose: bool = False):
        """
        初始化审计器

        Args:
            repo_path: 仓库路径
            branch: 分支/tag/commit
            incremental: 是否增量审计
            language_filter: 语言过滤
            timeout: 超时时间
            verbose: 详细输出
        """
        self.repo_path = Path(repo_path)
        self.branch = branch
        self.incremental = incremental
        self.language_filter = language_filter
        self.timeout = timeout
        self.verbose = verbose

        self.config_manager = ConfigManager()
        self.config_manager.load_repo_config(repo_path)
        self.language_detector = LanguageDetector()
        self.file_collector = FileCollector(self.config_manager.merged_config)
        self.analyzer_registry = AnalyzerRegistry()

        if verbose:
            logging.basicConfig(level=logging.INFO)

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

        # 5. 执行分析
        try:
            result = analyzer.analyze()
            logger.info(f"审计完成: {len(result.issues)} 个问题")
            return result
        except Exception as e:
            logger.error(f"分析器执行失败: {e}")
            return self._create_empty_result(primary_language, analyzer_name)

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
