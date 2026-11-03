"""
ESLint 分析器 - 审计 JavaScript/TypeScript 代码
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


class ESLintAnalyzer(BaseAnalyzer):
    """ESLint 分析器"""

    @property
    def name(self) -> str:
        return "eslint"

    @property
    def language(self) -> str:
        return "javascript"

    @property
    def supported_extensions(self) -> List[str]:
        return [".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs"]

    def check_prerequisites(self) -> bool:
        """检查 ESLint 是否可用"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()

        # 检查仓库本地或全局工具
        if installer.is_installed("eslint", self.repo_path):
            return True

        logger.warning("ESLint 未安装，尝试自动安装...")
        return installer.install("eslint", repo_path=self.repo_path)

    def analyze(self) -> AnalysisResult:
        """执行 ESLint 分析"""
        import time
        start_time = time.time()

        # 收集文件
        files = self.collect_files()
        if not files:
            return self._create_empty_result()

        # 构建命令
        cmd = self._build_command(files)
        if not cmd:
            return self._create_empty_result()

        # 执行 ESLint
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=self.config.get("general.max_file_size", 600)
            )

            # ESLint 返回码：0=无问题，1=有问题，2=配置错误
            if result.returncode == 2:
                logger.error(f"ESLint 配置错误: {result.stderr}")
                return self._create_empty_result()

            # 解析 JSON 输出
            issues = self._parse_output(result.stdout, files)

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
            logger.error("ESLint 执行超时")
            return self._create_empty_result()
        except Exception as e:
            logger.error(f"ESLint 执行失败: {e}")
            return self._create_empty_result()

    def _build_command(self, files: List[Path]) -> Optional[List[str]]:
        """构建 ESLint 命令"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()
        tool_cmd = installer.get_tool_command("eslint", self.repo_path)

        if not tool_cmd:
            logger.error("无法获取 ESLint 命令")
            return None

        # 基本命令
        cmd = [tool_cmd]

        # 使用 JSON 格式输出
        cmd.extend(["--format", "json"])

        # 检查是否有仓库配置文件和 node_modules
        repo_config = Path(self.repo_path) / ".eslintrc.js"
        has_config = repo_config.exists()

        if not has_config:
            repo_config = Path(self.repo_path) / ".eslintrc.json"
            has_config = repo_config.exists()
        if not has_config:
            repo_config = Path(self.repo_path) / ".eslintrc"
            has_config = repo_config.exists()
        if not has_config:
            repo_config = Path(self.repo_path) / ".eslintrc.yaml"
            has_config = repo_config.exists()

        # 检查 node_modules 是否存在
        node_modules = Path(self.repo_path) / "node_modules"
        has_deps = node_modules.exists()

        # 如果有配置但没有依赖，使用 --no-eslintrc 避免插件缺失错误
        if has_config and not has_deps:
            logger.warning("找到 ESLint 配置但未安装依赖，使用最小化配置")
            cmd.append("--no-eslintrc")
            # 添加基本规则
            cmd.extend(["--rule", '{"no-unused-vars": "warn", "no-undef": "error"}'])

        # 添加文件路径（相对于仓库根目录）
        repo_root = Path(self.repo_path)
        for f in files:
            try:
                rel_path = f.relative_to(repo_root)
                cmd.append(str(rel_path))
            except ValueError:
                # 如果无法转换为相对路径，使用绝对路径
                cmd.append(str(f))

        return cmd

    def _parse_output(self, output: str, files: List[Path]) -> List[Issue]:
        """解析 ESLint JSON 输出"""
        issues = []

        try:
            results = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"解析 ESLint 输出失败: {e}")
            return issues

        for file_result in results:
            file_path = file_result.get("filePath", "")
            messages = file_result.get("messages", [])

            for msg in messages:
                issue = self._convert_to_issue(file_path, msg)
                if issue:
                    issues.append(issue)

        return issues

    def _convert_to_issue(self, file_path: str, message: dict) -> Optional[Issue]:
        """将 ESLint 消息转换为 Issue"""
        # 提取信息
        line = message.get("line", 1)
        column = message.get("column", 1)
        msg_text = message.get("message", "")
        rule_id = message.get("ruleId", "unknown")
        severity_num = message.get("severity", 1)

        # 映射严重级别
        # ESLint: 1=warning, 2=error
        if severity_num == 2:
            severity = Severity.HIGH
        else:
            severity = Severity.MEDIUM

        # 根据规则调整严重级别
        severity = self._map_severity(rule_id, severity)

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

    def _map_severity(self, rule_id: str, default: Severity) -> Severity:
        """根据规则映射严重级别"""
        # 安全性规则
        security_rules = [
            "no-eval", "no-implied-eval", "no-new-func",
            "no-dangerously-set-innerhtml", "no-script-url"
        ]
        if rule_id in security_rules:
            return Severity.CRITICAL

        # 错误类规则
        error_rules = [
            "no-unused-vars", "no-undef", "no-unreachable",
            "no-dupe-keys", "no-redeclare", "no-shadow"
        ]
        if rule_id in error_rules:
            return Severity.HIGH

        # 警告类规则
        warning_rules = [
            "no-console", "no-debugger", "no-alert",
            "eqeqeq", "no-var", "prefer-const"
        ]
        if rule_id in warning_rules:
            return Severity.MEDIUM

        return default

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
