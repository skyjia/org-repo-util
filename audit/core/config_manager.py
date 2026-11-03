"""
配置管理器 - 加载和合并全局/仓库级配置
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """配置管理器"""

    def __init__(self, project_root: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            project_root: 项目根目录，默认为当前目录
        """
        self.project_root = Path(project_root or os.getcwd())
        self.global_config: Dict[str, Any] = {}
        self.repo_config: Dict[str, Any] = {}
        self.merged_config: Dict[str, Any] = {}

        # 加载配置
        self.load_global_config()

    def load_global_config(self) -> Dict[str, Any]:
        """
        加载全局配置

        Returns:
            全局配置字典
        """
        # 尝试多个可能的配置路径
        possible_paths = [
            self.project_root / "audit" / "config" / "global" / "rules.yaml",
            self.project_root / "config" / "global" / "rules.yaml",
            Path(__file__).parent.parent / "config" / "global" / "rules.yaml",
        ]

        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break

        if config_path and config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self.global_config = yaml.safe_load(f) or {}
        else:
            # 使用默认配置
            self.global_config = self._get_default_config()

        return self.global_config

    def load_repo_config(self, repo_path: str) -> Dict[str, Any]:
        """
        加载仓库级配置

        Args:
            repo_path: 仓库路径

        Returns:
            仓库级配置字典
        """
        repo_config_path = Path(repo_path) / ".audit-config.yaml"

        if repo_config_path.exists():
            with open(repo_config_path, "r", encoding="utf-8") as f:
                self.repo_config = yaml.safe_load(f) or {}
        else:
            self.repo_config = {}

        # 合并配置
        self.merge_config()

        return self.repo_config

    def merge_config(self) -> Dict[str, Any]:
        """
        合并全局配置和仓库级配置
        仓库级配置优先级更高

        Returns:
            合并后的配置字典
        """
        self.merged_config = self._deep_merge(self.global_config, self.repo_config)
        return self.merged_config

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        深度合并两个字典
        数组类型的配置采用追加方式

        Args:
            base: 基础字典
            override: 覆盖字典

        Returns:
            合并后的字典
        """
        result = base.copy()

        for key, value in override.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._deep_merge(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    # 数组追加
                    result[key] = result[key] + value
                else:
                    # 标量值覆盖
                    result[key] = value
            else:
                result[key] = value

        return result

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        验证配置是否符合 Schema

        Args:
            config: 配置字典

        Returns:
            配置是否有效
        """
        # TODO: 实现 Schema 验证
        # 目前只检查必要字段是否存在
        required_fields = ["version"]
        for field in required_fields:
            if field not in config:
                return False
        return True

    def get(self, key: str, default=None):
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键（如 "general.exclude_patterns"）
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self.merged_config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def _get_default_config(self) -> Dict[str, Any]:
        """
        获取默认配置

        Returns:
            默认配置字典
        """
        return {
            "version": "1.0",
            "general": {
                "severity_levels": ["critical", "high", "medium", "low", "info"],
                "exclude_patterns": [
                    "node_modules/",
                    "vendor/",
                    "dist/",
                    "build/",
                    ".git/",
                    "*.min.js",
                    "*.min.css"
                ],
                "dimensions": {
                    "code_style": True,
                    "security": True,
                    "reliability": False,
                    "performance": False
                },
                "max_file_size": 10 * 1024 * 1024,  # 10MB
                "language_threshold": 10.0  # 10%
            },
            "languages": {
                "javascript": {
                    "enabled": True,
                    "primary_tools": ["eslint"],
                    "file_patterns": ["*.js", "*.jsx", "*.ts", "*.tsx", "*.vue"]
                },
                "go": {
                    "enabled": True,
                    "primary_tools": ["golangci-lint"],
                    "file_patterns": ["*.go"]
                },
                "csharp": {
                    "enabled": True,
                    "primary_tools": ["dotnet-format"],
                    "file_patterns": ["*.cs"]
                }
            }
        }
