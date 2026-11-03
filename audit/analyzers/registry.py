"""
分析器注册表 - 管理所有分析器
"""

from typing import Dict, List, Optional, Type
import logging

from audit.analyzers.base import BaseAnalyzer


logger = logging.getLogger(__name__)


class AnalyzerRegistry:
    """分析器注册表"""

    _instance = None
    _analyzers: Dict[str, Type[BaseAnalyzer]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._analyzers = {}
            cls._instance._register_default_analyzers()
        return cls._instance

    def _register_default_analyzers(self):
        """注册默认分析器"""
        try:
            from audit.analyzers.eslint_analyzer import ESLintAnalyzer
            self.register("eslint", ESLintAnalyzer)
        except ImportError as e:
            logger.warning(f"无法加载 ESLintAnalyzer: {e}")

        try:
            from audit.analyzers.golangci_lint_analyzer import GolangciLintAnalyzer
            self.register("golangci-lint", GolangciLintAnalyzer)
        except ImportError as e:
            logger.warning(f"无法加载 GolangciLintAnalyzer: {e}")

        try:
            from audit.analyzers.dotnet_format_analyzer import DotnetFormatAnalyzer
            self.register("dotnet-format", DotnetFormatAnalyzer)
        except ImportError as e:
            logger.warning(f"无法加载 DotnetFormatAnalyzer: {e}")

    def register(self, name: str, analyzer_class: Type[BaseAnalyzer]):
        """
        注册分析器

        Args:
            name: 分析器名称
            analyzer_class: 分析器类
        """
        self._analyzers[name] = analyzer_class
        logger.debug(f"注册分析器: {name}")

    def get(self, name: str) -> Optional[Type[BaseAnalyzer]]:
        """
        获取分析器类

        Args:
            name: 分析器名称

        Returns:
            分析器类，如果不存在则返回 None
        """
        return self._analyzers.get(name)

    def get_by_language(self, language: str) -> List[Type[BaseAnalyzer]]:
        """
        根据语言获取分析器

        Args:
            language: 语言名称

        Returns:
            分析器类列表
        """
        result = []
        for name, analyzer_class in self._analyzers.items():
            # 创建一个临时实例来检查语言
            try:
                temp_instance = analyzer_class(repo_path="/tmp")
                if temp_instance.language == language:
                    result.append(analyzer_class)
            except Exception:
                pass
        return result

    def list_analyzers(self) -> List[str]:
        """
        列出所有已注册的分析器

        Returns:
            分析器名称列表
        """
        return list(self._analyzers.keys())

    def create_analyzer(self, name: str, repo_path: str, **kwargs) -> Optional[BaseAnalyzer]:
        """
        创建分析器实例

        Args:
            name: 分析器名称
            repo_path: 仓库路径
            **kwargs: 其他参数

        Returns:
            分析器实例，如果创建失败则返回 None
        """
        analyzer_class = self.get(name)
        if analyzer_class:
            return analyzer_class(repo_path=repo_path, **kwargs)
        return None

    def auto_select(self, language: str) -> Optional[str]:
        """
        根据语言自动选择分析器

        Args:
            language: 语言名称

        Returns:
            分析器名称，如果没有可用的则返回 None
        """
        # 语言到分析器的映射
        language_map = {
            "javascript": "eslint",
            "typescript": "eslint",
            "vue": "eslint",
            "go": "golangci-lint",
            "csharp": "dotnet-format",
        }

        analyzer_name = language_map.get(language.lower())
        if analyzer_name and analyzer_name in self._analyzers:
            return analyzer_name

        # 尝试查找任何支持该语言的分析器
        analyzers = self.get_by_language(language)
        if analyzers:
            return analyzers[0].name

        return None
