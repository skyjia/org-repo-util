"""Collector 基类与公共工具（ANALYSIS-DESIGN.md §5 统一契约）

- 输出必含 _meta（subtask/generated_at/commit_sha/warnings）
- 「如有」类数据缺失时输出 not_found()（REQ §2.3：标注 + 补齐建议，不得省略）
- 文件遍历统一排除规则，且排除规则必须写入 _meta（REQ §3.2 披露要求）
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterator, Optional

from analysis.core.models import now_iso
from analysis.core.registry import register

# ---------- 语言映射 ----------
LANG_BY_EXT = {
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".vue": "Vue",
    ".py": "Python", ".go": "Go", ".cs": "C#",
    ".java": "Java", ".rb": "Ruby", ".php": "PHP", ".rs": "Rust",
    ".c": "C", ".h": "C/C++ Header", ".cpp": "C++", ".cc": "C++", ".hpp": "C++ Header",
    ".swift": "Swift", ".kt": "Kotlin", ".m": "Objective-C",
    ".sh": "Shell", ".fish": "Fish", ".ps1": "PowerShell",
    ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "Less",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".md": "Markdown", ".txt": "Text",
    ".dart": "Dart", ".lua": "Lua", ".r": "R",
}

CODE_EXTS = {  # 计入「代码行数」的扩展名（文档/配置另计）
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".py", ".go", ".cs",
    ".java", ".rb", ".php", ".rs", ".c", ".h", ".cpp", ".cc", ".hpp",
    ".swift", ".kt", ".m", ".sh", ".fish", ".ps1", ".sql", ".dart", ".lua",
    ".html", ".css", ".scss", ".less",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "vendor", "vendors", "dist", "build",
    "out", "target", "bin", "obj", "__pycache__", ".venv", "venv", "env",
    "coverage", ".next", ".nuxt", ".output", ".idea", ".vscode", ".gradle",
    ".mvn", "Pods", ".terraform", ".cache", "testdata_snapshots",
}

GENERATED_PATTERNS = (
    "*.min.js", "*.min.css", "*.pb.go", "*_pb2.py", "*.generated.*",
    "*.designer.cs", "*-lock.*", "package-lock.json", "yarn.lock", "go.sum",
    "uv.lock", "Cargo.lock", "poetry.lock", "*.snap",
)

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".tiff",
    ".zip", ".gz", ".tar", ".bz2", ".7z", ".rar", ".jar", ".war", ".dll",
    ".so", ".dylib", ".exe", ".bin", ".pdf", ".woff", ".woff2", ".ttf",
    ".eot", ".mp3", ".mp4", ".avi", ".mov", ".wasm", ".db", ".sqlite",
}


def is_generated(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, p) for p in GENERATED_PATTERNS)


def is_test_path(rel: Path) -> bool:
    """按路径/命名约定判断测试代码"""
    parts = {p.lower() for p in rel.parts[:-1]}
    if parts & {"test", "tests", "__tests__", "spec", "specs", "e2e", "cypress"}:
        return True
    name = rel.name
    return (
        name.endswith("_test.go")
        or ".test." in name or ".spec." in name
        or (name.startswith("test_") and name.endswith(".py"))
        or (name.startswith("Test") and name.endswith(".cs"))
        or (name.endswith("Tests.cs") or name.endswith("Test.cs"))
        or (name.startswith("Test") and name.endswith(".java"))
    )


def iter_files(root: Path, exclude_dirs: Optional[set] = None) -> Iterator[Path]:
    """遍历仓库文件（跳过排除目录与二进制）"""
    exclude = DEFAULT_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except (PermissionError, OSError):
            continue
        for e in entries:
            if e.is_symlink():
                continue
            if e.is_dir():
                if e.name not in exclude and not e.name.startswith("."):
                    stack.append(e)
            elif e.is_file() and e.suffix.lower() not in BINARY_EXTS:
                yield e


def read_lines(path: Path, max_bytes: int = 5_000_000) -> Optional[list[str]]:
    """读文本行；二进制/超大文件返回 None"""
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace").splitlines()
    except (OSError, PermissionError):
        return None


def not_found(what: str, suggestion: str) -> dict:
    """REQ §2.3 统一缺失结构"""
    return {"found": False, "what": what, "suggestion": suggestion}


def collector(cls):
    """类装饰器：注册为 collect.<name> handler，统一注入 _meta"""
    inst = cls()
    subtask = f"collect.{cls.name}"

    @register(subtask)
    def handler(ctx) -> dict:
        ctx.log(f"开始采集: {cls.name}")
        result = inst.collect(ctx)
        meta = result.setdefault("_meta", {})
        meta.update({
            "subtask": subtask,
            "generated_at": now_iso(),
            "commit_sha": ctx.commit_sha,
        })
        meta.setdefault("warnings", [])
        meta.setdefault("excluded_dirs", sorted(DEFAULT_EXCLUDE_DIRS))
        return result

    return cls


class Collector:
    name: str = ""

    def collect(self, ctx) -> dict:
        raise NotImplementedError
