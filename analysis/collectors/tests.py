"""collect.tests — 测试分析（REQ §3.8）：纯静态代理指标 + 已有产物读取 + CI 配置只读"""

from __future__ import annotations

import json
import re
from pathlib import Path

from analysis.collectors.base import (
    CODE_EXTS, Collector, collector, is_generated, is_test_path, iter_files,
    not_found, read_lines,
)

FRAMEWORK_MARKERS = {
    # (文件, JSON 字段路径, 关键词) -> 框架
    "jest": ("package.json", "jest"), "vitest": ("package.json", "vitest"),
    "mocha": ("package.json", "mocha"), "cypress": ("package.json", "cypress"),
    "playwright": ("package.json", "playwright"),
}

TEST_STEP_PATTERN = re.compile(
    r"(npm|yarn|pnpm)\s+(run\s+)?(test|e2e|coverage)|go\s+test|dotnet\s+test|pytest|phpunit",
    re.I)

COVERAGE_ARTIFACTS = ("coverage/lcov.info", "coverage/coverage-final.json", "coverage.xml",
                      "cover.out", "coverage/index.html", ".coverage", "lcov.info",
                      # M7: Java jacoco / Ruby simplecov / Python htmlcov
                      "target/site/jacoco/jacoco.xml",
                      "build/reports/jacoco/test/jacocoTestReport.xml",
                      "coverage/.resultset.json", "htmlcov/index.html")


def _detect_frameworks(root: Path) -> dict:
    found = {}
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        for fw in ("jest", "vitest", "mocha", "cypress", "@playwright/test",
                   "karma", "chai", "@testing-library/react", "@vue/test-utils"):
            key = fw.lstrip("@").split("/")[-1] if fw.startswith("@") else fw
            if fw in deps:
                found[key] = deps[fw]
        if data.get("scripts", {}).get("test"):
            found["_test_script"] = data["scripts"]["test"][:120]
    gomod = root / "go.mod"
    if gomod.exists():
        text = gomod.read_text(encoding="utf-8", errors="replace")
        if "stretchr/testify" in text:
            found["testify"] = True
        found.setdefault("go test", "builtin")
    for csproj in root.rglob("*.csproj"):
        if any(x in csproj.parts for x in ("node_modules", "obj", "bin")):
            continue
        text = csproj.read_text(encoding="utf-8", errors="replace")
        for fw in ("xunit", "nunit", "MSTest", "Microsoft.NET.Test.Sdk"):
            if fw.lower() in text.lower():
                found[fw] = True
    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        text = ((root / "requirements.txt").read_text(errors="replace")
                if (root / "requirements.txt").exists() else "")
        text += ((root / "pyproject.toml").read_text(errors="replace")
                 if (root / "pyproject.toml").exists() else "")
        for fw in ("pytest", "unittest"):
            if fw in text.lower():
                found[fw] = True
    # ---- M7: Dart / Java / Ruby / Shell ----
    pubspec = root / "pubspec.yaml"
    if pubspec.exists():
        try:
            import yaml
            data = yaml.safe_load(pubspec.read_text(errors="replace")) or {}
            all_deps = {**(data.get("dependencies") or {}), **(data.get("dev_dependencies") or {})}
            for fw in ("flutter_test", "test", "mockito", "integration_test", "build_runner"):
                if fw in all_deps:
                    found[fw] = all_deps[fw] if isinstance(all_deps[fw], str) else True
        except Exception:
            pass
    for build_file in list(root.glob("pom.xml")) + list(root.glob("*/pom.xml")) \
            + list(root.glob("build.gradle*")) + list(root.glob("*/build.gradle*")):
        text = build_file.read_text(encoding="utf-8", errors="replace")
        for fw in ("junit", "mockito", "testng", "surefire", "spock"):
            if fw in text.lower():
                found.setdefault(fw, True)
    gemfile = root / "Gemfile"
    if gemfile.exists():
        text = gemfile.read_text(encoding="utf-8", errors="replace").lower()
        for fw in ("rspec", "minitest", "cucumber", "rubocop"):
            if fw in text:
                found[fw] = True
    if next(root.rglob("*.bats"), None):
        found["bats"] = True
    return found


def _ci_test_steps(root: Path) -> dict:
    """读取 CI 配置（仅读文件，不触发运行）"""
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return not_found("CI 配置", "未发现 .github/workflows/；如使用其他 CI（GitLab/Jenkins），"
                                   "建议将测试执行配置纳入版本库以便评估自动化测试情况")
    steps = []
    for yml in sorted(wf_dir.glob("*.y*ml")):
        text = yml.read_text(encoding="utf-8", errors="replace")
        hits = sorted(set(m.group(0) for m in TEST_STEP_PATTERN.finditer(text)))
        steps.append({"workflow": yml.name, "test_steps_found": hits,
                      "runs_tests": bool(hits)})
    any_tests = any(s["runs_tests"] for s in steps)
    return {"found": True, "runs_tests_in_ci": any_tests, "workflows": steps}


@collector
class TestsCollector(Collector):
    name = "tests"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path

        test_files: list[dict] = []
        test_lines = 0
        prod_lines = 0
        empty_tests = []
        skipped_markers = 0

        for path in iter_files(root):
            rel = path.relative_to(root)
            if is_generated(path) or rel.suffix.lower() not in CODE_EXTS:
                continue
            lines = read_lines(path)
            if lines is None:
                continue
            if is_test_path(rel):
                test_lines += len(lines)
                text = "\n".join(lines)
                # 空测试/无断言启发式
                has_assert = bool(re.search(
                    r"(assert|expect\(|should\.|t\.(Error|Fatal)|Assert\.|verify\(|chai)", text))
                n_cases = len(re.findall(
                    r"(func Test\w+|it\(|test\(|def test_|\[Fact\]|\[Test\]|@Test)", text))
                if n_cases > 0 and not has_assert:
                    empty_tests.append({"path": str(rel), "test_cases": n_cases,
                                        "reason": "未检测到断言"})
                skipped_markers += len(re.findall(
                    r"(t\.Skip|it\.skip|test\.skip|xit\(|xtest\(|@Ignore|\[Skip\]|pytest\.mark\.skip|@pytest\.mark\.skipif)", text))
                if len(test_files) < 200:
                    test_files.append({"path": str(rel), "lines": len(lines)})
            else:
                prod_lines += len(lines)

        # 覆盖率产物（REQ §2.2-4：如有则读取并标注）
        coverage_artifacts = []
        for rel_path in COVERAGE_ARTIFACTS:
            p = root / rel_path
            if p.exists():
                try:
                    mtime = p.stat().st_mtime
                    import datetime
                    generated = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                except OSError:
                    generated = None
                coverage_artifacts.append({"path": rel_path, "generated_at_file_mtime": generated})

        frameworks = _detect_frameworks(root)

        return {
            "frameworks": frameworks or not_found(
                "测试框架", "未识别到测试框架；建议引入与语言生态匹配的测试框架（JS: vitest/jest, Go: go test+testify, C#: xunit）"),
            "test_files_count": len(test_files),
            "test_files": sorted(test_files, key=lambda f: -f["lines"])[:30],
            "test_lines": test_lines,
            "production_lines": prod_lines,
            "test_to_production_ratio": round(test_lines / prod_lines, 4) if prod_lines else 0,
            "coverage_static_note": "纯静态约束（REQ §1.2）：未运行测试，覆盖率为静态代理指标（测试/生产代码比）",
            "coverage_artifacts": (
                {"found": True, "files": coverage_artifacts,
                 "note": "引用仓库已有产物，生成时间取自文件 mtime（可能晚于实际生成）"}
                if coverage_artifacts
                else not_found("覆盖率报告", "仓库中未发现 lcov.info/coverage.xml/cover.out 等产物；"
                                            "建议在 CI 中生成覆盖率报告并提交或由流水线归档")),
            "empty_or_assertion_free_tests": empty_tests[:30],
            "skipped_test_markers": skipped_markers,
            "ci": _ci_test_steps(root),
        }
