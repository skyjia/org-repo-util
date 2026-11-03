"""
语言检测器 - 检测仓库主要编程语言
"""

import os
from typing import Dict, List, Optional
from pathlib import Path
from collections import defaultdict


class LanguageDetector:
    """语言检测器"""

    # 文件扩展名到语言的映射
    EXTENSION_LANGUAGE_MAP = {
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.mjs': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.vue': 'vue',
        '.go': 'go',
        '.cs': 'csharp',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.py': 'python',
        '.java': 'java',
        '.rb': 'ruby',
        '.php': 'php',
        '.rs': 'rust',
        '.swift': 'swift',
        '.kt': 'kotlin',
    }

    # 语言到分析器的映射
    LANGUAGE_ANALYZER_MAP = {
        'javascript': 'eslint',
        'typescript': 'eslint',
        'vue': 'eslint',
        'go': 'golangci-lint',
        'c#': 'dotnet-format',
        'csharp': 'dotnet-format',
    }

    def detect_from_files(self, repo_path: str) -> Dict[str, float]:
        """
        从本地文件检测语言

        Args:
            repo_path: 仓库路径

        Returns:
            语言比例字典 {language: percentage}
        """
        # 统计文件扩展名
        ext_counts = defaultdict(int)
        total_files = 0

        repo = Path(repo_path)
        for root, dirs, files in os.walk(repo):
            # 排除常见目录
            dirs[:] = [d for d in dirs if d not in [
                'node_modules', '.git', 'vendor', 'dist', 'build',
                '__pycache__', '.venv', 'venv'
            ]]

            for filename in files:
                file_path = Path(root) / filename
                ext = file_path.suffix.lower()

                if ext in self.EXTENSION_LANGUAGE_MAP:
                    ext_counts[ext] += 1
                    total_files += 1

        if total_files == 0:
            return {}

        # 转换为语言比例
        language_counts = defaultdict(int)
        for ext, count in ext_counts.items():
            language = self.EXTENSION_LANGUAGE_MAP.get(ext)
            if language:
                language_counts[language] += count

        # 计算百分比
        language_percentages = {}
        for language, count in language_counts.items():
            percentage = (count / total_files) * 100
            language_percentages[language] = percentage

        return language_percentages

    def detect_from_local(self, repo_path: str) -> List[Dict[str, any]]:
        """
        从本地文件检测语言（返回排序后的列表）

        Args:
            repo_path: 仓库路径

        Returns:
            语言信息列表 [{language, percentage}, ...]
        """
        percentages = self.detect_from_files(repo_path)

        # 转换为列表并排序
        result = [
            {"language": lang, "percentage": pct}
            for lang, pct in percentages.items()
        ]
        result.sort(key=lambda x: x["percentage"], reverse=True)

        return result

    def get_primary_language(self, languages: Dict[str, float]) -> Optional[str]:
        """
        获取主要语言

        Args:
            languages: 语言比例字典

        Returns:
            主要语言名称
        """
        if not languages:
            return None
        return max(languages, key=languages.get)

    def get_analyzer_for_language(self, language: str) -> Optional[str]:
        """
        获取语言对应的分析器

        Args:
            language: 语言名称

        Returns:
            分析器名称
        """
        return self.LANGUAGE_ANALYZER_MAP.get(language.lower())
