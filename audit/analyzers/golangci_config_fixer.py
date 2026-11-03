"""
golangci-lint 配置修复器

自动检测和修复常见的配置问题：
1. enable/disable 列表冲突（enable 优先）
2. 版本格式降级（v2 → v1）
3. v2 专有结构的兼容处理
"""

import yaml
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import logging


logger = logging.getLogger(__name__)


class GolangciConfigFixer:
    """golangci-lint 配置修复器"""

    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化配置修复器

        Args:
            cache_dir: 缓存目录，默认为 audit/cache/tmp
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.cache_dir = project_root / "audit" / "cache" / "tmp"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fixes_applied: List[str] = []

    def needs_fixing(self, config_path: Path) -> bool:
        """
        检查配置文件是否需要修复

        Args:
            config_path: 配置文件路径

        Returns:
            是否需要修复
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not config:
                return False

            # 检查版本格式
            version = config.get('version', '1')
            if str(version) == '2':
                return True

            # 检查 enable/disable 冲突
            linters = config.get('linters', {})
            enable_set = set(linters.get('enable', []))
            disable_set = set(linters.get('disable', []))

            if enable_set & disable_set:
                return True

            return False

        except Exception as e:
            logger.warning(f"检查配置文件失败: {e}")
            return False

    def fix_config(self, config_path: Path) -> Tuple[Path, List[str]]:
        """
        修复配置文件

        Args:
            config_path: 原配置文件路径

        Returns:
            (修复后的配置文件路径, 修复内容列表)
        """
        self.fixes_applied = []

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            return config_path, []

        # 修复版本格式（v2 → v1）
        version = config.get('version', '1')
        if str(version) == '2':
            self._downgrade_v2_to_v1(config)
            self.fixes_applied.append("配置版本从 v2 降级到 v1")

        # 修复 enable/disable 冲突（enable 优先）
        linters = config.get('linters', {})
        enable_set = set(linters.get('enable', []))
        disable_set = set(linters.get('disable', []))

        conflicts = enable_set & disable_set
        if conflicts:
            # 从 disable 列表中移除冲突项
            linters['disable'] = [x for x in linters.get('disable', []) if x not in enable_set]
            self.fixes_applied.append(f"移除 disable 列表中的冲突项: {', '.join(sorted(conflicts))}")

        # 生成修复后的配置文件
        fixed_path = self._write_fixed_config(config, config_path)

        logger.info(f"配置已自动修复: {fixed_path}")
        for fix in self.fixes_applied:
            logger.info(f"  - {fix}")

        return fixed_path, self.fixes_applied

    def _downgrade_v2_to_v1(self, config: Dict[str, Any]):
        """
        将 v2 格式降级到 v1 格式

        Args:
            config: 配置字典（会被修改）
        """
        # 移除 version 字段（v1 不需要）
        if 'version' in config:
            del config['version']

        # v2 的 formatters 部分在 v1 中不存在，移除
        if 'formatters' in config:
            del config['formatters']
            self.fixes_applied.append("移除 v2 专有的 formatters 部分")

        # v2 的 output.formats 结构在 v1 中不同
        output = config.get('output', {})
        if 'formats' in output:
            # v1 使用 output.format 而不是 output.formats
            formats = output.pop('formats', {})
            if 'text' in formats:
                text_config = formats['text']
                # v1 的 output 结构
                output['format'] = 'colored-line-number'  # 默认格式
                if text_config.get('print-linter-name'):
                    output['print-linter-name'] = True
                if text_config.get('print-issued-lines'):
                    output['print-issued-lines'] = True
            self.fixes_applied.append("转换 output.formats 到 v1 格式")

        # v2 的 linters.settings 结构可能与 v1 不同，但大部分兼容
        # 暂时不做深度转换

    def _write_fixed_config(self, config: Dict[str, Any], original_path: Path) -> Path:
        """
        将修复后的配置写入临时文件

        Args:
            config: 修复后的配置字典
            original_path: 原配置文件路径

        Returns:
            修复后的配置文件路径
        """
        # 基于原文件内容生成哈希，作为临时文件名
        config_content = yaml.dump(config, default_flow_style=False, allow_unicode=True)
        config_hash = hashlib.md5(config_content.encode()).hexdigest()[:12]

        fixed_filename = f".golangci.fixed.{config_hash}.yml"
        fixed_path = self.cache_dir / fixed_filename

        # 如果文件已存在且内容相同，直接返回
        if fixed_path.exists():
            existing_content = fixed_path.read_text()
            if existing_content == config_content:
                return fixed_path

        # 写入新文件
        with open(fixed_path, 'w', encoding='utf-8') as f:
            f.write(config_content)

        return fixed_path

    def cleanup(self):
        """清理临时文件"""
        try:
            if self.cache_dir.exists():
                for f in self.cache_dir.glob(".golangci.fixed.*.yml"):
                    f.unlink()
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
