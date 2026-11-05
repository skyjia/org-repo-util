"""collect.structure — 代码结构（REQ §3.2）：目录树 + 行数统计（生产/测试/生成分类）"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from analysis.collectors.base import (
    CODE_EXTS, LANG_BY_EXT, Collector, collector, is_generated, is_test_path,
    iter_files, read_lines,
)


@collector
class StructureCollector(Collector):
    name = "structure"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        by_lang: dict[str, dict] = defaultdict(lambda: {"files": 0, "lines": 0})
        by_category = {"production": {"files": 0, "lines": 0},
                       "test": {"files": 0, "lines": 0},
                       "generated_or_vendored": {"files": 0, "lines": 0}}
        top_dirs: dict[str, dict] = {}
        longest: list[tuple[int, str]] = []
        total_files = 0

        for path in iter_files(root):
            rel = path.relative_to(root)
            ext = path.suffix.lower()
            lines = read_lines(path)
            n_lines = len(lines) if lines is not None else 0
            total_files += 1

            lang = LANG_BY_EXT.get(ext)
            if lang and ext in CODE_EXTS:
                by_lang[lang]["files"] += 1
                by_lang[lang]["lines"] += n_lines

            if is_generated(path):
                cat = "generated_or_vendored"
            elif is_test_path(rel):
                cat = "test"
            else:
                cat = "production"
            by_category[cat]["files"] += 1
            by_category[cat]["lines"] += n_lines

            if ext in CODE_EXTS and cat == "production":
                longest.append((n_lines, str(rel)))

            # 顶层目录统计（第一层）
            top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            entry = top_dirs.setdefault(top, {"files": 0, "lines": 0, "subdirs": set()})
            entry["files"] += 1
            entry["lines"] += n_lines
            if len(rel.parts) > 2:
                entry["subdirs"].add(rel.parts[1])

        longest.sort(reverse=True)
        tree = {
            name: {
                "files": e["files"],
                "lines": e["lines"],
                "subdirs": sorted(e["subdirs"])[:20],
            }
            for name, e in sorted(top_dirs.items(), key=lambda kv: -kv[1]["lines"])
        }

        # 主语言判定（按代码行数）
        code_langs = {l: s for l, s in by_lang.items()}
        primary = max(code_langs, key=lambda l: code_langs[l]["lines"]) if code_langs else None

        prod = by_category["production"]["lines"] or 1
        return {
            "total_files": total_files,
            "primary_language": primary,
            "languages": dict(sorted(by_lang.items(), key=lambda kv: -kv[1]["lines"])),
            "categories": by_category,
            "test_to_production_ratio": round(by_category["test"]["lines"] / prod, 4),
            "top_level_dirs": tree,
            "longest_files": [
                {"path": p, "lines": n} for n, p in longest[:20]
            ],
            "exclusion_disclosure": "行数统计已排除: 目录 "
                + ", ".join(sorted(list({"node_modules", "vendor", "dist", "build", ".git"})))
                + "；及生成/锁定文件（*.min.js、*.pb.go、lock 文件等），完整清单见 _meta.excluded_dirs",
        }
