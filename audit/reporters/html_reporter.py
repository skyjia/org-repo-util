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
        rule_counts = Counter()

        for result in results:
            language_counts[result.language] += len(result.issues)
            for issue in result.issues:
                severity_counts[issue.severity.value] += 1
                tool_counts[issue.tool] += 1
                # 处理 None 值的 rule
                rule_name = issue.rule if issue.rule else '(unknown)'
                rule_counts[rule_name] += 1

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
                        'rule': issue.rule if issue.rule else '(unknown)',
                        'tool': issue.tool,
                    }
                    for issue in sorted(
                        result.issues,
                        key=lambda x: list(Severity).index(x.severity)
                    )
                ]
            }
            repos.append(repo_data)

        # 判断是否为单仓库报告
        is_single_repo = len(results) == 1

        return {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_repos': len(results),
            'total_files': sum(r.files_scanned for r in results),
            'total_issues': sum(len(r.issues) for r in results),
            'total_duration': f"{sum(r.duration_seconds for r in results):.2f}s",
            'severity_counts': dict(severity_counts),
            'tool_counts': dict(tool_counts),
            'language_counts': dict(language_counts),
            'rule_counts': dict(rule_counts),
            'repos': repos,
            'is_single_repo': is_single_repo,
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

        # 生成统计卡片 HTML（单仓库移除「审计仓库」）
        stats_html = ""
        if not ctx['is_single_repo']:
            stats_html += f"""
            <div class="stat-card">
                <div class="value">{ctx['total_repos']}</div>
                <div class="label">审计仓库</div>
            </div>
            """
        stats_html += f"""
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
        """

        # 生成规则列表（用于下拉选择）
        rules = sorted(ctx['rule_counts'].keys())
        rules_options = '<option value="">全部规则</option>'
        for rule in rules:
            count = ctx['rule_counts'][rule]
            rules_options += f'<option value="{rule}">{rule} ({count})</option>'

        # 生成仓库 HTML
        repos_html = ""
        for repo in ctx['repos']:
            repos_html += f"""
            <div class="repo-card">
                <h3>{repo['name']} <small class="text-muted">({repo['language']})</small></h3>
                <div class="repo-stats">
                    <span>分析器: <strong>{repo['analyzer']}</strong></span>
                    <span>文件数: <strong>{repo['files_scanned']}</strong></span>
                    <span>问题数: <strong class="{'text-danger' if repo['issue_count'] > 0 else 'text-success'}">{repo['issue_count']}</strong></span>
                    <span>耗时: <strong>{repo['duration']}</strong></span>
                </div>

                <div class="filters">
                    <div class="filter-group">
                        <label>严重级别:</label>
                        <div class="severity-buttons">
                            <button class="filter-btn active" data-severity="all">全部</button>
                            <button class="filter-btn" data-severity="critical" style="border-color: #dc3545">Critical</button>
                            <button class="filter-btn" data-severity="high" style="border-color: #fd7e14">High</button>
                            <button class="filter-btn" data-severity="medium" style="border-color: #ffc107">Medium</button>
                            <button class="filter-btn" data-severity="low" style="border-color: #17a2b8">Low</button>
                            <button class="filter-btn" data-severity="info" style="border-color: #6c757d">Info</button>
                        </div>
                    </div>

                    <div class="filter-group">
                        <label>规则:</label>
                        <select class="rule-select">
                            {rules_options}
                        </select>
                    </div>

                    <div class="filter-group">
                        <label>每页显示:</label>
                        <select class="page-size-select">
                            <option value="50">50 条</option>
                            <option value="100" selected>100 条</option>
                            <option value="200">200 条</option>
                        </select>
                    </div>

                    <button class="clear-btn">清除筛选</button>
                </div>

                <div class="filter-info" style="display: none;">
                    <span class="filter-info-text"></span>
                </div>

                <table class="table issues-table">
                    <thead>
                        <tr>
                            <th>级别</th>
                            <th>位置</th>
                            <th>问题</th>
                            <th>规则</th>
                        </tr>
                    </thead>
                    <tbody class="issues-body">
            """

            # 生成所有问题的 HTML（隐藏，通过 JS 控制显示）
            for i, issue in enumerate(repo['issues']):
                color = severity_colors.get(issue['severity'], '#6c757d')
                repos_html += f"""
                        <tr class="issue-row"
                            data-severity="{issue['severity']}"
                            data-rule="{issue['rule']}"
                            data-index="{i}"
                            style="display: none;">
                            <td><span class="badge" style="background-color: {color}">{issue['severity']}</span></td>
                            <td><code>{issue['file']}:{issue['line']}</code></td>
                            <td>{issue['message']}</td>
                            <td><code>{issue['rule']}</code></td>
                        </tr>
                """

            repos_html += """
                    </tbody>
                </table>

                <div class="pagination">
                    <button class="page-btn prev-page" disabled>上一页</button>
                    <span class="page-info">第 1 页</span>
                    <button class="page-btn next-page">下一页</button>
                </div>

                <div class="no-results" style="display: none;">
                    <p>🔍 没有匹配的问题</p>
                </div>
            </div>
            """

        # 生成统计概览 HTML
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
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ color: #2c3e50; margin-bottom: 10px; }}
        h2 {{ color: #2c3e50; margin-bottom: 15px; }}
        h3 {{ color: #2c3e50; margin-bottom: 15px; }}
        .header {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .stat-card .value {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .stat-card .label {{ color: #7f8c8d; font-size: 0.9em; }}
        .repo-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .stats-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .repo-stats {{ display: flex; gap: 20px; margin-bottom: 15px; flex-wrap: wrap; }}
        .filters {{ background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 15px; display: flex; gap: 20px; flex-wrap: wrap; align-items: center; }}
        .filter-group {{ display: flex; align-items: center; gap: 10px; }}
        .filter-group label {{ font-weight: 600; color: #495057; }}
        .severity-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .filter-btn {{ padding: 6px 12px; border: 2px solid #e0e0e0; background: white; border-radius: 4px; cursor: pointer; font-size: 0.85em; transition: all 0.2s; }}
        .filter-btn:hover {{ background: #f8f9fa; }}
        .filter-btn.active {{ background: #667eea; color: white; border-color: #667eea; }}
        .rule-select, .page-size-select {{ padding: 6px 12px; border: 2px solid #e0e0e0; border-radius: 4px; font-size: 0.85em; background: white; cursor: pointer; }}
        .clear-btn {{ padding: 6px 16px; border: 2px solid #dc3545; background: white; color: #dc3545; border-radius: 4px; cursor: pointer; font-size: 0.85em; transition: all 0.2s; }}
        .clear-btn:hover {{ background: #dc3545; color: white; }}
        .filter-info {{ background: #e3f2fd; padding: 10px 15px; border-radius: 4px; margin-bottom: 15px; color: #1976d2; font-size: 0.9em; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        .table th, .table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
        .table th {{ background: #f8f9fa; font-weight: 600; position: sticky; top: 0; }}
        .table tr:hover {{ background: #f8f9fa; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; color: white; font-size: 0.8em; font-weight: 600; }}
        code {{ background: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
        small {{ font-size: 0.8em; }}
        .text-muted {{ color: #7f8c8d; }}
        .text-danger {{ color: #dc3545; }}
        .text-success {{ color: #28a745; }}
        .text-center {{ text-align: center; }}
        .section {{ margin-bottom: 30px; }}
        .pagination {{ display: flex; justify-content: center; align-items: center; gap: 15px; margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 6px; }}
        .page-btn {{ padding: 8px 16px; border: 2px solid #667eea; background: white; color: #667eea; border-radius: 4px; cursor: pointer; font-size: 0.9em; transition: all 0.2s; }}
        .page-btn:hover:not(:disabled) {{ background: #667eea; color: white; }}
        .page-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .page-info {{ font-weight: 600; color: #495057; }}
        .no-results {{ text-align: center; padding: 40px; color: #7f8c8d; font-size: 1.1em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 代码审计报告</h1>
            <p class="text-muted">生成时间: {ctx['generated_at']}</p>
        </div>

        <div class="stats">
            {stats_html}
        </div>

        <div class="section">
            <h2>📊 统计概览</h2>
            <div class="stats-card">
                <h3>严重级别分布</h3>
                <p>{severity_html if severity_html else '<span class="text-success">✓ 无问题</span>'}</p>
            </div>
        </div>

        <div class="section">
            <h2>📁 仓库详情</h2>
            {repos_html}
        </div>
    </div>

    <script>
        // 初始化所有仓库的筛选和分页
        document.querySelectorAll('.repo-card').forEach(card => {{
            const issues = Array.from(card.querySelectorAll('.issue-row'));
            const totalIssues = issues.length;

            let currentSeverity = 'all';
            let currentRule = '';
            let currentPage = 1;
            let pageSize = 100;

            // 显示所有问题（初始状态）
            function updateDisplay() {{
                const filtered = issues.filter(issue => {{
                    const severityMatch = currentSeverity === 'all' || issue.dataset.severity === currentSeverity;
                    const ruleMatch = !currentRule || issue.dataset.rule === currentRule;
                    return severityMatch && ruleMatch;
                }});

                // 更新筛选信息
                const filterInfo = card.querySelector('.filter-info');
                const filterInfoText = card.querySelector('.filter-info-text');
                if (currentSeverity !== 'all' || currentRule) {{
                    filterInfo.style.display = 'block';
                    filterInfoText.textContent = `显示 ${{filtered.length}} / ${{totalIssues}} 个问题`;
                }} else {{
                    filterInfo.style.display = 'none';
                }}

                // 分页处理
                const totalPages = Math.ceil(filtered.length / pageSize) || 1;
                if (currentPage > totalPages) currentPage = totalPages;

                const startIndex = (currentPage - 1) * pageSize;
                const endIndex = startIndex + pageSize;

                // 隐藏所有问题
                issues.forEach(issue => issue.style.display = 'none');

                // 显示当前页的问题
                const pageIssues = filtered.slice(startIndex, endIndex);
                pageIssues.forEach(issue => issue.style.display = '');

                // 更新分页信息
                const pagination = card.querySelector('.pagination');
                const pageInfo = card.querySelector('.page-info');
                const prevBtn = card.querySelector('.prev-page');
                const nextBtn = card.querySelector('.next-page');
                const noResults = card.querySelector('.no-results');

                if (filtered.length === 0) {{
                    pagination.style.display = 'none';
                    noResults.style.display = 'block';
                }} else {{
                    pagination.style.display = 'flex';
                    noResults.style.display = 'none';
                    pageInfo.textContent = `第 ${{currentPage}} / ${{totalPages}} 页 (${{startIndex + 1}}-${{Math.min(endIndex, filtered.length)}} / ${{filtered.length}})`;
                    prevBtn.disabled = currentPage === 1;
                    nextBtn.disabled = currentPage === totalPages;
                }}
            }}

            // 严重级别筛选
            card.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.addEventListener('click', function() {{
                    card.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentSeverity = this.dataset.severity;
                    currentPage = 1;
                    updateDisplay();
                }});
            }});

            // 规则筛选
            card.querySelector('.rule-select').addEventListener('change', function() {{
                currentRule = this.value;
                currentPage = 1;
                updateDisplay();
            }});

            // 每页显示数量
            card.querySelector('.page-size-select').addEventListener('change', function() {{
                pageSize = parseInt(this.value);
                currentPage = 1;
                updateDisplay();
            }});

            // 清除筛选
            card.querySelector('.clear-btn').addEventListener('click', function() {{
                currentSeverity = 'all';
                currentRule = '';
                currentPage = 1;
                card.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                card.querySelector('.filter-btn[data-severity="all"]').classList.add('active');
                card.querySelector('.rule-select').value = '';
                updateDisplay();
            }});

            // 分页按钮
            card.querySelector('.prev-page').addEventListener('click', function() {{
                if (currentPage > 1) {{
                    currentPage--;
                    updateDisplay();
                }}
            }});

            card.querySelector('.next-page').addEventListener('click', function() {{
                const filtered = issues.filter(issue => {{
                    const severityMatch = currentSeverity === 'all' || issue.dataset.severity === currentSeverity;
                    const ruleMatch = !currentRule || issue.dataset.rule === currentRule;
                    return severityMatch && ruleMatch;
                }});
                const totalPages = Math.ceil(filtered.length / pageSize);
                if (currentPage < totalPages) {{
                    currentPage++;
                    updateDisplay();
                }}
            }});

            // 初始显示
            updateDisplay();
        }});
    </script>
</body>
</html>
"""
