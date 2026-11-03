"""
JSON 报告生成器

生成标准格式的 JSON 审计报告，包含完整的统计信息
"""

import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from collections import Counter

from audit.reporters.base import BaseReporter
from audit.core.models import AnalysisResult, Severity


class JsonReporter(BaseReporter):
    """JSON 报告生成器"""

    def generate(self, results: List[AnalysisResult], output_path: Optional[str] = None):
        """
        生成 JSON 报告

        Args:
            results: 分析结果列表
            output_path: 输出路径
        """
        report = {
            'metadata': self._generate_metadata(results),
            'summary': self._generate_summary(results),
            'results': [result.to_dict() for result in results]
        }

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))

    def _generate_metadata(self, results: List[AnalysisResult]) -> Dict[str, Any]:
        """生成报告元数据"""
        return {
            'generated_at': datetime.now().isoformat(),
            'tool': 'audit',
            'version': '1.0.0',
            'total_repos': len(results),
            'total_files': sum(r.files_scanned for r in results),
            'total_issues': sum(len(r.issues) for r in results),
            'total_duration': sum(r.duration_seconds for r in results),
        }

    def _generate_summary(self, results: List[AnalysisResult]) -> Dict[str, Any]:
        """生成汇总统计"""
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

        return {
            'by_severity': dict(severity_counts),
            'by_tool': dict(tool_counts),
            'by_dimension': dict(dimension_counts),
            'by_language': dict(language_counts),
        }
