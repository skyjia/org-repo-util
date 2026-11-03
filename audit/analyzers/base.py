"""
分析器基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path

from audit.core.models import AnalysisResult


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
