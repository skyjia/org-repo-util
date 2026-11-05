"""collect.performance — 性能分析（REQ §3.6）：静态启发式反模式识别

边界声明为必含字段（REQ §3.6）：未运行任何性能测试，结论仅方向性参考。
"""

from __future__ import annotations

import re
from pathlib import Path

from analysis.collectors.base import (
    CODE_EXTS, Collector, collector, is_generated, iter_files, read_lines,
)

LOOP_START = re.compile(r"^\s*(for|while)\b[^\n]*[:{(]?\s*$|^\s*(for|while)\b.*[:{]\s*$")
IO_CALL = re.compile(
    r"(\.query\(|\.execute\(|\.exec\(|\.find(?:One|All)?\(|\.select\(|"
    r"fetch\(|axios\.|requests\.(?:get|post|put|delete)\(|http\.(?:Get|Post|Do)\(|"
    r"db\.\w+\(|session\.\w+\(|open\(|readFile(?:Sync)?\(|writeFile(?:Sync)?\()")
LOOP_WINDOW = 12          # 循环体检查窗口（行）
STRING_CONCAT = re.compile(r"^\s*\w+\s*(\+=|\+\+)\s*.*[\"'`]")
ASYNC_DEF = re.compile(r"^\s*(async\s+def\s+\w+|async\s+function\s+\w+|\w+\s*:\s*async)")
SYNC_BLOCKING = re.compile(r"(requests\.(?:get|post)|time\.sleep\(|open\([^)]*\)\.read|\.readFile)")
MAX_HITS_PER_PATTERN = 60

ANTIPATTERNS = ("io_in_loop", "string_concat_in_loop", "sync_io_in_async",
                "unbounded_select")
UNBOUNDED_SELECT = re.compile(
    r"(?i)[\"'`](select\s+.+?\s+from\s+[\w`\"'.]+(?![\s\S]{0,120}\b(limit|top|where\s+rownum)\b))[\"'`]")


@collector
class PerformanceCollector(Collector):
    name = "performance"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        hits: dict[str, list] = {k: [] for k in ANTIPATTERNS}

        for path in iter_files(root):
            rel = path.relative_to(root)
            if path.suffix.lower() not in CODE_EXTS or is_generated(path):
                continue
            lines = read_lines(path)
            if lines is None or len(lines) > 20000:
                continue

            for i, line in enumerate(lines):
                # 1. 循环内 IO / 字符串拼接
                if LOOP_START.match(line):
                    window = lines[i + 1: i + 1 + LOOP_WINDOW]
                    for j, wl in enumerate(window):
                        stripped = wl.strip()
                        if not stripped or stripped.startswith(("//", "#", "*")):
                            continue
                        if IO_CALL.search(wl) and len(hits["io_in_loop"]) < MAX_HITS_PER_PATTERN:
                            hits["io_in_loop"].append({
                                "file": str(rel), "line": i + j + 2,
                                "loop_line": i + 1,
                                "evidence": f"{line.strip()[:80]} → {stripped[:100]}",
                                "confidence": "suspected",
                            })
                            break
                        if STRING_CONCAT.match(wl) and len(hits["string_concat_in_loop"]) < MAX_HITS_PER_PATTERN:
                            hits["string_concat_in_loop"].append({
                                "file": str(rel), "line": i + j + 2,
                                "evidence": stripped[:120], "confidence": "suspected"})
                            break

                # 2. async 上下文中的同步阻塞调用
                if ASYNC_DEF.match(line):
                    window = lines[i + 1: i + 1 + 25]
                    for j, wl in enumerate(window):
                        if LOOP_START.match(wl) or ASYNC_DEF.match(wl):
                            break  # 简化：不跨函数/循环边界
                        if SYNC_BLOCKING.search(wl) and len(hits["sync_io_in_async"]) < MAX_HITS_PER_PATTERN:
                            hits["sync_io_in_async"].append({
                                "file": str(rel), "line": i + j + 2,
                                "evidence": wl.strip()[:120], "confidence": "suspected"})
                            break

                # 3. SELECT 无 LIMIT
                if ("select" in line.lower() and len(hits["unbounded_select"]) < MAX_HITS_PER_PATTERN
                        and UNBOUNDED_SELECT.search(line)):
                    hits["unbounded_select"].append({
                        "file": str(rel), "line": i + 1,
                        "evidence": line.strip()[:140], "confidence": "suspected"})

        total = sum(len(v) for v in hits.values())
        return {
            "boundary_declaration": (
                "本维度基于静态启发式分析（REQ §3.6），未运行任何性能测试；"
                "所有命中均为『疑似』（suspected），需人工复核；结论仅为方向性参考。"),
            "antipattern_counts": {k: len(v) for k, v in hits.items()},
            "total_suspected": total,
            "hits": {k: v[:20] for k, v in hits.items()},
            "benchmark_artifacts": self._find_benchmarks(root),
        }

    @staticmethod
    def _find_benchmarks(root: Path) -> dict:
        from analysis.collectors.base import not_found
        files = []
        for pat in ("*bench*_test.go", "Benchmark*", "*benchmark*.json", "*benchmark*.md",
                    "bench/*.txt", "*perf*.report.json"):
            files.extend(str(p.relative_to(root)) for p in root.rglob(pat)
                         if p.is_file() and "node_modules" not in p.parts)
        bench_dirs = [d for d in ("bench", "benchmark", "benchmarks", "perf")
                      if (root / d).is_dir()]
        if files or bench_dirs:
            return {"found": True, "files": sorted(set(files))[:20], "directories": bench_dirs,
                    "note": "仓库已有 benchmark 产物/目录（引用自仓库文件，未运行）"}
        return not_found("性能测试结果",
                         "仓库中未发现 benchmark 结果或性能测试产物；建议为关键路径建立 benchmark 并归档结果")
