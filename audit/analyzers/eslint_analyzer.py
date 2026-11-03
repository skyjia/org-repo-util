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

        # 检查并安装依赖（如果仓库有 package.json）
        self._ensure_dependencies()

        # 构建命令
        cmd = self._build_command(files)
        if not cmd:
            return self._create_empty_result()

        # 执行 ESLint
        try:
            # 设置环境变量，让 ESLint 能找到缓存的解析器/插件
            env = os.environ.copy()
            from audit.core.tool_installer import ToolInstaller
            installer = ToolInstaller()
            cache_node_modules = str(installer.cache_dir / "node_modules")
            if "NODE_PATH" in env:
                env["NODE_PATH"] = f"{cache_node_modules}{os.pathsep}{env['NODE_PATH']}"
            else:
                env["NODE_PATH"] = cache_node_modules

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=self.config.get("general.max_file_size", 600),
                env=env
            )

            # ESLint 返回码：0=无问题，1=有问题，2=配置错误
            if result.returncode == 2:
                logger.error(f"ESLint 配置错误: {result.stderr}")
                return self._create_empty_result()

            # 解析 JSON 输出
            issues = self._parse_output(result.stdout, files)

            # 过滤被忽略的问题
            issues = self.filter_ignored_issues(issues)

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
        has_config = self._has_repo_config()
        has_deps = self._has_node_modules()

        # 决定配置策略
        if has_config and has_deps:
            # 有配置有依赖：直接使用仓库配置
            logger.info("使用仓库自带的 ESLint 配置")
        elif has_config and not has_deps:
            # 有配置但无依赖：生成带解析器支持的回退配置
            logger.warning("找到 ESLint 配置但未安装依赖，生成带解析器支持的回退配置")
            fallback_config = self._generate_fallback_config(files)
            if fallback_config:
                # 必须同时使用 --no-eslintrc 来阻止加载仓库配置
                cmd.append("--no-eslintrc")
                cmd.extend(["--config", fallback_config])
            else:
                cmd.append("--no-eslintrc")
                cmd.extend(["--rule", '{"no-unused-vars": "warn", "no-undef": "error"}'])
        else:
            # 无配置：生成带解析器支持的最小化配置
            logger.info("未找到 ESLint 配置，生成带解析器支持的最小化配置")
            fallback_config = self._generate_fallback_config(files)
            if fallback_config:
                cmd.extend(["--config", fallback_config])
            else:
                cmd.append("--no-eslintrc")
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

    def _has_repo_config(self) -> bool:
        """检查仓库是否有 ESLint 配置文件"""
        config_names = [".eslintrc.js", ".eslintrc.json", ".eslintrc",
                        ".eslintrc.yaml", ".eslintrc.yml", ".eslintrc.cjs",
                        ".eslintrc.mjs"]
        for name in config_names:
            if (Path(self.repo_path) / name).exists():
                return True
        # 也检查 package.json 中的 eslintConfig 字段
        package_json = Path(self.repo_path) / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "eslintConfig" in data:
                        return True
            except Exception:
                pass
        return False

    def _has_node_modules(self) -> bool:
        """检查仓库是否有 node_modules"""
        return (Path(self.repo_path) / "node_modules").exists()

    def _ensure_dependencies(self):
        """确保项目依赖已安装（如果存在 package.json）"""
        from audit.core.audit_logger import get_audit_logger
        audit_logger = get_audit_logger()

        package_json = Path(self.repo_path) / "package.json"
        if not package_json.exists():
            return

        node_modules = Path(self.repo_path) / "node_modules"
        if node_modules.exists():
            logger.info("node_modules 已存在，跳过依赖安装")
            return

        # 尝试安装依赖
        logger.info("检测到 package.json 但未找到 node_modules，正在安装依赖...")
        audit_logger.info("开始安装项目依赖（npm install）...")

        try:
            result = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund", "--legacy-peer-deps"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("依赖安装成功")
                audit_logger.info("✅ 项目依赖安装成功")
            else:
                logger.warning(f"依赖安装失败: {result.stderr[:200]}")
                audit_logger.warning(f"⚠️ 项目依赖安装失败，将使用回退配置进行审计")
                audit_logger.warning(f"npm install 错误: {result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            logger.warning("依赖安装超时")
            audit_logger.warning("⚠️ 项目依赖安装超时（300秒），将使用回退配置进行审计")
        except Exception as e:
            logger.warning(f"依赖安装异常: {e}")
            audit_logger.warning(f"⚠️ 项目依赖安装异常: {e}，将使用回退配置进行审计")

    def _detect_file_types(self, files: List[Path]) -> dict:
        """检测文件类型"""
        types = {
            "has_vue": False,
            "has_jsx": False,
            "has_ts": False,
            "has_es6": False,
        }
        for f in files:
            ext = f.suffix.lower()
            if ext == ".vue":
                types["has_vue"] = True
            elif ext in (".jsx", ".tsx"):
                types["has_jsx"] = True
            elif ext in (".ts", ".tsx"):
                types["has_ts"] = True
            elif ext in (".js", ".mjs"):
                # 检查是否包含 ES6 语法
                try:
                    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read(2048)  # 只读前 2KB
                        if "import " in content or "export " in content or \
                           "const " in content or "let " in content or \
                           "=>" in content:
                            types["has_es6"] = True
                except Exception:
                    pass
        return types

    def _ensure_vue_parser(self) -> Optional[str]:
        """确保 vue-eslint-parser 可用，返回其路径"""
        from audit.core.tool_installer import ToolInstaller

        installer = ToolInstaller()
        cache_dir = installer.cache_dir

        # 检查是否已安装
        vue_parser_dir = cache_dir / "node_modules" / "vue-eslint-parser"
        if vue_parser_dir.exists():
            return str(vue_parser_dir)

        # 尝试安装
        logger.info("安装 vue-eslint-parser 以支持 Vue 文件解析...")
        npm_install_dir = cache_dir
        npm_install_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                ["npm", "install", "vue-eslint-parser@latest"],
                capture_output=True,
                text=True,
                cwd=str(npm_install_dir),
                timeout=120
            )
            if result.returncode == 0 and vue_parser_dir.exists():
                logger.info("vue-eslint-parser 安装成功")
                return str(vue_parser_dir)
            else:
                logger.warning(f"vue-eslint-parser 安装失败: {result.stderr}")
                return None
        except Exception as e:
            logger.warning(f"安装 vue-eslint-parser 失败: {e}")
            return None

    def _generate_fallback_config(self, files: List[Path]) -> Optional[str]:
        """生成带回退解析器支持的 ESLint 配置文件"""
        import tempfile

        # 检测文件类型
        file_types = self._detect_file_types(files)

        # 构建解析器配置
        parser_options = {
            "ecmaVersion": "latest",
            "sourceType": "module",
        }

        if file_types["has_jsx"]:
            parser_options["ecmaFeatures"] = {"jsx": True}

        # 构建基本配置
        config = {
            "parserOptions": parser_options,
            "env": {
                "browser": True,
                "es2022": True,
                "node": True,
            },
            "rules": {
                "no-unused-vars": "warn",
                "no-undef": "error",
                "no-console": "warn",
            }
        }

        # 处理 Vue 文件
        if file_types["has_vue"]:
            vue_parser_path = self._ensure_vue_parser()
            if vue_parser_path:
                config["overrides"] = [
                    {
                        "files": ["*.vue"],
                        "parser": "vue-eslint-parser",
                        "parserOptions": parser_options,
                    }
                ]
            else:
                logger.warning("无法安装 vue-eslint-parser，Vue 文件可能无法正确解析")

        # 处理 TypeScript 文件
        if file_types["has_ts"]:
            logger.warning("TypeScript 文件需要 @typescript-eslint/parser，回退配置可能不完整")

        # 写入临时配置文件
        try:
            from audit.core.tool_installer import ToolInstaller
            installer = ToolInstaller()
            tmp_dir = installer.cache_dir / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            config_path = tmp_dir / ".eslintrc-fallback.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            return str(config_path)
        except Exception as e:
            logger.error(f"生成回退配置文件失败: {e}")
            return None

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

        # 过滤掉文件忽略消息（不是真正的代码问题）
        if msg_text.startswith("File ignored"):
            logger.debug(f"跳过文件忽略消息: {file_path}")
            return None

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
