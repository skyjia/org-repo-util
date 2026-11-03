"""
结果聚合器 - 聚合多个仓库的审计结果
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import Counter
from pathlib import Path

from audit.core.models import AnalysisResult, Severity


@dataclass
class AggregateResult:
    """聚合结果"""

    # 基本信息
    total_repos: int = 0
    successful_repos: int = 0
    failed_repos: int = 0

    # 统计数据
    total_files: int = 0
    total_lines: int = 0
    total_issues: int = 0
    total_duration: float = 0.0

    # 分类统计
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_tool: Dict[str, int] = field(default_factory=dict)
    by_dimension: Dict[str, int] = field(default_factory=dict)
    by_language: Dict[str, int] = field(default_factory=dict)

    # 详细结果
    results: List[AnalysisResult] = field(default_factory=list)

    # 失败仓库列表
    failed_repo_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_repos': self.total_repos,
            'successful_repos': self.successful_repos,
            'failed_repos': self.failed_repos,
            'total_files': self.total_files,
            'total_lines': self.total_lines,
            'total_issues': self.total_issues,
            'total_duration': self.total_duration,
            'by_severity': self.by_severity,
            'by_tool': self.by_tool,
            'by_dimension': self.by_dimension,
            'by_language': self.by_language,
            'results': [r.to_dict() for r in self.results],
            'failed_repo_names': self.failed_repo_names,
        }


class ResultAggregator:
    """结果聚合器"""

    def aggregate(self, results: List[AnalysisResult]) -> AggregateResult:
        """
        聚合多个仓库的审计结果

        Args:
            results: 分析结果列表

        Returns:
            聚合结果
        """
        agg = AggregateResult()
        agg.total_repos = len(results)
        agg.results = results

        # 统计成功/失败仓库
        for result in results:
            if result.error:
                agg.failed_repos += 1
                agg.failed_repo_names.append(result.repo)
            else:
                agg.successful_repos += 1

        # 基础统计
        agg.total_files = sum(r.files_scanned for r in results)
        agg.total_lines = sum(r.lines_scanned for r in results)
        agg.total_issues = sum(len(r.issues) for r in results)
        agg.total_duration = sum(r.duration_seconds for r in results)

        # 分类统计
        severity_counts = Counter()
        tool_counts = Counter()
        dimension_counts = Counter()
        language_counts = Counter()

        for result in results:
            language_counts[result.language] += len(result.issues)
            for issue in result.issues:
                severity_counts[issue.severity.value] += 1
                tool_counts[issue.tool] += 1
                dimension_counts[issue.dimension] += 1

        agg.by_severity = dict(severity_counts)
        agg.by_tool = dict(tool_counts)
        agg.by_dimension = dict(dimension_counts)
        agg.by_language = dict(language_counts)

        return agg

    def get_top_issues(self, results: List[AnalysisResult], limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最常见的问题

        Args:
            results: 分析结果列表
            limit: 返回数量限制

        Returns:
            问题列表
        """
        rule_counts = Counter()
        rule_examples = {}

        for result in results:
            for issue in result.issues:
                rule_key = f"{issue.tool}:{issue.rule}"
                rule_counts[rule_key] += 1
                if rule_key not in rule_examples:
                    rule_examples[rule_key] = {
                        'tool': issue.tool,
                        'rule': issue.rule,
                        'message': issue.message,
                        'severity': issue.severity.value,
                        'count': 0,
                    }
                rule_examples[rule_key]['count'] += 1

        # 按出现次数排序
        top_rules = rule_counts.most_common(limit)
        return [rule_examples[rule] for rule, _ in top_rules]

    def get_repo_summary(self, result: AnalysisResult) -> Dict[str, Any]:
        """
        获取单个仓库的摘要

        Args:
            result: 分析结果

        Returns:
            仓库摘要
        """
        severity_counts = Counter()
        for issue in result.issues:
            severity_counts[issue.severity.value] += 1

        return {
            'repo': result.repo,
            'language': result.language,
            'analyzer': result.analyzer,
            'files_scanned': result.files_scanned,
            'lines_scanned': result.lines_scanned,
            'issue_count': len(result.issues),
            'duration': result.duration_seconds,
            'by_severity': dict(severity_counts),
            'error': result.error,
        }
