"""
govulncheck Go 依赖漏洞扫描器

扫描 Go 项目的依赖漏洞
使用 govulncheck 获取漏洞信息
"""

import json
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Any
import logging

from audit.core.models import Issue, Severity
from audit.core.audit_logger import get_audit_logger


logger = logging.getLogger(__name__)
audit_logger = get_audit_logger()


class GoVulnScanner:
    """govulncheck Go 依赖漏洞扫描器"""

    @property
    def name(self) -> str:
        return "govulncheck"

    @property
    def language(self) -> str:
        return "go"

    def is_applicable(self, repo_path: str) -> bool:
        """检查是否适用于该仓库"""
        repo = Path(repo_path)
        return (repo / "go.mod").exists()

    def check_prerequisites(self) -> bool:
        """检查 govulncheck 是否可用"""
        try:
            result = subprocess.run(
                ["govulncheck", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def scan(self, repo_path: str) -> List[Issue]:
        """
        执行依赖漏洞扫描

        Args:
            repo_path: 仓库路径

        Returns:
            Issue 列表
        """
        repo = Path(repo_path)
        go_mod = repo / "go.mod"

        if not go_mod.exists():
            audit_logger.warning(f"未找到 go.mod: {repo_path}")
            return []

        # 执行 govulncheck
        issues = self._run_govulncheck(repo_path)
        return issues

    def _run_govulncheck(self, repo_path: str) -> List[Issue]:
        """执行 govulncheck 并解析结果"""
        try:
            # govulncheck -json ./... 输出 JSON 格式
            result = subprocess.run(
                ["govulncheck", "-json", "./..."],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=300
            )

            # govulncheck 返回码：0=无漏洞，其他=有漏洞
            # 但即使有漏洞，JSON 输出仍然可用
            if not result.stdout:
                audit_logger.warning("govulncheck 无输出")
                return []

            # 解析 JSON（govulncheck 输出多行 JSON）
            return self._parse_govulncheck_output(result.stdout, repo_path)

        except subprocess.TimeoutExpired:
            audit_logger.error("govulncheck 超时")
            return []
        except Exception as e:
            audit_logger.error(f"govulncheck 执行失败: {e}")
            return []

    def _parse_govulncheck_output(self, output: str, repo_path: str) -> List[Issue]:
        """解析 govulncheck JSON 输出"""
        issues = []

        # govulncheck -json 输出多个 JSON 对象（可能是 pretty-printed）
        # 需要逐个解析 JSON 对象

        # 尝试逐个解析 JSON 对象
        decoder = json.JSONDecoder()
        idx = 0
        output_len = len(output)

        while idx < output_len:
            # 跳过空白
            while idx < output_len and output[idx] in ' \t\n\r':
                idx += 1

            if idx >= output_len:
                break

            # 尝试解析一个 JSON 对象
            try:
                data, end_idx = decoder.raw_decode(output, idx)
                idx = end_idx

                # 检查是否有漏洞信息（govulncheck 使用 'osv' 键）
                if "osv" in data:
                    vuln = data["osv"]
                    vuln_issues = self._parse_vulnerability(vuln, repo_path)
                    issues.extend(vuln_issues)
            except json.JSONDecodeError:
                # 跳过无法解析的部分
                idx += 1
                continue

        return issues

    def _parse_vulnerability(self, vuln: Dict[str, Any], repo_path: str) -> List[Issue]:
        """解析单个漏洞"""
        issues = []

        # govulncheck 漏洞格式
        vuln_id = vuln.get("id", "unknown")
        aliases = vuln.get("aliases", [])
        summary = vuln.get("summary", "Unknown vulnerability")
        details = vuln.get("details", "")
        affected = vuln.get("affected", [])

        # 获取严重级别
        severity = self._extract_severity(vuln)

        # 获取受影响的包
        for aff in affected:
            pkg_range = aff.get("ranges", [])
            pkg_info = aff.get("package", {})
            pkg_name = pkg_info.get("name", "unknown")

            # 构建消息
            message = f"{pkg_name}: {summary}"
            if aliases:
                message += f" ({', '.join(aliases)})"

            # 构建修复建议
            suggestion = self._build_fix_suggestion(pkg_name, pkg_range)

            # 查找受影响的具体文件
            files = self._find_affected_files(repo_path, pkg_name)

            if files:
                for file_path in files:
                    issues.append(Issue(
                        file=file_path,
                        line=1,
                        column=1,
                        severity=severity,
                        message=message,
                        rule=f"govulncheck/{vuln_id}",
                        tool=self.name,
                        dimension="dependency_security",
                        suggestion=suggestion,
                    ))
            else:
                # 如果找不到具体文件，指向 go.mod
                issues.append(Issue(
                    file=str(Path(repo_path) / "go.mod"),
                    line=1,
                    column=1,
                    severity=severity,
                    message=message,
                    rule=f"govulncheck/{vuln_id}",
                    tool=self.name,
                    dimension="dependency_security",
                    suggestion=suggestion,
                ))

        return issues

    def _extract_severity(self, vuln: Dict[str, Any]) -> Severity:
        """提取漏洞严重级别"""
        # govulncheck 可能包含 CVSS 评分或严重级别
        # 如果有 database_specific，尝试从中提取

        db_specific = vuln.get("database_specific", {})
        severity_str = db_specific.get("severity", "").upper()

        if severity_str:
            severity_map = {
                "CRITICAL": Severity.CRITICAL,
                "HIGH": Severity.HIGH,
                "MEDIUM": Severity.MEDIUM,
                "MODERATE": Severity.MEDIUM,
                "LOW": Severity.LOW,
                "INFO": Severity.INFO,
            }
            return severity_map.get(severity_str, Severity.MEDIUM)

        # 尝试从 CVSS 评分推断
        cvss = db_specific.get("cvss", 0)
        if cvss >= 9.0:
            return Severity.CRITICAL
        elif cvss >= 7.0:
            return Severity.HIGH
        elif cvss >= 4.0:
            return Severity.MEDIUM
        elif cvss > 0:
            return Severity.LOW

        # 默认 MEDIUM
        return Severity.MEDIUM

    def _build_fix_suggestion(self, pkg_name: str, pkg_ranges: List[Dict]) -> str:
        """构建修复建议"""
        # 查找修复版本
        for pkg_range in pkg_ranges:
            events = pkg_range.get("events", [])
            for event in events:
                if "fixed" in event:
                    fixed_version = event["fixed"]
                    return f"升级 {pkg_name} 到版本 {fixed_version} 或更高（go get {pkg_name}@{fixed_version}）"

        return f"检查 {pkg_name} 的最新版本并升级（go get -u {pkg_name}）"

    def _find_affected_files(self, repo_path: str, pkg_name: str) -> List[str]:
        """查找受影响的 Go 文件"""
        # 简单实现：查找 go.mod 中的引用
        # 实际应该分析 import 语句，但这里简化处理

        repo = Path(repo_path)
        files = []

        # 查找所有 .go 文件
        for go_file in repo.rglob("*.go"):
            try:
                content = go_file.read_text(encoding="utf-8", errors="ignore")
                # 检查是否导入了该包
                if f'"{pkg_name}"' in content or f'"{pkg_name}/' in content:
                    files.append(str(go_file))
            except Exception:
                continue

        return files if files else []
