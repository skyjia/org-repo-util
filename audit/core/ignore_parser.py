"""
忽略注释解析器 - 解析源代码中的 @audit-ignore 注释

支持的语言和注释风格：
- JavaScript/TypeScript: // @audit-ignore 或 /* @audit-ignore */
- Go: // @audit-ignore
- C#: // @audit-ignore
- Python: # @audit-ignore
- YAML: # @audit-ignore
"""

import re
from pathlib import Path
from typing import Set, Dict, Optional, Tuple
import logging


logger = logging.getLogger(__name__)


# 每种语言的注释模式
# 匹配单行注释中的 @audit-ignore
COMMENT_PATTERNS = {
    "javascript": [
        # // @audit-ignore
        re.compile(r"^\s*//.*@audit-ignore", re.MULTILINE),
        # /* @audit-ignore */
        re.compile(r"/\*.*?@audit-ignore.*?\*/", re.DOTALL),
    ],
    "typescript": [
        re.compile(r"^\s*//.*@audit-ignore", re.MULTILINE),
        re.compile(r"/\*.*?@audit-ignore.*?\*/", re.DOTALL),
    ],
    "go": [
        re.compile(r"^\s*//.*@audit-ignore", re.MULTILINE),
    ],
    "csharp": [
        re.compile(r"^\s*//.*@audit-ignore", re.MULTILINE),
        re.compile(r"/\*.*?@audit-ignore.*?\*/", re.DOTALL),
    ],
    "python": [
        re.compile(r"^\s*#.*@audit-ignore", re.MULTILINE),
    ],
    "yaml": [
        re.compile(r"^\s*#.*@audit-ignore", re.MULTILINE),
    ],
}

# 默认模式（如果语言不在上面的列表中）
DEFAULT_PATTERNS = [
    re.compile(r"@audit-ignore", re.MULTILINE),
]


class IgnoreCommentParser:
    """忽略注释解析器"""

    def __init__(self):
        self._cache: Dict[str, Set[int]] = {}

    def parse_file(self, file_path: str, language: str) -> Set[int]:
        """
        解析文件中的 @audit-ignore 注释，返回被忽略的行号集合

        Args:
            file_path: 文件路径
            language: 语言标识

        Returns:
            被忽略的行号集合（1-indexed）
        """
        # 检查缓存
        cache_key = f"{file_path}:{language}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        ignored_lines: Set[int] = set()

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            logger.debug(f"无法读取文件 {file_path}: {e}")
            return ignored_lines

        # 获取语言的注释模式
        patterns = COMMENT_PATTERNS.get(language.lower(), DEFAULT_PATTERNS)

        # 逐行检查
        for line_num, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern.search(line):
                    # 如果注释在当前行，忽略当前行
                    ignored_lines.add(line_num)
                    # 如果注释在上一行（如 /* ... */），忽略下一行
                    if line_num + 1 <= len(lines):
                        ignored_lines.add(line_num + 1)
                    break

        # 缓存结果
        self._cache[cache_key] = ignored_lines
        return ignored_lines

    def is_line_ignored(self, file_path: str, line: int, language: str) -> bool:
        """
        检查特定行是否被 @audit-ignore 注释忽略

        Args:
            file_path: 文件路径
            line: 行号（1-indexed）
            language: 语言标识

        Returns:
            是否被忽略
        """
        ignored_lines = self.parse_file(file_path, language)
        return line in ignored_lines

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()


# 全局实例
_parser: Optional[IgnoreCommentParser] = None


def get_parser() -> IgnoreCommentParser:
    """获取全局解析器实例"""
    global _parser
    if _parser is None:
        _parser = IgnoreCommentParser()
    return _parser


def is_line_ignored(file_path: str, line: int, language: str) -> bool:
    """
    检查特定行是否被 @audit-ignore 注释忽略

    便捷函数，使用全局解析器实例

    Args:
        file_path: 文件路径
        line: 行号（1-indexed）
        language: 语言标识

    Returns:
        是否被忽略
    """
    return get_parser().is_line_ignored(file_path, line, language)
