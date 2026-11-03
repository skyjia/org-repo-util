"""
dotnet list package --vulnerable 依赖漏洞扫描器

扫描 .NET 项目的依赖漏洞
使用 dotnet list package --vulnerable --format json 获取漏洞信息
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


class DotnetVulnScanner:
    """dotnet list package 依赖漏洞扫描器"""

    @property
    def name(self) -> str:
        return "dotnet-vuln"

    @property
    def language(self) -> str:
        return "csharp"

    def is_applicable(self, repo_path: str) -> bool:
        """检查是否适用于该仓库（是否有 .csproj/.sln 文件）"""
        repo = Path(repo_path)
        # 查找 .csproj 或 .sln 文件
        csproj_files = list(repo.rglob("*.csproj"))
        sln_files = list(repo.rglob("*.sln"))
        return len(csproj_files) > 0 or len(sln_files) > 0

    def check_prerequisites(self) -> bool:
        """检查 dotnet 是否可用"""
        try:
            result = subprocess.run(
                ["dotnet", "--version"],
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
        if not self.is_applicable(repo_path):
            audit_logger.warning(f"未找到 .csproj 或 .sln 文件: {repo_path}")
            return []

        # 查找项目文件
        projects = self._find_project_files(repo_path)
        if not projects:
            audit_logger.warning(f"未找到可扫描的项目: {repo_path}")
            return []

        # 对每个项目执行 dotnet list package --vulnerable
        issues = []
        for project_file in projects:
            project_issues = self._scan_project(project_file)
            issues.extend(project_issues)

        return issues

    def _find_project_files(self, repo_path: str) -> List[str]:
        """查找 .csproj 和 .sln 文件"""
        repo = Path(repo_path)
        projects = []

        # 优先使用 .sln
        sln_files = list(repo.rglob("*.sln"))
        if sln_files:
            projects.extend([str(f) for f in sln_files])
        else:
            # 使用 .csproj
            csproj_files = list(repo.rglob("*.csproj"))
            projects.extend([str(f) for f in csproj_files])

        return projects

    def _scan_project(self, project_file: str) -> List[Issue]:
        """扫描单个项目"""
        issues = []

        try:
            # 使用绝对路径
            project_file_abs = str(Path(project_file).resolve())

            result = subprocess.run(
                ["dotnet", "list", project_file_abs, "package", "--vulnerable", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=300
            )

            if not result.stdout:
                audit_logger.warning(f"dotnet list package 无输出: {project_file}")
                return []

            # 解析 JSON
            try:
                vuln_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                audit_logger.error(f"JSON 解析失败: {e}\n输出: {result.stdout[:500]}")
                return []

            # 解析漏洞信息
            issues = self._parse_vulnerabilities(vuln_data, project_file)

        except subprocess.TimeoutExpired:
            audit_logger.error(f"dotnet list package 超时: {project_file}")
        except Exception as e:
            audit_logger.error(f"dotnet list package 执行失败: {e}")

        return issues

    def _parse_vulnerabilities(self, vuln_data: Dict[str, Any], project_file: str) -> List[Issue]:
        """解析 dotnet list package --vulnerable JSON 输出"""
        issues = []

        # dotnet list package --vulnerable --format json 格式:
        # {
        #   "projects": [
        #     {
        #       "path": "...",
        #       "frameworks": [
        #         {
        #           "framework": "net6.0",
        #           "topLevelPackages": [
        #             {
        #               "id": "PackageName",
        #               "requestedVersion": "1.0.0",
        #               "resolvedVersion": "1.0.0",
        #               "vulnerabilities": [...]
        #             }
        #           ],
        #           "transitivePackages": [...]
        #         }
        #       ]
        #     }
        #   ]
        # }

        projects = vuln_data.get("projects", [])

        for project in projects:
            project_path = project.get("path", "")
            frameworks = project.get("frameworks", [])

            for framework_info in frameworks:
                framework = framework_info.get("framework", "")

                # 检查顶级包
                top_level = framework_info.get("topLevelPackages", [])
                for pkg in top_level:
                    pkg_issues = self._parse_package_vulnerability(pkg, project_path, is_transitive=False)
                    issues.extend(pkg_issues)

                # 检查传递依赖
                transitive = framework_info.get("transitivePackages", [])
                for pkg in transitive:
                    pkg_issues = self._parse_package_vulnerability(pkg, project_path, is_transitive=True)
                    issues.extend(pkg_issues)

        return issues

    def _parse_package_vulnerability(self, pkg: Dict[str, Any], project_file: str, is_transitive: bool) -> List[Issue]:
        """解析单个包的漏洞信息"""
        issues = []

        pkg_name = pkg.get("id", "unknown")
        requested_version = pkg.get("requestedVersion", "")
        resolved_version = pkg.get("resolvedVersion", "")
        vulnerabilities = pkg.get("vulnerabilities", [])

        if not vulnerabilities:
            return []

        for vuln in vulnerabilities:
            severity_str = vuln.get("severity", "Moderate")
            severity = self._map_severity(severity_str)
            advisory_url = vuln.get("advisoryurl", "")

            # 构建消息
            dep_type = "（传递依赖）" if is_transitive else "（直接依赖）"
            message = f"{pkg_name}@{resolved_version} 存在漏洞 {dep_type}"
            if advisory_url:
                message += f"（参考: {advisory_url}）"

            # 构建修复建议
            suggestion = f"升级 {pkg_name} 到安全版本"
            if requested_version:
                suggestion += f"（当前请求版本: {requested_version}，已解析: {resolved_version}）"

            issues.append(Issue(
                file=project_file,
                line=1,
                column=1,
                severity=severity,
                message=message,
                rule=f"dotnet-vuln/{pkg_name}",
                tool=self.name,
                dimension="dependency_security",
                suggestion=suggestion,
            ))

        return issues

    def _map_severity(self, dotnet_severity: str) -> Severity:
        """映射 dotnet 严重级别到统一格式"""
        severity_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
            "info": Severity.INFO,
        }
        return severity_map.get(dotnet_severity.lower(), Severity.MEDIUM)
