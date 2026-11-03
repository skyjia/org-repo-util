"""
终端摘要报告生成器

使用 rich 库生成格式化的终端输出
"""

from typing import List, Optional, Dict
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from audit.reporters.base import BaseReporter
from audit.core.models import AnalysisResult, Severity


class ConsoleReporter(BaseReporter):
    """终端摘要报告生成器"""

    def __init__(self):
        self.console = Console()

        # 严重级别颜色映射
        self.severity_colors = {
            Severity.CRITICAL: "bold red",
            Severity.HIGH: "red",
            Severity.MEDIUM: "yellow",
            Severity.LOW: "blue",
            Severity.INFO: "dim",
        }

    def generate(self, results: List[AnalysisResult], output_path: Optional[str] = None):
        """
        生成终端摘要

        Args:
            results: 分析结果列表
            output_path: 输出路径（终端报告不使用）
        """
        if not results:
            self.console.print("[yellow]没有审计结果[/yellow]")
            return

        # 1. 汇总表
        self._print_summary_table(results)

        # 2. 统计信息
        self._print_statistics(results)

        # 3. 详细问题列表
        for result in results:
            if result.issues:
                self._print_repo_details(result)

    def _print_summary_table(self, results: List[AnalysisResult]):
        """打印汇总表"""
        table = Table(
            title="代码审计结果汇总",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("仓库", style="cyan", max_width=40)
        table.add_column("语言", style="magenta")
        table.add_column("分析器", style="dim")
        table.add_column("文件数", justify="right", style="green")
        table.add_column("问题数", justify="right", style="red")
        table.add_column("耗时", justify="right", style="blue")

        total_files = 0
        total_issues = 0
        total_duration = 0.0

        for result in results:
            total_files += result.files_scanned
            total_issues += len(result.issues)
            total_duration += result.duration_seconds

            # 问题数颜色编码
            issue_count = len(result.issues)
            if issue_count == 0:
                issue_style = "green"
            elif issue_count < 100:
                issue_style = "yellow"
            else:
                issue_style = "red"

            table.add_row(
                result.repo,
                result.language,
                result.analyzer,
                str(result.files_scanned),
                f"[{issue_style}]{issue_count}[/{issue_style}]",
                f"{result.duration_seconds:.2f}s"
            )

        # 总计行
        table.add_row(
            "[bold]总计[/bold]",
            "",
            "",
            f"[bold]{total_files}[/bold]",
            f"[bold red]{total_issues}[/bold red]",
            f"[bold]{total_duration:.2f}s[/bold]"
        )

        self.console.print()
        self.console.print(table)
        self.console.print()

    def _print_statistics(self, results: List[AnalysisResult]):
        """打印统计信息"""
        # 按严重级别统计
        severity_counts = Counter()
        tool_counts = Counter()
        dimension_counts = Counter()
        top_files = Counter()

        for result in results:
            for issue in result.issues:
                severity_counts[issue.severity] += 1
                tool_counts[issue.tool] += 1
                dimension_counts[issue.dimension] += 1
                # 使用相对路径
                rel_file = issue.file.split('/')[-1] if '/' in issue.file else issue.file
                top_files[rel_file] += 1

        total_issues = sum(severity_counts.values())
        if total_issues == 0:
            return

        # 严重级别分布
        severity_text = Text()
        severity_text.append("严重级别分布: ", style="bold")
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            count = severity_counts.get(severity, 0)
            if count > 0:
                pct = (count / total_issues) * 100
                color = self.severity_colors[severity]
                severity_text.append(f"{severity.value}={count}({pct:.1f}%) ", style=color)

        self.console.print(severity_text)

        # Top 问题文件
        if top_files:
            self.console.print("\n[bold]问题最多的文件 (Top 5):[/bold]")
            for file, count in top_files.most_common(5):
                self.console.print(f"  {count:4d}  {file}")

    def _print_repo_details(self, result: AnalysisResult):
        """打印仓库详情"""
        self.console.print()
        self.console.print(f"[bold cyan]{result.repo}[/bold cyan] ({result.language})")
        self.console.print(f"  扫描文件: {result.files_scanned}")
        self.console.print(f"  发现问题: {len(result.issues)}")

        if result.issues:
            self.console.print("  [bold]问题列表:[/bold]")

            # 按严重级别排序
            sorted_issues = sorted(
                result.issues,
                key=lambda x: list(Severity).index(x.severity)
            )

            for issue in sorted_issues[:10]:  # 只显示前10个
                # 使用 markup=False 避免路径中的特殊字符被解释为 rich markup
                color = self.severity_colors.get(issue.severity, "white")
                severity_tag = issue.severity.value.upper()

                # 构造输出文本，避免 rich markup 解析问题
                file_info = f"{issue.file}:{issue.line}"
                msg = issue.message

                # 使用 Text 对象避免 markup 问题
                line = Text()
                line.append(f"    [{severity_tag}] ", style=color)
                line.append(f"{file_info} ", style="dim")
                line.append(f"- {msg}")

                self.console.print(line)

            if len(result.issues) > 10:
                self.console.print(
                    f"    [dim]... 还有 {len(result.issues) - 10} 个问题[/dim]"
                )
