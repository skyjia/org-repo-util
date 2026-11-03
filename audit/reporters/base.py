"""
报告生成器基类
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path

from audit.core.models import AnalysisResult


class BaseReporter(ABC):
    """报告生成器基类"""

    @abstractmethod
    def generate(self, results: List[AnalysisResult], output_path: Optional[str] = None):
        """
        生成报告

        Args:
            results: 分析结果列表
            output_path: 输出路径
        """
        pass
