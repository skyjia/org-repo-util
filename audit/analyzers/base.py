"""
分析器基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path

from audit.core.models import AnalysisResult, Issue


class BaseAnalyzer(ABC):
    """分析器基类"""

    def __init__(self, repo_path: str, config: Optional[Dict[str, Any]] = None):
        """
        初始化分析器

        Args:
            repo_path: 仓库路径
            config: 配置字典
        """
        self.repo_path = repo_path
        self.config = config or {}

    @property
    @abstractmethod
    def name(self) -> str:
        """分析器名称"""
        pass

    @property
    @abstractmethod
    def language(self) -> str:
        """支持的语言"""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """支持的文件扩展名"""
        pass

    @abstractmethod
    def check_prerequisites(self) -> bool:
        """
        检查工具是否已安装

        Returns:
            是否满足先决条件
        """
        pass

    @abstractmethod
    def analyze(self) -> AnalysisResult:
        """
        执行分析

        Returns:
            分析结果
        """
        pass

    def collect_files(self) -> List[Path]:
        """
        收集待分析的文件

        Returns:
            文件路径列表
        """
        from audit.core.file_collector import FileCollector

        collector = FileCollector(self.config)
        return collector.collect(
            self.repo_path,
            extensions=self.supported_extensions
        )

    def filter_ignored_issues(self, issues: List[Issue]) -> List[Issue]:
        """
        过滤被忽略的问题

        支持两种忽略方式：
        1. 配置文件级别：在 .audit-config.yaml 中定义文件级规则覆盖
           ```yaml
           overrides:
             files:
               "src/legacy/**":
                 rules:
                   no-console: ignore
           ```
        2. 代码注释级别：在代码中添加 @audit-ignore 注释
           ```javascript
           // @audit-ignore
           console.log("debug");
           ```

        Args:
            issues: 原始问题列表

        Returns:
            过滤后的问题列表
        """
        from audit.core.config_manager import ConfigManager
        from audit.core.ignore_parser import is_line_ignored

        # 初始化配置管理器
        config_manager = ConfigManager()
        config_manager.load_repo_config(self.repo_path)

        filtered_issues = []
        for issue in issues:
            # 检查配置文件级别的忽略规则
            relative_path = self._get_relative_path(issue.file)
            if config_manager.is_rule_ignored(relative_path, issue.rule, self.language):
                continue

            # 检查代码注释级别的忽略
            if is_line_ignored(issue.file, issue.line, self.language):
                continue

            filtered_issues.append(issue)

        return filtered_issues

    def _get_relative_path(self, file_path: str) -> str:
        """
        获取文件相对于仓库根目录的路径

        Args:
            file_path: 文件路径（可能是绝对路径）

        Returns:
            相对路径
        """
        import os
        try:
            path = Path(file_path).resolve()
            repo = Path(self.repo_path).resolve()
            return str(path.relative_to(repo))
        except ValueError:
            # 如果无法转换为相对路径，尝试使用 os.path.relpath
            try:
                return os.path.relpath(file_path, self.repo_path)
            except ValueError:
                # 如果仍然失败，返回原始路径
                return file_path
