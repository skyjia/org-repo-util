"""
报告存储管理器 - 管理审计报告的存储和索引
"""

import json
import shutil
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class ReportStorage:
    """报告存储管理器"""

    def __init__(self, reports_dir: Optional[str] = None):
        """
        初始化报告存储

        Args:
            reports_dir: 报告根目录，默认为项目根目录下的 reports/
        """
        if reports_dir:
            self.reports_dir = Path(reports_dir)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.reports_dir = project_root / "reports"

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.reports_dir / "reports.json"

    def save_report(
        self,
        org: str,
        repo: str,
        report_data: Dict[str, Any],
        formats: List[str] = None
    ) -> Dict[str, Path]:
        """
        保存审计报告

        Args:
            org: 组织名
            repo: 仓库名
            report_data: 报告数据
            formats: 输出格式列表 ['json', 'html']

        Returns:
            生成的报告文件路径字典
        """
        if formats is None:
            formats = ['json', 'html']

        # 创建时间戳目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = self.reports_dir / org / repo / timestamp
        report_dir.mkdir(parents=True, exist_ok=True)

        saved_files = {}

        # 保存 JSON 报告
        if 'json' in formats:
            json_path = report_dir / "report.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            saved_files['json'] = json_path

        # 保存 HTML 报告
        if 'html' in formats:
            from audit.reporters.html_reporter import HtmlReporter
            from audit.core.models import AnalysisResult

            # 从 report_data 重建 AnalysisResult 列表
            results = []
            for r in report_data.get('results', []):
                from audit.core.models import Issue, Severity
                issues = [
                    Issue(
                        file=i['file'],
                        line=i['line'],
                        column=i['column'],
                        severity=Severity(i['severity']),
                        message=i['message'],
                        rule=i['rule'],
                        tool=i['tool'],
                        dimension=i['dimension'],
                    )
                    for i in r.get('issues', [])
                ]
                results.append(AnalysisResult(
                    repo=r['repo'],
                    language=r['language'],
                    analyzer=r['analyzer'],
                    issues=issues,
                    files_scanned=r['files_scanned'],
                    lines_scanned=r['lines_scanned'],
                    duration_seconds=r['duration_seconds'],
                    error=r.get('error'),
                ))

            html_path = report_dir / "report.html"
            reporter = HtmlReporter()
            reporter.generate(results, str(html_path))
            saved_files['html'] = html_path

        # 更新 latest 符号链接
        self._update_latest_link(org, repo, report_dir)

        # 更新索引
        self._update_index(org, repo, timestamp, report_dir)

        logger.info(f"报告已保存: {report_dir}")
        return saved_files

    def _update_latest_link(self, org: str, repo: str, report_dir: Path):
        """更新 latest 符号链接"""
        latest_link = self.reports_dir / org / repo / "latest"

        try:
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(report_dir.name)
        except OSError as e:
            logger.warning(f"无法创建 latest 符号链接: {e}")

    def _update_index(self, org: str, repo: str, timestamp: str, report_dir: Path):
        """更新报告索引"""
        index = self._load_index()

        # 确保结构存在
        if org not in index:
            index[org] = {}
        if repo not in index[org]:
            index[org][repo] = []

        # 添加新记录
        record = {
            'timestamp': timestamp,
            'path': str(report_dir.relative_to(self.reports_dir)),
            'created_at': datetime.now().isoformat(),
        }

        # 避免重复
        index[org][repo] = [r for r in index[org][repo] if r['timestamp'] != timestamp]
        index[org][repo].append(record)

        # 按时间排序（最新的在前）
        index[org][repo].sort(key=lambda x: x['timestamp'], reverse=True)

        # 保存索引
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _load_index(self) -> Dict[str, Any]:
        """加载报告索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载索引失败: {e}")
        return {}

    def list_reports(self, org: Optional[str] = None, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出报告

        Args:
            org: 组织名过滤
            repo: 仓库名过滤

        Returns:
            报告列表
        """
        index = self._load_index()
        reports = []

        for o, repos in index.items():
            if org and o != org:
                continue
            for r, records in repos.items():
                if repo and r != repo:
                    continue
                for record in records:
                    reports.append({
                        'org': o,
                        'repo': r,
                        **record,
                    })

        # 按时间排序
        reports.sort(key=lambda x: x['timestamp'], reverse=True)
        return reports

    def clean_old_reports(self, days: int = 30) -> int:
        """
        清理旧报告

        Args:
            days: 保留天数

        Returns:
            清理的报告数量
        """
        cutoff = datetime.now().timestamp() - days * 86400
        cleaned = 0

        # 遍历所有报告目录
        for org_dir in self.reports_dir.iterdir():
            if not org_dir.is_dir() or org_dir.name == ".git":
                continue

            for repo_dir in org_dir.iterdir():
                if not repo_dir.is_dir():
                    continue

                for timestamp_dir in repo_dir.iterdir():
                    if not timestamp_dir.is_dir() or timestamp_dir.name == "latest":
                        continue

                    # 检查时间戳
                    try:
                        dir_time = datetime.strptime(
                            timestamp_dir.name, "%Y%m%d_%H%M%S"
                        ).timestamp()

                        if dir_time < cutoff:
                            shutil.rmtree(timestamp_dir)
                            cleaned += 1
                            logger.info(f"清理旧报告: {timestamp_dir}")
                    except ValueError:
                        continue

        # 更新索引
        self._rebuild_index()

        return cleaned

    def _rebuild_index(self):
        """重建索引"""
        index = {}

        for org_dir in self.reports_dir.iterdir():
            if not org_dir.is_dir():
                continue

            org = org_dir.name
            index[org] = {}

            for repo_dir in org_dir.iterdir():
                if not repo_dir.is_dir():
                    continue

                repo = repo_dir.name
                index[org][repo] = []

                for timestamp_dir in repo_dir.iterdir():
                    if not timestamp_dir.is_dir() or timestamp_dir.name == "latest":
                        continue

                    index[org][repo].append({
                        'timestamp': timestamp_dir.name,
                        'path': str(timestamp_dir.relative_to(self.reports_dir)),
                        'created_at': datetime.fromtimestamp(
                            timestamp_dir.stat().st_mtime
                        ).isoformat(),
                    })

                # 排序
                index[org][repo].sort(key=lambda x: x['timestamp'], reverse=True)

                # 清理空仓库
                if not index[org][repo]:
                    del index[org][repo]

            # 清理空组织
            if not index[org]:
                del index[org]

        # 保存
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
