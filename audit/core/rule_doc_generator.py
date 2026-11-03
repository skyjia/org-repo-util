"""
规则文档生成器 - 自动生成所有启用规则的 Markdown 文档

生成内容包括：
- 规则名称
- 所属工具
- 严重级别
- 规则说明
- 修复建议
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class RuleDocGenerator:
    """规则文档生成器"""

    def __init__(self, output_dir: str = "audit/docs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> Optional[str]:
        """
        生成规则文档

        Returns:
            输出文件路径，失败返回 None
        """
        # 收集所有规则
        rules = self._collect_rules()
        if not rules:
            logger.warning("没有找到任何规则")
            return None

        # 生成 Markdown
        markdown = self._render_markdown(rules)

        # 写入文件
        output_path = self.output_dir / "rules-reference.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        return str(output_path)

    def _collect_rules(self) -> List[Dict[str, Any]]:
        """收集所有分析器的规则"""
        rules = []

        # ESLint 规则
        rules.extend(self._collect_eslint_rules())

        # golangci-lint 规则
        rules.extend(self._collect_golangci_rules())

        # dotnet-format 规则
        rules.extend(self._collect_dotnet_rules())

        return rules

    def _collect_eslint_rules(self) -> List[Dict[str, Any]]:
        """收集 ESLint 规则"""
        return [
            {
                "name": "no-unused-vars",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "high",
                "dimension": "code_style",
                "description": "禁止未使用的变量",
                "suggestion": "删除未使用的变量，或在变量名前加 _ 前缀表示有意忽略",
                "url": "https://eslint.org/docs/rules/no-unused-vars",
            },
            {
                "name": "no-undef",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "high",
                "dimension": "code_style",
                "description": "禁止使用未声明的变量",
                "suggestion": "确保变量已正确声明，或使用 typeof 检查变量是否存在",
                "url": "https://eslint.org/docs/rules/no-undef",
            },
            {
                "name": "no-console",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "medium",
                "dimension": "code_style",
                "description": "禁止使用 console 语句",
                "suggestion": "使用专业的日志库（如 winston、pino）替代 console，或在生产环境中移除",
                "url": "https://eslint.org/docs/rules/no-console",
            },
            {
                "name": "eqeqeq",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "medium",
                "dimension": "code_style",
                "description": "要求使用 === 和 !==",
                "suggestion": "使用严格相等运算符 === 和 !== 替代 == 和 !=",
                "url": "https://eslint.org/docs/rules/eqeqeq",
            },
            {
                "name": "no-eval",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "critical",
                "dimension": "security",
                "description": "禁止使用 eval()",
                "suggestion": "eval() 存在安全风险，使用 Function 构造函数或 JSON.parse() 替代",
                "url": "https://eslint.org/docs/rules/no-eval",
            },
            {
                "name": "no-implied-eval",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "critical",
                "dimension": "security",
                "description": "禁止隐式 eval()",
                "suggestion": "避免使用 setTimeout/setInterval 的字符串参数形式",
                "url": "https://eslint.org/docs/rules/no-implied-eval",
            },
            {
                "name": "no-new-func",
                "tool": "eslint",
                "language": "JavaScript/TypeScript",
                "severity": "critical",
                "dimension": "security",
                "description": "禁止使用 new Function()",
                "suggestion": "Function 构造函数与 eval 类似，存在安全风险",
                "url": "https://eslint.org/docs/rules/no-new-func",
            },
        ]

    def _collect_golangci_rules(self) -> List[Dict[str, Any]]:
        """收集 golangci-lint 规则"""
        return [
            {
                "name": "govet",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "high",
                "dimension": "code_style",
                "description": "Go vet 检查代码正确性",
                "suggestion": "修复 govet 报告的问题，通常是 Printf 格式不匹配、 unreachable code 等",
                "url": "https://pkg.go.dev/cmd/vet",
            },
            {
                "name": "errcheck",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "high",
                "dimension": "code_style",
                "description": "检查未处理的错误返回值",
                "suggestion": "处理所有错误返回值，或使用 _ = 明确表示有意忽略",
                "url": "https://github.com/kisielk/errcheck",
            },
            {
                "name": "staticcheck",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "high",
                "dimension": "code_style",
                "description": "静态分析检查",
                "suggestion": "修复 staticcheck 报告的问题，包括性能、正确性、简洁性等",
                "url": "https://staticcheck.io/",
            },
            {
                "name": "gosec",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "high",
                "dimension": "security",
                "description": "安全漏洞检查",
                "suggestion": "修复 gosec 报告的安全问题，如 SQL 注入、弱随机数等",
                "url": "https://github.com/securego/gosec",
            },
            {
                "name": "gosimple",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "medium",
                "dimension": "code_style",
                "description": "代码简化建议",
                "suggestion": "按照建议简化代码，如使用更简洁的语法",
                "url": "https://github.com/dominikh/go-tools",
            },
            {
                "name": "protogetter",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "medium",
                "dimension": "code_style",
                "description": "检查 proto 字段直接访问（应使用 getter）",
                "suggestion": "使用 proto 消息的 getter 方法访问字段，而非直接访问",
                "url": "https://github.com/ghostiam/protogetter",
            },
            {
                "name": "gofmt",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "info",
                "dimension": "code_style",
                "description": "代码格式化检查",
                "suggestion": "运行 gofmt -w 自动修复格式问题",
                "url": "https://pkg.go.dev/cmd/gofmt",
            },
            {
                "name": "gofumpt",
                "tool": "golangci-lint",
                "language": "Go",
                "severity": "info",
                "dimension": "code_style",
                "description": "更严格的代码格式化",
                "suggestion": "运行 gofumpt -w 自动修复格式问题",
                "url": "https://github.com/mvdan/gofumpt",
            },
        ]

    def _collect_dotnet_rules(self) -> List[Dict[str, Any]]:
        """收集 dotnet-format 规则"""
        return [
            {
                "name": "WHITESPACE",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "info",
                "dimension": "code_style",
                "description": "空白格式问题",
                "suggestion": "运行 dotnet format 自动修复格式问题",
                "url": "https://docs.microsoft.com/en-us/dotnet/core/tools/dotnet-format",
            },
            {
                "name": "CA1002",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "medium",
                "dimension": "code_style",
                "description": "不要使用泛型 List<T>",
                "suggestion": "使用 Collection<T> 替代 List<T> 作为公开 API 的返回类型",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1002",
            },
            {
                "name": "CA2227",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "medium",
                "dimension": "code_style",
                "description": "集合属性应为只读",
                "suggestion": "将集合属性改为只读，提供 Add/Remove 方法而非直接设置",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca2227",
            },
            {
                "name": "CA1062",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "medium",
                "dimension": "code_style",
                "description": "验证公开方法的非空参数",
                "suggestion": "在使用参数前检查是否为 null，抛出 ArgumentNullException",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1062",
            },
            {
                "name": "CA1056",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "medium",
                "dimension": "code_style",
                "description": "URI 属性不应为字符串",
                "suggestion": "使用 System.Uri 类型替代 string 表示 URI",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1056",
            },
            {
                "name": "CA5394",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "high",
                "dimension": "security",
                "description": "不要使用不安全的随机数生成器",
                "suggestion": "使用 System.Security.Cryptography.RandomNumberGenerator 替代 System.Random",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5394",
            },
            {
                "name": "CA5358",
                "tool": "dotnet-format",
                "language": "C#",
                "severity": "high",
                "dimension": "security",
                "description": "审查 ECB 密码模式的使用",
                "suggestion": "ECB 模式不安全，使用 CBC 或 GCM 模式替代",
                "url": "https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5358",
            },
        ]

    def _render_markdown(self, rules: List[Dict[str, Any]]) -> str:
        """渲染 Markdown 文档"""
        lines = [
            "# 审计规则参考文档",
            "",
            f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"> 规则总数: {len(rules)}",
            "",
            "---",
            "",
            "## 目录",
            "",
        ]

        # 按工具分组
        tools = {}
        for rule in rules:
            tool = rule["tool"]
            if tool not in tools:
                tools[tool] = []
            tools[tool].append(rule)

        # 生成目录
        for tool, tool_rules in sorted(tools.items()):
            lines.append(f"- [{tool}](#{tool})")
            for rule in tool_rules:
                lines.append(f"  - [{rule['name']}](#{rule['name'].lower()})")

        lines.append("")
        lines.append("---")
        lines.append("")

        # 生成规则详情
        for tool, tool_rules in sorted(tools.items()):
            lines.append(f"## {tool}")
            lines.append("")

            # 语言信息
            languages = set(r["language"] for r in tool_rules)
            lines.append(f"**语言:** {', '.join(sorted(languages))}")
            lines.append("")

            for rule in tool_rules:
                lines.append(f"### {rule['name']}")
                lines.append("")
                lines.append(f"| 属性 | 值 |")
                lines.append(f"|------|-----|")
                lines.append(f"| **工具** | {rule['tool']} |")
                lines.append(f"| **语言** | {rule['language']} |")
                lines.append(f"| **严重级别** | {rule['severity'].upper()} |")
                lines.append(f"| **维度** | {rule['dimension']} |")
                if rule.get("url"):
                    lines.append(f"| **文档** | [{rule['url']}]({rule['url']}) |")
                lines.append("")
                lines.append(f"**说明:** {rule['description']}")
                lines.append("")
                lines.append(f"**修复建议:** {rule['suggestion']}")
                lines.append("")

        return "\n".join(lines)
