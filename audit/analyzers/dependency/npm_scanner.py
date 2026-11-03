"""
npm audit 依赖漏洞扫描器

扫描 JavaScript/TypeScript 项目的依赖漏洞
使用 npm audit --json 获取漏洞信息
"""

import json
import subprocess
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from audit.core.models import Issue, Severity
from audit.core.audit_logger import get_audit_logger


logger = logging.getLogger(__name__)
audit_logger = get_audit_logger()


class NpmAuditScanner:
    """npm audit 依赖漏洞扫描器"""

    @property
    def name(self) -> str:
        return "npm-audit"

    @property
    def language(self) -> str:
        return "javascript"

    def is_applicable(self, repo_path: str) -> bool:
        """检查是否适用于该仓库"""
        repo = Path(repo_path)
        return (repo / "package.json").exists()

    def check_prerequisites(self) -> bool:
        """检查 npm 是否可用"""
        try:
            result = subprocess.run(
                ["npm", "--version"],
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
        package_json = repo / "package.json"

        if not package_json.exists():
            audit_logger.warning(f"未找到 package.json: {repo_path}")
            return []

        # 检查 node_modules 是否存在
        node_modules = repo / "node_modules"
        if not node_modules.exists():
            audit_logger.warning(f"未找到 node_modules，尝试安装依赖: {repo_path}")
            if not self._install_dependencies(repo_path):
                audit_logger.warning("依赖安装失败，跳过依赖扫描")
                return []

        # 执行 npm audit
        issues = self._run_npm_audit(repo_path)
        return issues

    def _install_dependencies(self, repo_path: str) -> bool:
        """安装依赖"""
        try:
            # 使用 --legacy-peer-deps 处理依赖冲突
            result = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund", "--legacy-peer-deps"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=300
            )
            return result.returncode == 0
        except Exception as e:
            audit_logger.error(f"npm install 失败: {e}")
            return False

    def _run_npm_audit(self, repo_path: str) -> List[Issue]:
        """执行 npm audit 并解析结果"""
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=120
            )

            # npm audit 返回码：0=无漏洞，其他=有漏洞
            # 但即使有漏洞，JSON 输出仍然可用
            if not result.stdout:
                audit_logger.warning("npm audit 无输出")
                return []

            # 解析 JSON
            try:
                audit_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                audit_logger.error(f"npm audit JSON 解析失败: {e}")
                return []

            return self._parse_audit_result(audit_data, repo_path)

        except subprocess.TimeoutExpired:
            audit_logger.error("npm audit 超时")
            return []
        except Exception as e:
            audit_logger.error(f"npm audit 执行失败: {e}")
            return []

    def _parse_audit_result(self, audit_data: Dict[str, Any], repo_path: str) -> List[Issue]:
        """解析 npm audit 结果"""
        issues = []

        # npm audit 输出格式（npm v6/v7+ 不同）
        # v6: {"advisories": {...}, "metadata": {...}}
        # v7+: {"vulnerabilities": {...}, "metadata": {...}}

        # 尝试 v7+ 格式
        vulnerabilities = audit_data.get("vulnerabilities", {})
        if vulnerabilities:
            for pkg_name, vuln_info in vulnerabilities.items():
                pkg_issues = self._parse_vulnerability_v7(pkg_name, vuln_info, repo_path)
                issues.extend(pkg_issues)
            return issues

        # 尝试 v6 格式
        advisories = audit_data.get("advisories", {})
        if advisories:
            for adv_id, advisory in advisories.items():
                adv_issues = self._parse_advisory_v6(adv_id, advisory, repo_path)
                issues.extend(adv_issues)
            return issues

        return issues

    def _parse_vulnerability_v7(self, pkg_name: str, vuln_info: Dict, repo_path: str) -> List[Issue]:
        """解析 npm v7+ 格式的漏洞"""
        issues = []

        # vuln_info 可能包含多个 via 来源
        severity_str = vuln_info.get("severity", "info")
        severity = self._map_severity(severity_str)

        # 获取漏洞详情
        via = vuln_info.get("via", [])
        range_str = vuln_info.get("range", "")
        fix_available = vuln_info.get("fixAvailable", False)

        # 构建消息
        if isinstance(via, list) and via:
            # via 可能是字符串列表或对象列表
            if isinstance(via[0], dict):
                # 有详细漏洞信息
                for vuln_detail in via:
                    if isinstance(vuln_detail, dict) and "title" in vuln_detail:
                        cve = vuln_detail.get("cve_ids", [])
                        cve_str = ", ".join(cve) if cve else "N/A"
                        url = vuln_detail.get("url", "")

                        message = f"{vuln_detail.get('title', 'Unknown vulnerability')}"
                        if cve_str != "N/A":
                            message += f" ({cve_str})"

                        suggestion = f"升级 {pkg_name} 到安全版本"
                        if fix_available:
                            if isinstance(fix_available, dict):
                                suggestion += f"（{fix_available.get('name', pkg_name)}@{fix_available.get('version', 'latest')}）"
                            else:
                                suggestion += "（运行 npm audit fix）"

                        issues.append(Issue(
                            file=str(Path(repo_path) / "package.json"),
                            line=1,
                            column=1,
                            severity=severity,
                            message=message,
                            rule=f"npm-audit/{pkg_name}",
                            tool=self.name,
                            dimension="dependency_security",
                            suggestion=suggestion,
                        ))
            else:
                # via 是字符串列表（依赖链）
                message = f"{pkg_name} 存在 {severity_str} 级别漏洞"
                if range_str:
                    message += f"（受影响版本: {range_str}）"

                suggestion = f"升级 {pkg_name} 到安全版本"
                if fix_available:
                    suggestion += "（运行 npm audit fix）"

                issues.append(Issue(
                    file=str(Path(repo_path) / "package.json"),
                    line=1,
                    column=1,
                    severity=severity,
                    message=message,
                    rule=f"npm-audit/{pkg_name}",
                    tool=self.name,
                    dimension="dependency_security",
                    suggestion=suggestion,
                ))
        else:
            # 简单格式
            message = f"{pkg_name} 存在 {severity_str} 级别漏洞"
            if range_str:
                message += f"（受影响版本: {range_str}）"

            suggestion = f"升级 {pkg_name} 到安全版本"
            if fix_available:
                suggestion += "（运行 npm audit fix）"

            issues.append(Issue(
                file=str(Path(repo_path) / "package.json"),
                line=1,
                column=1,
                severity=severity,
                message=message,
                rule=f"npm-audit/{pkg_name}",
                tool=self.name,
                dimension="dependency_security",
                suggestion=suggestion,
            ))

        return issues

    def _parse_advisory_v6(self, adv_id: str, advisory: Dict, repo_path: str) -> List[Issue]:
        """解析 npm v6 格式的漏洞"""
        issues = []

        module_name = advisory.get("module_name", "unknown")
        severity_str = advisory.get("severity", "info")
        severity = self._map_severity(severity_str)
        title = advisory.get("title", "Unknown vulnerability")
        overview = advisory.get("overview", "")
        recommendation = advisory.get("recommendation", "")
        cves = advisory.get("cves", [])
        url = advisory.get("url", "")

        message = f"{module_name}: {title}"
        if cves:
            message += f" ({', '.join(cves)})"

        suggestion = recommendation or f"升级 {module_name} 到安全版本"

        issues.append(Issue(
            file=str(Path(repo_path) / "package.json"),
            line=1,
            column=1,
            severity=severity,
            message=message,
            rule=f"npm-audit/{module_name}",
            tool=self.name,
            dimension="dependency_security",
            suggestion=suggestion,
        ))

        return issues

    def _map_severity(self, npm_severity: str) -> Severity:
        """映射 npm 严重级别到统一格式"""
        severity_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
            "info": Severity.INFO,
        }
        return severity_map.get(npm_severity.lower(), Severity.MEDIUM)
