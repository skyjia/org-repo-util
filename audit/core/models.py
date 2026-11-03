"""
数据模型定义 - Issue, AnalysisResult 等
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class Severity(Enum):
    """问题严重级别"""
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    INFO = 'info'


@dataclass
class Issue:
    """审计问题"""
    file: str
    line: int
    column: int
    severity: Severity
    message: str
    rule: str
    tool: str
    dimension: str  # code_style | security
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'file': self.file,
            'line': self.line,
            'column': self.column,
            'severity': self.severity.value,
            'message': self.message,
            'rule': self.rule,
            'tool': self.tool,
            'dimension': self.dimension,
            'suggestion': self.suggestion,
        }


@dataclass
class AnalysisResult:
    """单个分析器的结果"""
    repo: str
    language: str
    analyzer: str
    issues: List[Issue] = field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'repo': self.repo,
            'language': self.language,
            'analyzer': self.analyzer,
            'issues': [issue.to_dict() for issue in self.issues],
            'files_scanned': self.files_scanned,
            'lines_scanned': self.lines_scanned,
            'duration_seconds': self.duration_seconds,
            'error': self.error,
        }
