"""
工具安装器 - 管理分析工具的安装和版本控制

策略：
1. 优先使用仓库本地工具（repo-local）
2. 回退到全局管理工具（global-managed）
3. 支持每仓库版本覆盖
"""

import os
import subprocess
import json
import platform
from pathlib import Path
from typing import Optional, Dict, Tuple
import logging


logger = logging.getLogger(__name__)


class ToolInstaller:
    """工具安装器"""

    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化工具安装器

        Args:
            cache_dir: 工具缓存目录，默认为 audit/cache/tools
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.cache_dir = project_root / "audit" / "cache" / "tools"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 工具版本配置（全局默认）
        self.tool_versions = {
            "eslint": "8.56.0",
            "golangci-lint": "1.55.2",
            "dotnet-format": "latest",
        }

    def is_installed(self, tool_name: str, repo_path: Optional[str] = None) -> bool:
        """
        检查工具是否已安装

        Args:
            tool_name: 工具名称
            repo_path: 仓库路径（可选，用于检查本地工具）

        Returns:
            工具是否已安装
        """
        # 先检查仓库本地工具
        if repo_path:
            local_path = self._get_local_tool_path(tool_name, repo_path)
            if local_path and local_path.exists():
                return True

        # 再检查全局工具
        return self._is_globally_installed(tool_name)

    def _get_local_tool_path(self, tool_name: str, repo_path: str) -> Optional[Path]:
        """
        获取仓库本地工具路径

        Args:
            tool_name: 工具名称
            repo_path: 仓库路径

        Returns:
            本地工具路径，如果不存在则返回 None
        """
        repo = Path(repo_path)

        if tool_name == "eslint":
            # Node.js 项目：node_modules/.bin/eslint
            local_path = repo / "node_modules" / ".bin" / "eslint"
            if local_path.exists():
                return local_path

        elif tool_name == "golangci-lint":
            # Go 项目通常不使用本地工具
            return None

        elif tool_name == "dotnet-format":
            # .NET 项目可能使用 dotnet tool
            local_path = repo / ".dotnet" / "dotnet-format"
            if local_path.exists():
                return local_path

        return None

    def _is_globally_installed(self, tool_name: str) -> bool:
        """
        检查工具是否全局安装

        Args:
            tool_name: 工具名称

        Returns:
            工具是否全局安装
        """
        try:
            if tool_name == "eslint":
                result = subprocess.run(
                    ["eslint", "--version"],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0

            elif tool_name == "golangci-lint":
                result = subprocess.run(
                    ["golangci-lint", "--version"],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0

            elif tool_name == "dotnet-format":
                result = subprocess.run(
                    ["dotnet", "format", "--version"],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False

    def get_version(self, tool_name: str, repo_path: Optional[str] = None) -> Optional[str]:
        """
        获取工具版本

        Args:
            tool_name: 工具名称
            repo_path: 仓库路径（可选）

        Returns:
            工具版本号，如果未安装则返回 None
        """
        try:
            if tool_name == "eslint":
                # 优先使用本地版本
                if repo_path:
                    local_path = self._get_local_tool_path("eslint", repo_path)
                    if local_path:
                        result = subprocess.run(
                            [str(local_path), "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            # 输出格式：v4.19.1
                            return result.stdout.strip().lstrip("v")

                # 回退到全局版本
                result = subprocess.run(
                    ["eslint", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip().lstrip("v")

            elif tool_name == "golangci-lint":
                result = subprocess.run(
                    ["golangci-lint", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # 输出格式：golangci-lint has version 1.55.2 built with go1.21.5 from ...
                    parts = result.stdout.split()
                    for i, part in enumerate(parts):
                        if part == "version" and i + 1 < len(parts):
                            return parts[i + 1]

            elif tool_name == "dotnet-format":
                result = subprocess.run(
                    ["dotnet", "format", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip()

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"获取 {tool_name} 版本失败: {e}")

        return None

    def install(self, tool_name: str, version: Optional[str] = None,
                repo_path: Optional[str] = None) -> bool:
        """
        安装工具

        Args:
            tool_name: 工具名称
            version: 版本号（可选，默认使用配置版本）
            repo_path: 仓库路径（可选，用于安装本地工具）

        Returns:
            安装是否成功
        """
        # 如果仓库已有本地工具，跳过安装
        if repo_path and self._get_local_tool_path(tool_name, repo_path):
            logger.info(f"{tool_name} 已在仓库中本地安装，跳过全局安装")
            return True

        if version is None:
            version = self.tool_versions.get(tool_name)

        logger.info(f"安装 {tool_name} {version}...")

        try:
            if tool_name == "eslint":
                return self._install_eslint(version)
            elif tool_name == "golangci-lint":
                return self._install_golangci_lint(version)
            elif tool_name == "dotnet-format":
                return self._install_dotnet_format(version)
            else:
                logger.error(f"未知的工具: {tool_name}")
                return False

        except Exception as e:
            logger.error(f"安装 {tool_name} 失败: {e}")
            return False

    def _install_eslint(self, version: str) -> bool:
        """安装 ESLint"""
        try:
            # 全局安装 ESLint
            result = subprocess.run(
                ["npm", "install", "-g", f"eslint@{version}"],
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"安装 ESLint 失败: {e}")
            return False

    def _install_golangci_lint(self, version: str) -> bool:
        """安装 golangci-lint"""
        try:
            # 使用官方安装脚本
            system = platform.system().lower()
            arch = platform.machine().lower()

            # 映射架构名称
            arch_map = {"x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
            arch = arch_map.get(arch, arch)

            url = f"https://github.com/golangci/golangci-lint/releases/download/v{version}/golangci-lint-{version}-{system}-{arch}.tar.gz"

            # 下载到缓存目录
            tar_path = self.cache_dir / f"golangci-lint-{version}.tar.gz"
            bin_dir = self.cache_dir / "bin"
            bin_dir.mkdir(exist_ok=True)

            # 下载
            result = subprocess.run(
                ["curl", "-sSfL", "-o", str(tar_path), url],
                capture_output=True,
                timeout=120
            )
            if result.returncode != 0:
                return False

            # 解压
            result = subprocess.run(
                ["tar", "-xzf", str(tar_path), "-C", str(bin_dir),
                 "--strip-components=1", f"golangci-lint-{version}-{system}-{arch}/golangci-lint"],
                capture_output=True,
                timeout=30
            )
            if result.returncode != 0:
                return False

            # 添加到 PATH（通过符号链接到 /usr/local/bin，需要 sudo）
            # 或者用户手动添加 cache_dir/bin 到 PATH
            logger.info(f"golangci-lint 已安装到 {bin_dir}/golangci-lint")
            logger.info(f"请将 {bin_dir} 添加到 PATH，或使用完整路径")

            return True

        except Exception as e:
            logger.error(f"安装 golangci-lint 失败: {e}")
            return False

    def _install_dotnet_format(self, version: str) -> bool:
        """安装 dotnet-format"""
        try:
            # 全局安装 dotnet-format
            result = subprocess.run(
                ["dotnet", "tool", "install", "-g", "dotnet-format"],
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"安装 dotnet-format 失败: {e}")
            return False

    def get_tool_command(self, tool_name: str, repo_path: Optional[str] = None) -> Optional[str]:
        """
        获取工具执行命令

        Args:
            tool_name: 工具名称
            repo_path: 仓库路径（可选）

        Returns:
            工具执行命令，如果未安装则返回 None
        """
        # 优先使用本地工具
        if repo_path:
            local_path = self._get_local_tool_path(tool_name, repo_path)
            if local_path:
                return str(local_path)

        # 回退到全局工具
        if tool_name == "eslint":
            return "eslint"
        elif tool_name == "golangci-lint":
            # 检查缓存目录
            cached_bin = self.cache_dir / "bin" / "golangci-lint"
            if cached_bin.exists():
                return str(cached_bin)
            return "golangci-lint"
        elif tool_name == "dotnet-format":
            return "dotnet format"

        return None

    def list_installed(self) -> Dict[str, Tuple[bool, Optional[str]]]:
        """
        列出所有已安装的工具

        Returns:
            字典：{tool_name: (is_installed, version)}
        """
        result = {}
        for tool in ["eslint", "golangci-lint", "dotnet-format"]:
            is_installed = self._is_globally_installed(tool)
            version = self.get_version(tool) if is_installed else None
            result[tool] = (is_installed, version)
        return result
