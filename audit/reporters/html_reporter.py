"""
HTML 报告生成器

使用 Jinja2 模板生成可视化 HTML 报告
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from collections import Counter

from audit.reporters.base import BaseReporter
from audit.core.models import AnalysisResult, Severity


class HtmlReporter(BaseReporter):
    """HTML 报告生成器"""

    def __init__(self, template_dir: Optional[str] = None):
        if template_dir:
            self.template_dir = Path(template_dir)
        else:
            self.template_dir = Path(__file__).parent / "templates"

    def generate(self, results: List[AnalysisResult], output_path: Optional[str] = None):
        """
        生成 HTML 报告

        Args:
            results: 分析结果列表
            output_path: 输出路径
        """
        # 准备模板数据
        context = self._prepare_context(results)

        # 渲染 HTML
        html_content = self._render_template(context)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        else:
            print(html_content)

    def _prepare_context(self, results: List[AnalysisResult]) -> Dict[str, Any]:
        """准备模板上下文"""
        # 统计信息
        severity_counts = Counter()
        tool_counts = Counter()
        language_counts = Counter()

        for result in results:
            language_counts[result.language] += len(result.issues)
            for issue in result.issues:
                severity_counts[issue.severity.value] += 1
                tool_counts[issue.tool] += 1

        # 仓库详情
        repos = []
        for result in results:
            repo_data = {
                'name': result.repo,
                'language': result.language,
                'analyzer': result.analyzer,
                'files_scanned': result.files_scanned,
                'lines_scanned': result.lines_scanned,
                'issue_count': len(result.issues),
                'duration': f"{result.duration_seconds:.2f}s",
                'issues': [
                    {
                        'file': issue.file,
                        'line': issue.line,
                        'column': issue.column,
                        'severity': issue.severity.value,
                        'message': issue.message,
                        'rule': issue.rule,
                        'tool': issue.tool,
                    }
                    for issue in sorted(
                        result.issues,
                        key=lambda x: list(Severity).index(x.severity)
                    )
                ]
            }
            repos.append(repo_data)

        return {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_repos': len(results),
            'total_files': sum(r.files_scanned for r in results),
            'total_issues': sum(len(r.issues) for r in results),
            'total_duration': f"{sum(r.duration_seconds for r in results):.2f}s",
            'severity_counts': dict(severity_counts),
            'tool_counts': dict(tool_counts),
            'language_counts': dict(language_counts),
            'repos': repos,
        }

    def _render_template(self, context: Dict[str, Any]) -> str:
        """渲染 HTML 模板"""
        # 先尝试使用 Jinja2
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            if self.template_dir.exists():
                env = Environment(
                    loader=FileSystemLoader(str(self.template_dir)),
                    autoescape=select_autoescape(['html'])
                )
                template = env.get_template('report.html')
                return template.render(**context)
        except ImportError:
            pass
        except Exception:
            pass

        # 回退到内置模板
        return self._builtin_template(context)

    def _builtin_template(self, ctx: Dict[str, Any]) -> str:
        """内置 HTML 模板"""
        severity_colors = {
            'critical': '#dc3545',
            'high': '#fd7e14',
            'medium': '#ffc107',
            'low': '#17a2b8',
            'info': '#6c757d',
        }

        # 生成仓库 HTML
        repos_html = ""
        for repo in ctx['repos']:
            issues_html = ""
            for issue in repo['issues'][:100]:  # 限制显示数量
                color = severity_colors.get(issue['severity'], '#6c757d')
                issues_html += f"""
                <tr>
                    <td><span class="badge" style="background-color: {color}">{issue['severity']}</span></td>
                    <td><code>{issue['file']}:{issue['line']}</code></td>
                    <td>{issue['message']}</td>
                    <td><code>{issue['rule']}</code></td>
                </tr>
                """

            if len(repo['issues']) > 100:
                issues_html += f"""
                <tr>
                    <td colspan="4" class="text-center text-muted">
                        ... 还有 {len(repo['issues']) - 100} 个问题
                    </td>
                </tr>
                """

            repos_html += f"""
            <div class="repo-card">
                <h3>{repo['name']} <small class="text-muted">({repo['language']})</small></h3>
                <div class="repo-stats">
                    <span>分析器: <strong>{repo['analyzer']}</strong></span>
                    <span>文件数: <strong>{repo['files_scanned']}</strong></span>
                    <span>问题数: <strong class="{'text-danger' if repo['issue_count'] > 0 else 'text-success'}">{repo['issue_count']}</strong></span>
                    <span>耗时: <strong>{repo['duration']}</strong></span>
                </div>
                <table class="table">
                    <thead>
                        <tr>
                            <th>级别</th>
                            <th>位置</th>
                            <th>问题</th>
                            <th>规则</th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues_html if issues_html else '<tr><td colspan="4" class="text-center text-success">✓ 无问题</td></tr>'}
                    </tbody>
                </table>
            </div>
            """

        # 生成统计 HTML
        severity_html = ""
        for sev, count in ctx['severity_counts'].items():
            color = severity_colors.get(sev, '#6c757d')
            severity_html += f'<span class="badge" style="background-color: {color}">{sev}: {count}</span> '

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码审计报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #2c3e50; margin-bottom: 10px; }}
        h3 {{ color: #2c3e50; margin-bottom: 15px; }}
        .header {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .stat-card .value {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .stat-card .label {{ color: #7f8c8d; font-size: 0.9em; }}
        .repo-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .repo-stats {{ display: flex; gap: 20px; margin-bottom: 15px; flex-wrap: wrap; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        .table th, .table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
        .table th {{ background: #f8f9fa; font-weight: 600; }}
        .table tr:hover {{ background: #f8f9fa; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; color: white; font-size: 0.8em; font-weight: 600; }}
        code {{ background: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
        small {{ font-size: 0.8em; }}
        .text-muted {{ color: #7f8c8d; }}
        .text-danger {{ color: #dc3545; }}
        .text-success {{ color: #28a745; }}
        .text-center {{ text-align: center; }}
        .section {{ margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 代码审计报告</h1>
            <p class="text-muted">生成时间: {ctx['generated_at']}</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="value">{ctx['total_repos']}</div>
                <div class="label">审计仓库</div>
            </div>
            <div class="stat-card">
                <div class="value">{ctx['total_files']}</div>
                <div class="label">扫描文件</div>
            </div>
            <div class="stat-card">
                <div class="value">{ctx['total_issues']}</div>
                <div class="label">发现问题</div>
            </div>
            <div class="stat-card">
                <div class="value">{ctx['total_duration']}</div>
                <div class="label">总耗时</div>
            </div>
        </div>

        <div class="section">
            <h2>📊 统计概览</h2>
            <div class="repo-card">
                <h3>严重级别分布</h3>
                <p>{severity_html if severity_html else '<span class="text-success">✓ 无问题</span>'}</p>
            </div>
        </div>

        <div class="section">
            <h2>📁 仓库详情</h2>
            {repos_html}
        </div>
    </div>
</body>
</html>
"""
