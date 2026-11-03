"""
文件收集器 - 根据配置收集待审计文件
"""

import os
import fnmatch
from typing import List, Dict, Any, Optional
from pathlib import Path


class FileCollector:
    """文件收集器"""

    # 语言到文件扩展名的映射
    EXTENSION_MAP = {
        'javascript': ['.js', '.jsx', '.mjs'],
        'typescript': ['.ts', '.tsx'],
        'vue': ['.vue'],
        'go': ['.go'],
        'c#': ['.cs'],
        'csharp': ['.cs'],
    }

    def __init__(self, config: Dict[str, Any]):
        """
        初始化文件收集器

        Args:
            config: 配置字典
        """
        self.config = config
        self.exclude_patterns = config.get('general', {}).get('exclude_patterns', [
            'node_modules/',
            'vendor/',
            'dist/',
            'build/',
            '.git/',
            '*.min.js',
            '*.min.css'
        ])
        self.max_file_size = config.get('general', {}).get('max_file_size', 10 * 1024 * 1024)

    def collect(self, repo_path: str, language: Optional[str] = None,
                extensions: Optional[List[str]] = None) -> List[Path]:
        """
        收集待审计文件

        Args:
            repo_path: 仓库路径
            language: 语言名称（可选）
            extensions: 文件扩展名列表（可选，优先于 language）

        Returns:
            文件路径列表
        """
        # 确定要收集的扩展名
        if extensions:
            target_extensions = extensions
        elif language:
            target_extensions = self.EXTENSION_MAP.get(language.lower(), [])
        else:
            # 收集所有支持的文件
            target_extensions = []
            for exts in self.EXTENSION_MAP.values():
                target_extensions.extend(exts)

        if not target_extensions:
            return []

        # 收集文件
        files = []
        repo = Path(repo_path)

        for root, dirs, filenames in os.walk(repo):
            # 过滤目录
            dirs[:] = [d for d in dirs if not self.should_exclude(os.path.join(root, d))]

            for filename in filenames:
                file_path = Path(root) / filename

                # 检查扩展名
                if not any(filename.endswith(ext) for ext in target_extensions):
                    continue

                # 检查排除规则
                if self.should_exclude(str(file_path)):
                    continue

                # 检查文件大小
                try:
                    if file_path.stat().st_size > self.max_file_size:
                        continue
                except OSError:
                    continue

                # 检查是否为二进制文件
                if self.is_binary(file_path):
                    continue

                files.append(file_path)

        return files

    def should_exclude(self, file_path: str) -> bool:
        """
        判断文件是否应被排除

        Args:
            file_path: 文件路径

        Returns:
            是否应排除
        """
        for pattern in self.exclude_patterns:
            # 支持目录模式（如 node_modules/）
            if pattern.endswith('/'):
                if pattern in file_path or f"/{pattern}" in file_path:
                    return True
            # 支持通配符模式（如 *.min.js）
            elif fnmatch.fnmatch(file_path, f"*{pattern}*"):
                return True
            elif fnmatch.fnmatch(os.path.basename(file_path), pattern):
                return True

        return False

    def is_binary(self, file_path: str) -> bool:
        """
        判断是否为二进制文件

        Args:
            file_path: 文件路径

        Returns:
            是否为二进制
        """
        try:
            # 读取前 1024 字节
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)

            # 如果包含空字节，认为是二进制
            if b'\x00' in chunk:
                return True

            # 检查是否有太多非文本字符
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
            non_text = sum(1 for byte in chunk if byte not in text_chars)

            return non_text / len(chunk) > 0.3

        except Exception:
            return False
