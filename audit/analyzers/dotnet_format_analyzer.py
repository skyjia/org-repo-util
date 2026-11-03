"""
dotnet-format 分析器 - 审计 C# 代码
"""

import subprocess
import os
import re
from pathlib import Path
from typing import List, Optional
import logging

from audit.analyzers.base import BaseAnalyzer
from audit.core.models import Issue, AnalysisResult, Severity


logger = logging.getLogger(__name__)


class DotnetFormatAnalyzer(BaseAnalyzer):
    """dotnet-format 分析器"""

    @property
    def name(self) -> str:
        return "dotnet-format"

    @property
    def language(self) -> str:
        return "csharp"

    @property
    def supported_extensions(self) -> List[str]:
        return [".cs"]

    def check_prerequisites(self) -> bool:
        """检查 dotnet SDK 是否可用"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()

        if installer.is_installed("dotnet-format"):
            return True

        logger.warning("dotnet-format 未安装，尝试自动安装...")
        return installer.install("dotnet-format")

    def analyze(self) -> AnalysisResult:
        """执行 dotnet-format 分析"""
        import time
        start_time = time.time()

        # 收集文件
        files = self.collect_files()
        if not files:
            return self._create_empty_result()

        # 构建命令
        cmd = self._build_command()
        if not cmd:
            return self._create_empty_result()

        # 执行 dotnet format
        try:
            logger.info(f"执行命令: {' '.join(cmd)}")
            logger.info(f"工作目录: {self.repo_path}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=600
            )

            logger.info(f"返回码: {result.returncode}")
            logger.info(f"Stdout 长度: {len(result.stdout)}")
            logger.info(f"Stderr 长度: {len(result.stderr)}")

            if result.stdout:
                logger.debug(f"Stdout 前 500 字符: {result.stdout[:500]}")
            if result.stderr:
                logger.debug(f"Stderr 前 500 字符: {result.stderr[:500]}")

            # dotnet format 返回码：0=无问题，其他=有问题或错误
            # 解析输出
            issues = self._parse_output(result.stdout, result.stderr)

            duration = time.time() - start_time

            return AnalysisResult(
                repo=os.path.basename(self.repo_path),
                language=self.language,
                analyzer=self.name,
                issues=issues,
                files_scanned=len(files),
                lines_scanned=self._count_lines(files),
                duration_seconds=duration
            )

        except subprocess.TimeoutExpired:
            logger.error("dotnet format 执行超时")
            return self._create_empty_result()
        except Exception as e:
            logger.error(f"dotnet format 执行失败: {e}")
            return self._create_empty_result()

    def _build_command(self) -> Optional[List[str]]:
        """构建 dotnet format 命令"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()
        tool_cmd = installer.get_tool_command("dotnet-format")

        if not tool_cmd:
            logger.error("无法获取 dotnet format 命令")
            return None

        # 基本命令
        cmd = ["dotnet", "format"]

        # 查找解决方案文件或项目文件
        sln_file = self._find_solution_file()
        if sln_file:
            # 使用文件名（相对于仓库根目录）
            cmd.append(sln_file.name)
            logger.info(f"使用解决方案文件: {sln_file.name}")
        else:
            # 查找项目文件
            csproj = self._find_project_file()
            if csproj:
                # 使用相对路径
                try:
                    rel_path = csproj.relative_to(Path(self.repo_path))
                    cmd.append(str(rel_path))
                except ValueError:
                    cmd.append(str(csproj))
                logger.info(f"使用项目文件: {csproj}")
            else:
                logger.warning("未找到解决方案或项目文件，使用当前目录")

        # 使用 verify-no-changes 模式（只检查，不修改）
        cmd.append("--verify-no-changes")

        # 添加 verbosity
        cmd.extend(["--verbosity", "detailed"])

        return cmd

    def _find_solution_file(self) -> Optional[Path]:
        """查找解决方案文件"""
        repo = Path(self.repo_path)

        # 查找 .sln 文件
        sln_files = list(repo.glob("*.sln"))
        if sln_files:
            return sln_files[0]

        return None

    def _find_project_file(self) -> Optional[Path]:
        """查找项目文件"""
        repo = Path(self.repo_path)

        # 查找 .csproj 文件
        csproj_files = list(repo.glob("**/*.csproj"))
        if csproj_files:
            return csproj_files[0]

        return None

    def _parse_output(self, stdout: str, stderr: str) -> List[Issue]:
        """解析 dotnet format 输出"""
        issues = []

        # 合并输出
        output = stdout + "\n" + stderr

        # dotnet format 输出格式：
        # /path/to/file.cs(line,col): error WHITESPACE: Fix whitespace formatting.
        # 或
        # /path/to/file.cs(line,col): warning CS0168: The variable 'x' is declared but never used.

        # 正则表达式匹配
        pattern = r"^\s*([^\s(]+)\((\d+),(\d+)\):\s+(?:error|warning)\s+([A-Z0-9_]+):\s+(.+)$"

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                column = int(match.group(3))
                rule_id = match.group(4)
                message = match.group(5)

                # 相对路径转绝对路径
                if not os.path.isabs(file_path):
                    file_path = str(Path(self.repo_path) / file_path)

                issue = self._convert_to_issue(
                    file_path, line_num, column, rule_id, message
                )
                if issue:
                    issues.append(issue)

        return issues

    def _convert_to_issue(self, file_path: str, line: int, column: int,
                         rule_id: str, message: str) -> Optional[Issue]:
        """将 dotnet format 问题转换为 Issue"""
        # 映射严重级别
        severity = self._map_severity(rule_id)

        return Issue(
            file=file_path,
            line=line,
            column=column,
            severity=severity,
            message=message,
            rule=rule_id,
            tool=self.name,
            dimension="code_style"
        )

    def _map_severity(self, rule_id: str) -> Severity:
        """根据规则映射严重级别"""
        # 高严重级别（错误）
        if rule_id.startswith("CS") and rule_id[2:].isdigit():
            # C# 编译器错误
            error_codes = ["CS0103", "CS0246", "CS1061", "CS0117", "CS0122"]
            if rule_id in error_codes:
                return Severity.HIGH

        # 中严重级别（警告）
        return Severity.MEDIUM

    def _count_lines(self, files: List[Path]) -> int:
        """统计文件行数"""
        total = 0
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    total += sum(1 for _ in f)
            except Exception:
                pass
        return total

    def _create_empty_result(self) -> AnalysisResult:
        """创建空结果"""
        return AnalysisResult(
            repo=os.path.basename(self.repo_path),
            language=self.language,
            analyzer=self.name,
            issues=[],
            files_scanned=0,
            lines_scanned=0,
            duration_seconds=0.0
        )
