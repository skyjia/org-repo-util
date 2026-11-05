"""
AI 辅助配置生成 - 分析仓库结构并生成审计配置建议
"""

import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
import yaml

from audit.ai.client import create_claude_client

logger = logging.getLogger(__name__)


class ConfigGenerator:
    """AI 辅助配置生成器"""

    def __init__(self):
        """初始化配置生成器"""
        self.client = create_claude_client()

    def analyze_repo(self, repo_path: str) -> Dict[str, Any]:
        """
        分析仓库结构

        Args:
            repo_path: 仓库路径

        Returns:
            仓库特征字典
        """
        repo = Path(repo_path)

        features = {
            "language": self._detect_language(repo),
            "framework": self._detect_framework(repo),
            "build_tools": self._detect_build_tools(repo),
            "test_framework": self._detect_test_framework(repo),
            "code_style": self._detect_code_style(repo),
            "dependencies": self._count_dependencies(repo),
        }

        return features

    def _detect_language(self, repo: Path) -> List[str]:
        """检测编程语言"""
        extensions = {
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".vue": "vue",
            ".py": "python",
            ".go": "go",
            ".cs": "csharp",
            ".java": "java",
            ".rb": "ruby",
        }

        languages = set()
        for ext, lang in extensions.items():
            if list(repo.rglob(f"*{ext}")):
                languages.add(lang)

        return list(languages)

    def _detect_framework(self, repo: Path) -> Optional[str]:
        """检测框架"""
        # 检查 package.json
        package_json = repo / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                    if "vue" in deps:
                        return "Vue.js"
                    elif "react" in deps:
                        return "React"
                    elif "angular" in deps or "@angular/core" in deps:
                        return "Angular"
                    elif "next" in deps:
                        return "Next.js"
                    elif "nuxt" in deps:
                        return "Nuxt.js"
            except Exception:
                pass

        # 检查 go.mod
        go_mod = repo / "go.mod"
        if go_mod.exists():
            return "Go"

        # 检查 .csproj
        csproj_files = list(repo.rglob("*.csproj"))
        if csproj_files:
            return ".NET"

        return None

    def _detect_build_tools(self, repo: Path) -> List[str]:
        """检测构建工具"""
        tools = []

        if (repo / "package.json").exists():
            tools.append("npm")

        if (repo / "yarn.lock").exists():
            tools.append("yarn")

        if (repo / "pnpm-lock.yaml").exists():
            tools.append("pnpm")

        if (repo / "go.mod").exists():
            tools.append("go modules")

        if (repo / "Makefile").exists():
            tools.append("make")

        if list(repo.rglob("*.csproj")):
            tools.append("dotnet")

        return tools

    def _detect_test_framework(self, repo: Path) -> List[str]:
        """检测测试框架"""
        frameworks = []

        package_json = repo / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                    if "jest" in deps:
                        frameworks.append("Jest")
                    if "mocha" in deps:
                        frameworks.append("Mocha")
                    if "vitest" in deps:
                        frameworks.append("Vitest")
            except Exception:
                pass

        return frameworks

    def _detect_code_style(self, repo: Path) -> Dict[str, bool]:
        """检测代码风格配置"""
        style = {
            "has_eslint": False,
            "has_prettier": False,
            "has_editorconfig": False,
        }

        if (repo / ".eslintrc.js").exists() or (repo / ".eslintrc.json").exists():
            style["has_eslint"] = True

        if (repo / ".prettierrc").exists() or (repo / "prettier.config.js").exists():
            style["has_prettier"] = True

        if (repo / ".editorconfig").exists():
            style["has_editorconfig"] = True

        return style

    def _count_dependencies(self, repo: Path) -> Dict[str, int]:
        """统计依赖数量"""
        counts = {
            "production": 0,
            "development": 0,
        }

        package_json = repo / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    counts["production"] = len(data.get("dependencies", {}))
                    counts["development"] = len(data.get("devDependencies", {}))
            except Exception:
                pass

        return counts

    def generate_config_suggestion(self, repo_path: str) -> str:
        """
        生成配置建议

        Args:
            repo_path: 仓库路径

        Returns:
            YAML 格式的配置建议
        """
        features = self.analyze_repo(repo_path)

        prompt = f"""分析以下仓库特征，生成审计配置建议（YAML 格式）：

仓库特征：
- 编程语言: {', '.join(features['language'])}
- 框架: {features['framework']}
- 构建工具: {', '.join(features['build_tools'])}
- 测试框架: {', '.join(features['test_framework'])}
- 代码风格配置: ESLint={features['code_style']['has_eslint']}, Prettier={features['code_style']['has_prettier']}
- 依赖数量: 生产={features['dependencies']['production']}, 开发={features['dependencies']['development']}

请生成 .audit-config.yaml 配置建议，包含：
1. 语言特定的分析器配置
2. 推荐的规则集
3. 排除的文件/目录
4. 严重级别调整

输出格式：YAML"""

        try:
            response = self.client.chat([
                {"role": "user", "content": prompt}
            ])

            # 提取 YAML 部分
            if "```yaml" in response:
                yaml_start = response.find("```yaml") + 7
                yaml_end = response.find("```", yaml_start)
                return response[yaml_start:yaml_end].strip()
            elif "```" in response:
                yaml_start = response.find("```") + 3
                yaml_end = response.find("```", yaml_start)
                return response[yaml_start:yaml_end].strip()
            else:
                return response.strip()

        except Exception as e:
            logger.error(f"生成配置建议失败: {e}")
            raise

    def save_config_suggestion(self, repo_path: str, output_path: Optional[str] = None):
        """
        保存配置建议到文件

        Args:
            repo_path: 仓库路径
            output_path: 输出文件路径，默认为 <repo_path>/.audit-config.yaml
        """
        if output_path is None:
            output_path = str(Path(repo_path) / ".audit-config.yaml")

        config_yaml = self.generate_config_suggestion(repo_path)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(config_yaml)

        logger.info(f"配置建议已保存到: {output_path}")
        return output_path
