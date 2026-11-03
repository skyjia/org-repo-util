"""
报告索引生成器 - 生成 reports/index.html
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging

from jinja2 import Template

logger = logging.getLogger(__name__)


class IndexGenerator:
    """报告索引生成器"""

    def __init__(self, reports_dir: str = "reports"):
        """
        初始化索引生成器

        Args:
            reports_dir: 报告根目录
        """
        self.reports_dir = Path(reports_dir)

    def generate_index(self) -> str:
        """
        生成索引页 HTML

        Returns:
            生成的 index.html 路径
        """
        if not self.reports_dir.exists():
            logger.warning(f"报告目录不存在: {self.reports_dir}")
            return ""

        # 1. 扫描所有报告
        reports = self._scan_all_reports()
        if not reports:
            logger.info("没有找到任何报告")
            return ""

        # 2. 按组织分组
        orgs = self._group_by_org(reports)

        # 3. 计算统计信息
        stats = self._calculate_stats(reports)

        # 4. 渲染 HTML
        html = self._render_index(orgs, stats)

        # 5. 写入文件
        output_path = self.reports_dir / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"索引页已生成: {output_path}")
        return str(output_path)

    def _scan_all_reports(self) -> List[Dict[str, Any]]:
        """
        扫描所有报告并提取元数据

        Returns:
            报告元数据列表
        """
        reports = []

        # 遍历 reports/<org>/<repo>/<timestamp>/ 结构
        for org_dir in self.reports_dir.iterdir():
            if not org_dir.is_dir() or org_dir.name.startswith('.'):
                continue

            for repo_dir in org_dir.iterdir():
                if not repo_dir.is_dir() or repo_dir.name.startswith('.'):
                    continue

                # 查找最新的报告（latest 符号链接或最新的时间戳目录）
                latest_report = self._get_latest_report(repo_dir)
                if not latest_report:
                    continue

                # 读取报告元数据
                report_info = self._extract_report_info(org_dir.name, repo_dir.name, latest_report)
                if report_info:
                    reports.append(report_info)

        return reports

    def _get_latest_report(self, repo_dir: Path) -> Path:
        """
        获取仓库最新的报告目录

        Args:
            repo_dir: 仓库目录

        Returns:
            最新报告目录路径
        """
        # 优先使用 latest 符号链接
        latest_link = repo_dir / "latest"
        if latest_link.exists() and latest_link.is_symlink():
            return latest_link.resolve()

        # 否则查找最新的时间戳目录
        timestamp_dirs = []
        for subdir in repo_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                try:
                    # 尝试解析为时间戳
                    datetime.strptime(subdir.name, "%Y%m%d_%H%M%S")
                    timestamp_dirs.append(subdir)
                except ValueError:
                    continue

        if not timestamp_dirs:
            return None

        # 返回最新的
        return max(timestamp_dirs, key=lambda x: x.name)

    def _extract_report_info(self, org: str, repo: str, report_dir: Path) -> Dict[str, Any]:
        """
        提取报告元数据

        Args:
            org: 组织名
            repo: 仓库名
            report_dir: 报告目录

        Returns:
            报告元数据字典
        """
        # 查找 JSON 报告文件
        json_files = list(report_dir.glob("report.json"))
        if not json_files:
            return None

        json_file = json_files[0]

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 提取关键信息
            metadata = data.get('metadata', {})
            results = data.get('results', [])

            if not results:
                return None

            result = results[0]  # 单个仓库报告

            # 统计问题数
            issues = result.get('issues', [])
            issue_count = len(issues)

            # 按严重程度统计
            severity_counts = {}
            for issue in issues:
                severity = issue.get('severity', 'unknown')
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

            return {
                'org': org,
                'repo': repo,
                'language': result.get('language', 'unknown'),
                'analyzer': result.get('analyzer', 'unknown'),
                'issue_count': issue_count,
                'severity_counts': severity_counts,
                'files_scanned': result.get('files_scanned', 0),
                'duration_seconds': result.get('duration_seconds', 0),
                'generated_at': metadata.get('generated_at', ''),
                'timestamp': report_dir.name,
                'html_path': f"{org}/{repo}/{report_dir.name}/report.html",
                'json_path': f"{org}/{repo}/{report_dir.name}/report.json",
            }

        except Exception as e:
            logger.warning(f"读取报告失败 {json_file}: {e}")
            return None

    def _group_by_org(self, reports: List[Dict]) -> Dict[str, List[Dict]]:
        """
        按组织分组报告

        Args:
            reports: 报告列表

        Returns:
            组织到报告列表的映射
        """
        orgs = {}
        for report in reports:
            org = report['org']
            if org not in orgs:
                orgs[org] = []
            orgs[org].append(report)

        # 按仓库名排序
        for org in orgs:
            orgs[org].sort(key=lambda x: x['repo'])

        return orgs

    def _calculate_stats(self, reports: List[Dict]) -> Dict[str, Any]:
        """
        计算统计信息

        Args:
            reports: 报告列表

        Returns:
            统计信息字典
        """
        total_repos = len(reports)
        total_issues = sum(r['issue_count'] for r in reports)
        total_files = sum(r['files_scanned'] for r in reports)

        # 语言分布
        language_counts = {}
        for report in reports:
            lang = report['language']
            language_counts[lang] = language_counts.get(lang, 0) + 1

        # 严重程度分布
        severity_totals = {}
        for report in reports:
            for severity, count in report['severity_counts'].items():
                severity_totals[severity] = severity_totals.get(severity, 0) + count

        return {
            'total_repos': total_repos,
            'total_issues': total_issues,
            'total_files': total_files,
            'language_counts': language_counts,
            'severity_totals': severity_totals,
        }

    def _render_index(self, orgs: Dict[str, List[Dict]], stats: Dict[str, Any]) -> str:
        """
        渲染索引页 HTML

        Args:
            orgs: 组织到报告列表的映射
            stats: 统计信息

        Returns:
            HTML 字符串
        """
        template_str = self._get_index_template()
        template = Template(template_str)

        html = template.render(
            orgs=orgs,
            stats=stats,
            generated_at=datetime.now().isoformat(),
        )

        return html

    def _get_index_template(self) -> str:
        """
        获取索引页 HTML 模板

        Returns:
            Jinja2 模板字符串
        """
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码审计报告索引</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        header {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .meta {
            color: #666;
            font-size: 0.9em;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .stat-label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }

        .controls {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .search-box {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            margin-bottom: 15px;
        }

        .search-box:focus {
            outline: none;
            border-color: #667eea;
        }

        .sort-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .sort-btn {
            padding: 8px 16px;
            border: 2px solid #e0e0e0;
            background: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s;
        }

        .sort-btn:hover {
            border-color: #667eea;
            background: #f5f5f5;
        }

        .sort-btn.active {
            border-color: #667eea;
            background: #667eea;
            color: white;
        }

        .org-section {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .org-header {
            font-size: 1.5em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
            color: #667eea;
        }

        .repo-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
        }

        .repo-card {
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            transition: all 0.2s;
            cursor: pointer;
        }

        .repo-card:hover {
            border-color: #667eea;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
            transform: translateY(-2px);
        }

        .repo-name {
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 10px;
            color: #333;
        }

        .repo-meta {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }

        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 500;
        }

        .badge-language {
            background: #e3f2fd;
            color: #1976d2;
        }

        .badge-issues {
            background: #ffebee;
            color: #c62828;
        }

        .badge-time {
            background: #f5f5f5;
            color: #666;
        }

        .severity-bar {
            display: flex;
            height: 6px;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 10px;
        }

        .severity-segment {
            height: 100%;
        }

        .severity-critical { background: #d32f2f; }
        .severity-high { background: #f44336; }
        .severity-medium { background: #ff9800; }
        .severity-low { background: #2196f3; }
        .severity-info { background: #9e9e9e; }

        .no-reports {
            text-align: center;
            padding: 60px 20px;
            color: #999;
        }

        @media (max-width: 768px) {
            h1 {
                font-size: 1.8em;
            }

            .repo-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 代码审计报告索引</h1>
            <div class="meta">
                生成时间: {{ generated_at[:19] }}
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">总仓库数</div>
                <div class="stat-value">{{ stats.total_repos }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">总问题数</div>
                <div class="stat-value">{{ stats.total_issues }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">已扫描文件</div>
                <div class="stat-value">{{ stats.total_files }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">语言种类</div>
                <div class="stat-value">{{ stats.language_counts|length }}</div>
            </div>
        </div>

        <div class="controls">
            <input type="text" class="search-box" id="searchBox" placeholder="🔍 搜索仓库名或语言...">
            <div class="sort-buttons">
                <button class="sort-btn active" data-sort="name">按名称</button>
                <button class="sort-btn" data-sort="issues">按问题数</button>
                <button class="sort-btn" data-sort="language">按语言</button>
                <button class="sort-btn" data-sort="time">按时间</button>
            </div>
        </div>

        {% if not orgs %}
        <div class="no-reports">
            <p>📭 暂无审计报告</p>
            <p>运行 <code>audit repo &lt;path&gt; --save</code> 或 <code>audit org &lt;name&gt; --save</code> 生成报告</p>
        </div>
        {% else %}
        {% for org, repos in orgs.items() %}
        <div class="org-section" data-org="{{ org }}">
            <h2 class="org-header">{{ org }} ({{ repos|length }})</h2>
            <div class="repo-grid">
                {% for repo in repos %}
                <div class="repo-card"
                     data-repo="{{ repo.repo|lower }}"
                     data-language="{{ repo.language|lower }}"
                     data-issues="{{ repo.issue_count }}"
                     data-time="{{ repo.generated_at }}">
                    <div class="repo-name">{{ repo.repo }}</div>
                    <div class="repo-meta">
                        <span class="badge badge-language">{{ repo.language }}</span>
                        <span class="badge badge-issues">{{ repo.issue_count }} 问题</span>
                        <span class="badge badge-time">{{ repo.generated_at[:10] }}</span>
                    </div>
                    {% if repo.severity_counts %}
                    <div class="severity-bar">
                        {% set total = repo.issue_count or 1 %}
                        {% if repo.severity_counts.get('critical', 0) > 0 %}
                        <div class="severity-segment severity-critical"
                             style="width: {{ (repo.severity_counts.critical / total * 100)|int }}%"
                             title="Critical: {{ repo.severity_counts.critical }}"></div>
                        {% endif %}
                        {% if repo.severity_counts.get('high', 0) > 0 %}
                        <div class="severity-segment severity-high"
                             style="width: {{ (repo.severity_counts.high / total * 100)|int }}%"
                             title="High: {{ repo.severity_counts.high }}"></div>
                        {% endif %}
                        {% if repo.severity_counts.get('medium', 0) > 0 %}
                        <div class="severity-segment severity-medium"
                             style="width: {{ (repo.severity_counts.medium / total * 100)|int }}%"
                             title="Medium: {{ repo.severity_counts.medium }}"></div>
                        {% endif %}
                        {% if repo.severity_counts.get('low', 0) > 0 %}
                        <div class="severity-segment severity-low"
                             style="width: {{ (repo.severity_counts.low / total * 100)|int }}%"
                             title="Low: {{ repo.severity_counts.low }}"></div>
                        {% endif %}
                        {% if repo.severity_counts.get('info', 0) > 0 %}
                        <div class="severity-segment severity-info"
                             style="width: {{ (repo.severity_counts.info / total * 100)|int }}%"
                             title="Info: {{ repo.severity_counts.info }}"></div>
                        {% endif %}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
        {% endif %}
    </div>

    <script>
        // 搜索功能
        const searchBox = document.getElementById('searchBox');
        searchBox.addEventListener('input', function() {
            const query = this.value.toLowerCase();
            const repoCards = document.querySelectorAll('.repo-card');

            repoCards.forEach(card => {
                const repoName = card.dataset.repo;
                const language = card.dataset.language;
                const match = repoName.includes(query) || language.includes(query);
                card.style.display = match ? 'block' : 'none';
            });

            // 隐藏空的组织
            document.querySelectorAll('.org-section').forEach(section => {
                const visibleCards = section.querySelectorAll('.repo-card[style*="display: block"], .repo-card:not([style])');
                section.style.display = visibleCards.length > 0 ? 'block' : 'none';
            });
        });

        // 排序功能
        const sortButtons = document.querySelectorAll('.sort-btn');
        sortButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                sortButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                const sortBy = this.dataset.sort;
                const repoGrids = document.querySelectorAll('.repo-grid');

                repoGrids.forEach(grid => {
                    const cards = Array.from(grid.querySelectorAll('.repo-card'));

                    cards.sort((a, b) => {
                        let valA, valB;

                        switch(sortBy) {
                            case 'name':
                                valA = a.dataset.repo;
                                valB = b.dataset.repo;
                                return valA.localeCompare(valB);
                            case 'issues':
                                valA = parseInt(a.dataset.issues) || 0;
                                valB = parseInt(b.dataset.issues) || 0;
                                return valB - valA; // 降序
                            case 'language':
                                valA = a.dataset.language;
                                valB = b.dataset.language;
                                return valA.localeCompare(valB);
                            case 'time':
                                valA = a.dataset.time;
                                valB = b.dataset.time;
                                return valB.localeCompare(valA); // 降序
                        }
                    });

                    cards.forEach(card => grid.appendChild(card));
                });
            });
        });

        // 点击仓库卡片跳转到报告
        document.querySelectorAll('.repo-card').forEach(card => {
            card.addEventListener('click', function() {
                const repoName = this.querySelector('.repo-name').textContent;
                const orgSection = this.closest('.org-section');
                const orgName = orgSection.dataset.org;

                // 从卡片数据中获取报告路径
                const cards = document.querySelectorAll('.repo-card');
                cards.forEach(c => {
                    if (c === this) {
                        // 查找对应的报告路径
                        const allRepos = {{ orgs|tojson }};
                        const repos = allRepos[orgName] || [];
                        const repo = repos.find(r => r.repo === repoName);
                        if (repo && repo.html_path) {
                            window.location.href = repo.html_path;
                        }
                    }
                });
            });
        });
    </script>
</body>
</html>
"""
