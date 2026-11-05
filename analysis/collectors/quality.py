"""collect.quality — 代码质量分析（REQ §3.4）：audit lint 桥接 + lizard 复杂度"""

from __future__ import annotations

from pathlib import Path

from analysis.collectors.audit_bridge import load_audit_report, split_issues_by_dimension, summarize_issues
from analysis.collectors.base import (
    CODE_EXTS, Collector, collector, is_generated, is_test_path, iter_files, not_found,
    read_lines,
)

LIZARD_EXTS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".py", ".go", ".cs",
               ".java", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".swift", ".kt"}
CCN_HIGH = 25       # 严重
CCN_MEDIUM = 15     # 中等
FUNC_LONG = 100     # 函数长度阈值（行）
FILE_LONG = 800     # 文件长度阈值（行）
MAX_LIZARD_FILES = 3000


@collector
class QualityCollector(Collector):
    name = "quality"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        out: dict = {}

        # ---- 1. audit lint 桥接（REQ §1.3） ----
        audit = load_audit_report(ctx.org, ctx.repo)
        lint_issues, _ = split_issues_by_dimension(audit)
        if audit.get("found"):
            out["style_lint"] = {
                "source": "audit",
                "audit_generated_at": audit.get("audit_generated_at"),
                "staleness_note": audit.get("staleness_note"),
                # 评分密度计算必需（scoring 按 issues/KLOC 归一）
                "lines_scanned": audit.get("lines_scanned"),
                "files_scanned": audit.get("files_scanned"),
                **summarize_issues(lint_issues, rel_root=None),
            }
        else:
            out["style_lint"] = {
                "source": None,
                **not_found("风格规范检查结果",
                            audit.get("suggestion", "先运行 audit 再重跑本分析")),
            }

        # ---- 2. lizard 复杂度 ----
        try:
            import lizard
        except ImportError:
            out["complexity"] = not_found(
                "复杂度分析", "lizard 未安装：运行 analysis/setup.sh")
            return out

        n_files = 0
        total_ccn = 0
        total_funcs = 0
        high_ccn, medium_ccn, long_funcs, long_files = [], [], [], []

        for path in iter_files(root):
            rel = path.relative_to(root)
            if (path.suffix.lower() not in LIZARD_EXTS or path.suffix.lower() not in CODE_EXTS
                    or is_generated(path)):
                continue
            lines = read_lines(path)
            if lines is None:
                continue
            n_files += 1
            if len(lines) > FILE_LONG and not is_test_path(rel):
                long_files.append({"path": str(rel), "lines": len(lines)})
            if n_files > MAX_LIZARD_FILES:
                continue
            try:
                res = lizard.analyze_file(str(path))
            except Exception:
                continue
            for fn in res.function_list:
                total_funcs += 1
                total_ccn += fn.cyclomatic_complexity
                item = {"path": str(rel), "function": fn.name,
                        "line": fn.start_line, "ccn": fn.cyclomatic_complexity,
                        "length": fn.length}
                if fn.cyclomatic_complexity > CCN_HIGH:
                    high_ccn.append(item)
                elif fn.cyclomatic_complexity > CCN_MEDIUM:
                    medium_ccn.append(item)
                if fn.length > FUNC_LONG:
                    long_funcs.append(item)

        avg_ccn = round(total_ccn / total_funcs, 2) if total_funcs else None
        out["complexity"] = {
            "tool": f"lizard (files={n_files}, cap={MAX_LIZARD_FILES})",
            "functions_analyzed": total_funcs,
            "average_ccn": avg_ccn,
            "high_ccn_count": len(high_ccn),
            "medium_ccn_count": len(medium_ccn),
            "high_ccn_ratio": round(len(high_ccn) / total_funcs, 4) if total_funcs else None,
            "top_complex_functions": sorted(high_ccn + medium_ccn,
                                            key=lambda x: -x["ccn"])[:20],
            "long_functions": sorted(long_funcs, key=lambda x: -x["length"])[:20],
            "long_files": sorted(long_files, key=lambda x: -x["lines"])[:20],
        }

        # ---- 3. 代码异味（轻量启发式；重复代码检测留待后续） ----
        smells = []
        if len(high_ccn) > 5:
            smells.append({"smell": "god_function_risk", "severity": "high",
                           "detail": f"{len(high_ccn)} 个函数圈复杂度 > {CCN_HIGH}"})
        if len(long_files) > 10:
            smells.append({"smell": "large_module", "severity": "medium",
                           "detail": f"{len(long_files)} 个文件超过 {FILE_LONG} 行"})
        if avg_ccn and avg_ccn > 8:
            smells.append({"smell": "high_average_complexity", "severity": "medium",
                           "detail": f"平均圈复杂度 {avg_ccn}"})
        out["code_smells"] = smells or [{"smell": "none_detected", "severity": "info",
                                         "detail": "轻量启发式未检出明显异味（重复代码检测未纳入本期）"}]
        return out
