"""
依赖扫描协调器

检测项目中的依赖文件，选择合适的扫描器执行扫描
"""

from pathlib import Path
from typing import List, Dict, Any
import logging

from audit.core.models import Issue
from audit.core.audit_logger import get_audit_logger
from audit.analyzers.dependency.npm_scanner import NpmAuditScanner
from audit.analyzers.dependency.go_scanner import GoVulnScanner
from audit.analyzers.dependency.dotnet_scanner import DotnetVulnScanner


logger = logging.getLogger(__name__)
audit_logger = get_audit_logger()


class DependencyScanner:
    """依赖扫描协调器"""

    def __init__(self):
        self.scanners = {
            "npm-audit": NpmAuditScanner(),
            "govulncheck": GoVulnScanner(),
            "dotnet-vuln": DotnetVulnScanner(),
        }

    def detect_dependency_files(self, repo_path: str) -> Dict[str, List[str]]:
        """
        检测项目中的依赖文件

        Returns:
            {"npm": ["package.json"], "go": ["go.mod"], "dotnet": ["*.csproj", "*.sln"]}
        """
        repo = Path(repo_path)
        detected = {
            "npm": [],
            "go": [],
            "dotnet": [],
        }

        # npm: package.json
        package_json = repo / "package.json"
        if package_json.exists():
            detected["npm"].append(str(package_json))

        # Go: go.mod
        go_mod = repo / "go.mod"
        if go_mod.exists():
            detected["go"].append(str(go_mod))

        # .NET: *.csproj, *.sln
        for pattern in ["*.csproj", "*.sln"]:
            for file in repo.rglob(pattern):
                detected["dotnet"].append(str(file))

        return detected

    def scan(self, repo_path: str, skip_install: bool = False) -> List[Issue]:
        """
        执行依赖漏洞扫描

        Args:
            repo_path: 仓库路径
            skip_install: 是否跳过依赖安装（npm install）

        Returns:
            Issue 列表
        """
        issues = []
        detected = self.detect_dependency_files(repo_path)

        logger.info(f"检测到依赖文件: {detected}")

        # npm 扫描
        if detected["npm"]:
            scanner = self.scanners["npm-audit"]
            if scanner.check_prerequisites():
                logger.info("执行 npm audit 扫描...")
                npm_issues = scanner.scan(repo_path)
                issues.extend(npm_issues)
                logger.info(f"npm audit 完成，发现 {len(npm_issues)} 个漏洞")
            else:
                audit_logger.warning("npm 不可用，跳过 npm 依赖扫描")

        # Go 扫描
        if detected["go"]:
            scanner = self.scanners["govulncheck"]
            if scanner.check_prerequisites():
                logger.info("执行 govulncheck 扫描...")
                go_issues = scanner.scan(repo_path)
                issues.extend(go_issues)
                logger.info(f"govulncheck 完成，发现 {len(go_issues)} 个漏洞")
            else:
                audit_logger.warning("govulncheck 不可用，跳过 Go 依赖扫描")

        # .NET 扫描
        if detected["dotnet"]:
            scanner = self.scanners["dotnet-vuln"]
            if scanner.check_prerequisites():
                logger.info("执行 dotnet list package 扫描...")
                dotnet_issues = scanner.scan(repo_path)
                issues.extend(dotnet_issues)
                logger.info(f"dotnet list package 完成，发现 {len(dotnet_issues)} 个漏洞")
            else:
                audit_logger.warning("dotnet 不可用，跳过 .NET 依赖扫描")

        return issues

    def get_scanner_status(self) -> Dict[str, bool]:
        """获取各扫描器的可用状态"""
        status = {}
        for name, scanner in self.scanners.items():
            try:
                status[name] = scanner.check_prerequisites()
            except Exception as e:
                audit_logger.error(f"检查 {name} 状态失败: {e}")
                status[name] = False
        return status
