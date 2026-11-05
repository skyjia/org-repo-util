"""collect.docs — 文档和注释分析（REQ §3.7）"""

from __future__ import annotations

import re
from pathlib import Path

from analysis.collectors.base import (
    Collector, collector, is_generated, is_test_path, iter_files, not_found, read_lines,
)

README_SECTION_PATTERNS = {
    "quick_start": re.compile(r"^#{1,3}\s*.*(快速开始|快速上手|getting started|quick ?start|usage|使用)", re.I | re.M),
    "installation": re.compile(r"^#{1,3}\s*.*(安装|install|部署|deploy|setup)", re.I | re.M),
    "configuration": re.compile(r"^#{1,3}\s*.*(配置|config|环境变量|env)", re.I | re.M),
    "architecture": re.compile(r"^#{1,3}\s*.*(架构|architecture|设计|design|结构)", re.I | re.M),
    "api": re.compile(r"^#{1,3}\s*.*(api|接口)", re.I | re.M),
    "contributing": re.compile(r"^#{1,3}\s*.*(贡献|contribut|开发指南|development)", re.I | re.M),
}

# 注释识别（行首，简化启发式）
LINE_COMMENT = {
    "JavaScript": ("//",), "TypeScript": ("//",), "Vue": ("//", "<!--"),
    "Go": ("//",), "Python": ("#",), "C#": ("//",), "Shell": ("#",),
    "Java": ("//",), "Ruby": ("#",), "PHP": ("//", "#"), "Rust": ("//",),
    "CSS": ("/*",), "SCSS": ("//",), "SQL": ("--",),
    "Dart": ("//",), "Kotlin": ("//",), "Swift": ("//",),
    "C": ("//", "/*"), "C++": ("//", "/*"),
}

# 公共 API 声明模式（判断其上是否有文档注释）
PUBLIC_API_PATTERNS = {
    "JavaScript": re.compile(r"^\s*(export\s+(default\s+)?(async\s+)?(function|class|const|let)\s+\w+|module\.exports)"),
    "TypeScript": re.compile(r"^\s*export\s+(default\s+)?(async\s+)?(function|class|const|interface|type|enum)\s+\w+"),
    "Go": re.compile(r"^(func\s+(\([^)]*\)\s*)?[A-Z]\w*|type\s+[A-Z]\w*)"),
    "C#": re.compile(r"^\s*public\s+(static\s+|async\s+|sealed\s+|abstract\s+)*(class|interface|enum|record|[\w<>\[\]]+\s+\w+\s*\()"),
    "Python": re.compile(r"^(class\s+\w+|def\s+\w+)"),  # 模块级
    # Dart：大写开头即公共（类/枚举/mixin/扩展/顶层函数）
    "Dart": re.compile(r"^(abstract\s+|sealed\s+|base\s+|interface\s+|mixin\s+)*(class|enum|mixin|extension)\s+[A-Z]\w*|^[A-Z]\w*<?[\w<>,\s?]*>?\s+[a-z]\w*\s*\("),
    # Java：public 声明
    "Java": re.compile(r"^\s*public\s+(static\s+|final\s+|abstract\s+|synchronized\s+)*(class|interface|enum|record|@interface|[\w<>\[\],\s]+\s+\w+\s*\()"),
    # Ruby：类与公共方法（Ruby 默认 public）
    "Ruby": re.compile(r"^\s*(class\s+[A-Z]\w*|module\s+[A-Z]\w*|def\s+\w+)"),
}


def _lang_of(path: Path) -> str | None:
    from analysis.collectors.base import LANG_BY_EXT
    return LANG_BY_EXT.get(path.suffix.lower())


def _python_docstring_stats(root: Path, max_files: int = 1500) -> dict | None:
    """Python docstring 覆盖率精确统计（ast 解析，M7 T701；替代前缀启发式）"""
    import ast
    py_files = [p for p in iter_files(root)
                if p.suffix == ".py" and not is_generated(p)
                and not is_test_path(p.relative_to(root))]
    if not py_files:
        return None
    stats = {"files": 0, "parse_errors": 0,
             "modules": 0, "modules_with_doc": 0,
             "classes": 0, "classes_with_doc": 0,
             "functions": 0, "functions_with_doc": 0}
    for path in py_files[:max_files]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError, RecursionError):
            stats["parse_errors"] += 1
            continue
        stats["files"] += 1
        stats["modules"] += 1
        if ast.get_docstring(tree):
            stats["modules_with_doc"] += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stats["functions"] += 1
                if ast.get_docstring(node):
                    stats["functions_with_doc"] += 1
            elif isinstance(node, ast.ClassDef):
                stats["classes"] += 1
                if ast.get_docstring(node):
                    stats["classes_with_doc"] += 1
    stats["function_docstring_coverage"] = (
        round(stats["functions_with_doc"] / stats["functions"], 4) if stats["functions"] else None)
    stats["class_docstring_coverage"] = (
        round(stats["classes_with_doc"] / stats["classes"], 4) if stats["classes"] else None)
    if stats["files"] < len(py_files):
        stats["note"] = f"统计上限 {max_files} 文件（共 {len(py_files)} 个 .py）"
    return stats


@collector
class DocsCollector(Collector):
    name = "docs"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        out: dict = {}

        # ---- 1. 项目文档清点 ----
        doc_files = {}
        for name in ("README.md", "README.rst", "README.txt", "README",
                     "CHANGELOG.md", "CONTRIBUTING.md", "docs"):
            p = root / name
            doc_files[name] = p.exists()
        docs_dir_files = []
        if (root / "docs").is_dir():
            docs_dir_files = [str(p.relative_to(root)) for p in (root / "docs").rglob("*.md")][:50]

        readme = None
        for name in ("README.md", "README.rst", "README.txt", "README"):
            if (root / name).exists():
                readme = (root / name).read_text(encoding="utf-8", errors="replace")
                break

        if readme is not None:
            sections = {k: bool(pat.search(readme)) for k, pat in README_SECTION_PATTERNS.items()}
            missing = [k for k, v in sections.items() if not v]
            out["readme"] = {
                "found": True,
                "lines": len(readme.splitlines()),
                "sections": sections,
                "missing_sections": missing,
                "completeness": round(sum(sections.values()) / len(sections), 2),
            }
        else:
            out["readme"] = not_found("README", "仓库缺少 README，建议补充：项目定位、快速开始、安装与配置说明")
        out["doc_files"] = doc_files
        out["docs_dir_files"] = docs_dir_files

        # ---- 2. API 文档（如有） ----
        api_docs = [str(p.relative_to(root)) for p in root.rglob("*")
                    if p.is_file() and not any(x in p.parts for x in ("node_modules", ".git", "vendor"))
                    and re.search(r"(openapi|swagger)\.(json|ya?ml)$", p.name, re.I)]
        out["api_docs"] = (
            {"found": True, "files": api_docs[:10]}
            if api_docs
            else not_found("API 文档", "未发现 OpenAPI/Swagger 文件或生成式 API 文档；建议为对外接口补充 openapi.yaml")
        )

        # ---- 3. 注释覆盖率与公共 API 文档注释 ----
        comment_stats: dict[str, dict] = {}
        api_stats: dict[str, dict] = {}
        for path in iter_files(root):
            rel = path.relative_to(root)
            if is_generated(path) or is_test_path(rel):
                continue
            lang = _lang_of(path)
            if not lang or lang not in LINE_COMMENT:
                continue
            lines = read_lines(path)
            if lines is None:
                continue

            st = comment_stats.setdefault(lang, {"code_lines": 0, "comment_lines": 0})
            markers = LINE_COMMENT[lang]
            in_block = False
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                st["code_lines"] += 1
                if in_block:
                    st["comment_lines"] += 1
                    if "*/" in s:
                        in_block = False
                elif any(s.startswith(m) for m in markers) or s.startswith("/*") or s.startswith("<!--"):
                    st["comment_lines"] += 1
                    if s.startswith("/*") and "*/" not in s:
                        in_block = True

            # 公共 API 文档注释比例
            pat = PUBLIC_API_PATTERNS.get(lang)
            if pat:
                a = api_stats.setdefault(lang, {"public_apis": 0, "documented": 0})
                for i, line in enumerate(lines):
                    if pat.search(line):
                        a["public_apis"] += 1
                        prev = lines[i - 1].strip() if i > 0 else ""
                        # 向上找最近的非空行判断是否文档注释
                        j = i - 1
                        while j >= 0 and not lines[j].strip():
                            j -= 1
                        prev = lines[j].strip() if j >= 0 else ""
                        if (prev.startswith("/**") or prev.startswith("*/") or prev.startswith("*")
                                or prev.startswith("///") or prev.startswith("//")
                                or prev.endswith("*/") or prev.startswith('"""')):
                            a["documented"] += 1

        for lang, st in comment_stats.items():
            st["comment_ratio"] = round(st["comment_lines"] / st["code_lines"], 4) if st["code_lines"] else 0
        for lang, a in api_stats.items():
            a["documented_ratio"] = round(a["documented"] / a["public_apis"], 4) if a["public_apis"] else None

        out["comment_stats"] = comment_stats
        out["public_api_docs"] = api_stats or not_found(
            "公共 API 统计", "未识别到目标语言的公共 API 声明（可能语言不在启发式覆盖范围）")

        # Python docstring 精确统计（ast，M7）
        py_doc = _python_docstring_stats(root)
        if py_doc:
            out["python_docstrings"] = py_doc

        total_code = sum(s["code_lines"] for s in comment_stats.values())
        total_comment = sum(s["comment_lines"] for s in comment_stats.values())
        out["overall_comment_ratio"] = round(total_comment / total_code, 4) if total_code else 0

        return out
