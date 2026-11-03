"""
golangci-lint 分析器 - 审计 Go 代码
"""

import json
import subprocess
import os
from pathlib import Path
from typing import List, Optional
import logging

from audit.analyzers.base import BaseAnalyzer
from audit.core.models import Issue, AnalysisResult, Severity


logger = logging.getLogger(__name__)


class GolangciLintAnalyzer(BaseAnalyzer):
    """golangci-lint 分析器"""

    @property
    def name(self) -> str:
        return "golangci-lint"

    @property
    def language(self) -> str:
        return "go"

    @property
    def supported_extensions(self) -> List[str]:
        return [".go"]

    def check_prerequisites(self) -> bool:
        """检查 golangci-lint 是否可用"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()

        if installer.is_installed("golangci-lint"):
            return True

        logger.warning("golangci-lint 未安装，尝试自动安装...")
        return installer.install("golangci-lint")

    def analyze(self) -> AnalysisResult:
        """执行 golangci-lint 分析"""
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

        # 执行 golangci-lint
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=600
            )

            # golangci-lint 返回码：0=无问题，其他=有问题或错误
            # 解析 JSON 输出
            issues = self._parse_output(result.stdout)

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
            logger.error("golangci-lint 执行超时")
            return self._create_empty_result()
        except Exception as e:
            logger.error(f"golangci-lint 执行失败: {e}")
            return self._create_empty_result()

    def _build_command(self) -> Optional[List[str]]:
        """构建 golangci-lint 命令"""
        from audit.core.tool_installer import ToolInstaller
        from audit.analyzers.golangci_config_fixer import GolangciConfigFixer

        installer = ToolInstaller()
        tool_cmd = installer.get_tool_command("golangci-lint")

        if not tool_cmd:
            logger.error("无法获取 golangci-lint 命令")
            return None

        # 基本命令
        cmd = [tool_cmd, "run"]

        # 检测 golangci-lint 版本
        version = self._get_golangci_version(tool_cmd)

        # 根据版本使用不同的输出格式参数
        if version and version.startswith("2"):
            # v2 使用 --output.json.path，需要禁用 text 输出
            cmd.extend(["--output.text.path", "", "--output.json.path", "stdout"])
        else:
            # v1 使用 --out-format
            cmd.extend(["--out-format", "json"])

        # 检查是否有配置文件
        repo_config = Path(self.repo_path) / ".golangci.yml"
        if not repo_config.exists():
            repo_config = Path(self.repo_path) / ".golangci.yaml"

        if repo_config.exists():
            # 对于 v2，直接使用原配置（不需要降级）
            if version and version.startswith("2"):
                logger.info(f"使用配置文件: {repo_config} (golangci-lint v{version})")
            else:
                # v1 需要检查是否需要修复
                fixer = GolangciConfigFixer()
                if fixer.needs_fixing(repo_config):
                    logger.info(f"检测到配置文件问题，自动修复: {repo_config}")
                    fixed_path, fixes = fixer.fix_config(repo_config)
                    if fixed_path != repo_config:
                        # 使用修复后的配置文件
                        cmd.extend(["--config", str(fixed_path)])
                        logger.info(f"使用修复后的配置: {fixed_path}")
                    else:
                        logger.info(f"使用配置文件: {repo_config}")
                else:
                    logger.info(f"使用配置文件: {repo_config}")
        else:
            logger.warning("未找到 golangci-lint 配置文件，使用默认配置")

        # 添加超时设置
        cmd.extend(["--timeout", "5m"])

        return cmd

    def _get_golangci_version(self, tool_cmd: str) -> Optional[str]:
        """获取 golangci-lint 版本"""
        import subprocess
        try:
            result = subprocess.run(
                [tool_cmd, "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 输出格式：golangci-lint has version 2.15.0 built with ...
                # 或：golangci-lint has version 1.64.8 built with ...
                parts = result.stdout.split()
                for i, part in enumerate(parts):
                    if part == "version" and i + 1 < len(parts):
                        return parts[i + 1]
        except Exception as e:
            logger.debug(f"获取 golangci-lint 版本失败: {e}")
        return None

    def _parse_output(self, output: str) -> List[Issue]:
        """解析 golangci-lint JSON 输出"""
        issues = []

        # golangci-lint v2 可能在 JSON 后附加摘要文本
        # 使用 json.JSONDecoder 来找到完整的 JSON 对象
        
        # 找到第一个 { 的位置
        json_start = output.find('{')
        if json_start == -1:
            logger.error("未找到 JSON 输出")
            return issues

        # 使用 JSONDecoder 解析，它会返回解析到的位置
        decoder = json.JSONDecoder()
        try:
            data, end_pos = decoder.raw_decode(output, json_start)
        except json.JSONDecodeError as e:
            logger.error(f"解析 golangci-lint 输出失败: {e}")
            logger.debug(f"输出前 500 字符: {output[:500]}")
            return issues

        # golangci-lint JSON 格式
        issues_data = data.get("Issues", [])

        for issue_data in issues_data:
            issue = self._convert_to_issue(issue_data)
            if issue:
                issues.append(issue)

        return issues

    def _convert_to_issue(self, issue_data: dict) -> Optional[Issue]:
        """将 golangci-lint 问题转换为 Issue"""
        # 提取信息
        file_path = issue_data.get("Pos", {}).get("Filename", "")
        line = issue_data.get("Pos", {}).get("Line", 1)
        column = issue_data.get("Pos", {}).get("Column", 1)
        msg_text = issue_data.get("Text", "")
        rule_id = issue_data.get("FromLinter", "unknown")

        # 相对路径转绝对路径
        if file_path and not os.path.isabs(file_path):
            file_path = str(Path(self.repo_path) / file_path)

        # 映射严重级别
        severity = self._map_severity(rule_id)

        return Issue(
            file=file_path,
            line=line,
            column=column,
            severity=severity,
            message=msg_text,
            rule=rule_id,
            tool=self.name,
            dimension="code_style"
        )

    def _map_severity(self, rule_id: str) -> Severity:
        """根据 linter 映射严重级别"""
        # 高严重级别
        high_linters = ["govet", "staticcheck", "errcheck"]
        if rule_id in high_linters:
            return Severity.HIGH

        # 中严重级别
        medium_linters = ["gosimple", "ineffassign", "unused"]
        if rule_id in medium_linters:
            return Severity.MEDIUM

        # 安全性检查
        if rule_id == "gosec":
            return Severity.HIGH

        # 默认中等
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
