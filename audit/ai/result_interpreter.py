"""
AI 辅助结果解读 - 分析审计结果并生成解读报告
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from audit.ai.client import create_claude_client

logger = logging.getLogger(__name__)


class ResultInterpreter:
    """AI 辅助结果解读器"""

    def __init__(self):
        """初始化结果解读器"""
        self.client = create_claude_client()

    def interpret_report(self, report_path: str) -> str:
        """
        解读审计报告

        Args:
            report_path: 报告文件路径（JSON 或 HTML）

        Returns:
            解读报告（Markdown 格式）
        """
        report_data = self._load_report(report_path)

        prompt = f"""分析以下审计报告，生成详细的解读报告：

报告摘要：
- 仓库: {report_data.get('repo', 'N/A')}
- 语言: {report_data.get('language', 'N/A')}
- 分析器: {report_data.get('analyzer', 'N/A')}
- 文件数: {report_data.get('files_scanned', 0)}
- 问题总数: {len(report_data.get('issues', []))}
- 扫描耗时: {report_data.get('duration_seconds', 0):.2f}s

问题统计：
{self._summarize_issues(report_data.get('issues', []))}

请生成包含以下内容的解读报告（Markdown 格式）：
1. 执行摘要（关键发现、风险评估）
2. 问题分类分析（安全、质量、性能等）
3. 修复优先级建议
4. 关键问题详解（Top 5）
5. 总体建议

输出格式：Markdown"""

        try:
            response = self.client.chat([
                {"role": "user", "content": prompt}
            ])
            return response

        except Exception as e:
            logger.error(f"解读报告失败: {e}")
            raise

    def _load_report(self, report_path: str) -> Dict[str, Any]:
        """加载报告文件"""
        path = Path(report_path)

        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # 对于 HTML 报告，尝试读取对应的 JSON 报告
            json_path = path.with_suffix(".json")
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                raise ValueError(f"无法找到对应的 JSON 报告: {json_path}")

    def _summarize_issues(self, issues: List[Dict[str, Any]]) -> str:
        """汇总问题统计"""
        if not issues:
            return "无问题"

        # 按严重级别统计
        severity_counts = {}
        for issue in issues:
            severity = issue.get("severity", "UNKNOWN")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # 按规则统计
        rule_counts = {}
        for issue in issues:
            rule = issue.get("rule", "UNKNOWN")
            rule_counts[rule] = rule_counts.get(rule, 0) + 1

        # 生成统计文本
        summary_lines = ["严重级别分布:"]
        for severity, count in sorted(severity_counts.items()):
            summary_lines.append(f"  - {severity}: {count}")

        summary_lines.append("\nTop 规则:")
        for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])[:5]:
            summary_lines.append(f"  - {rule}: {count}")

        return "\n".join(summary_lines)

    def suggest_fixes(self, report_path: str, top_n: int = 10) -> str:
        """
        生成修复建议

        Args:
            report_path: 报告文件路径
            top_n: 生成修复建议的问题数量

        Returns:
            修复建议（Markdown 格式）
        """
        report_data = self._load_report(report_path)
        issues = report_data.get("issues", [])[:top_n]

        prompt = f"""针对以下审计问题，生成详细的修复建议：

问题列表：
{self._format_issues_for_fix(issues)}

为每个问题提供：
1. 问题说明
2. 修复方法
3. 代码示例（如适用）
4. 注意事项

输出格式：Markdown"""

        try:
            response = self.client.chat([
                {"role": "user", "content": prompt}
            ])
            return response

        except Exception as e:
            logger.error(f"生成修复建议失败: {e}")
            raise

    def _format_issues_for_fix(self, issues: List[Dict[str, Any]]) -> str:
        """格式化问题列表用于修复建议"""
        lines = []
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. [{issue.get('severity', 'UNKNOWN')}] {issue.get('rule', 'UNKNOWN')}")
            lines.append(f"   文件: {issue.get('file', 'N/A')}:{issue.get('line', 0)}")
            lines.append(f"   消息: {issue.get('message', 'N/A')}")
            lines.append("")

        return "\n".join(lines)

    def classify_issues(self, report_path: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        问题分类

        Args:
            report_path: 报告文件路径

        Returns:
            分类后的问题字典
        """
        report_data = self._load_report(report_path)
        issues = report_data.get("issues", [])

        categories = {
            "security": [],
            "quality": [],
            "performance": [],
            "style": [],
            "other": []
        }

        # 简单分类规则
        security_keywords = ["security", "vulnerability", "injection", "xss", "csrf"]
        performance_keywords = ["performance", "slow", "memory", "leak"]
        style_keywords = ["style", "format", "whitespace", "indent"]

        for issue in issues:
            message = issue.get("message", "").lower()
            rule = issue.get("rule", "").lower()

            if any(kw in message or kw in rule for kw in security_keywords):
                categories["security"].append(issue)
            elif any(kw in message or kw in rule for kw in performance_keywords):
                categories["performance"].append(issue)
            elif any(kw in message or kw in rule for kw in style_keywords):
                categories["style"].append(issue)
            elif issue.get("severity") in ["HIGH", "CRITICAL"]:
                categories["quality"].append(issue)
            else:
                categories["other"].append(issue)

        return categories

    def save_interpretation(self, report_path: str, output_path: Optional[str] = None):
        """
        保存解读报告到文件

        Args:
            report_path: 报告文件路径
            output_path: 输出文件路径，默认保存在报告同目录下
        """
        if output_path is None:
            # 保存在报告同目录下
            report_dir = Path(report_path).parent
            output_path = str(report_dir / "ai-interpretation.md")

        interpretation = self.interpret_report(report_path)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(interpretation)

        logger.info(f"解读报告已保存到: {output_path}")
        return output_path
