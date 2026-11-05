"""collect.dependencies — 依赖关系分析（REQ §3.3）

manifest 解析（纯 Python）+ 模块级依赖图：
- JS/TS: madge（可用时）；Go: go mod graph；C#: csproj ProjectReference；Python: import 解析
- 工具缺失 → 按 REQ §3.3 标注省略原因（必出项降级需说明）
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from analysis.collectors.base import Collector, collector, iter_files, not_found


def _parse_package_json(root: Path) -> dict:
    out = {"runtime": {}, "development": {}}
    pkg = root / "package.json"
    if not pkg.exists():
        return out
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return out
    out["runtime"] = data.get("dependencies", {})
    out["development"] = data.get("devDependencies", {})
    return out


def _parse_go_mod(root: Path) -> dict:
    gomod = root / "go.mod"
    if not gomod.exists():
        return {"runtime": {}, "development": {}}
    text = gomod.read_text(encoding="utf-8", errors="replace")
    deps = {}
    in_require = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("require ("):
            in_require = True
            continue
        if in_require and s == ")":
            in_require = False
            continue
        m = re.match(r"require\s+(\S+)\s+(v[\w.\-+]+)", s)
        if m:
            deps[m.group(1)] = m.group(2)
            continue
        if in_require:
            m = re.match(r"(\S+)\s+(v[\w.\-+]+)", s)
            if m and "// indirect" not in s or (m and "indirect" in s):
                if m:
                    deps[m.group(1)] = m.group(2)
    return {"runtime": deps, "development": {}}


def _parse_csproj(root: Path) -> dict:
    deps = {}
    for csproj in root.rglob("*.csproj"):
        if any(x in csproj.parts for x in ("node_modules", "obj", "bin")):
            continue
        text = csproj.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
                r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]*)")?', text, re.I):
            deps[m.group(1)] = m.group(2) or "(version-unspecified)"
    return {"runtime": deps, "development": {}}


def _parse_python(root: Path) -> dict:
    deps = {}
    req = root / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*([=<>!~]=?\s*[\w.*]+)?", line)
            if m and not line.strip().startswith(("#", "-")):
                deps[m.group(1)] = (m.group(2) or "").strip() or "(unpinned)"
    ppt = root / "pyproject.toml"
    if ppt.exists():
        try:
            data = tomllib.loads(ppt.read_text(encoding="utf-8"))
            for d in data.get("project", {}).get("dependencies", []):
                m = re.match(r"([A-Za-z0-9_.\-]+)\s*(.*)", d)
                if m:
                    deps[m.group(1)] = m.group(2) or "(unpinned)"
        except (tomllib.TOMLDecodeError, OSError):
            pass
    return {"runtime": deps, "development": {}}


def _pinned_ratio(deps: dict) -> float | None:
    versions = [v for v in deps.values() if isinstance(v, str) and v]
    if not versions:
        return None
    exact = sum(1 for v in versions if re.match(r"^v?\d+(\.\d+)*$", v.strip()))
    return round(exact / len(versions), 3)


# ---------- 依赖图 ----------

def _graph_madge(root: Path) -> dict | None:
    """JS/TS 模块级依赖图（madge，需 node 环境）"""
    exe = shutil.which("madge") or (shutil.which("npx") and "npx")
    if not exe:
        return None
    cmd = ([exe, "--json", str(root)] if exe.endswith("madge")
           else [exe, "-y", "madge", "--json", str(root)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, cwd=str(root))
        if proc.returncode != 0:
            return None
        raw = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None
    nodes = sorted(raw.keys())
    edges = [{"source": k, "target": t} for k, v in raw.items() for t in v]
    if not nodes:
        return None
    return {"tool": "madge", "nodes": [{"id": n} for n in nodes], "edges": edges}


def _graph_go(root: Path) -> dict | None:
    if not shutil.which("go") or not (root / "go.mod").exists():
        return None
    try:
        proc = subprocess.run(["go", "mod", "graph"], capture_output=True, text=True,
                              timeout=120, cwd=str(root))
        if proc.returncode != 0:
            return None
    except (subprocess.TimeoutExpired, OSError):
        return None
    mod_name = ""
    gomod = (root / "go.mod").read_text(errors="replace")
    m = re.match(r"module\s+(\S+)", gomod)
    if m:
        mod_name = m.group(1)
    # 仅保留主模块的直接依赖边（模块级视图，避免全图爆炸）
    edges = []
    nodes = {mod_name}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == mod_name:
            dep = parts[1].rsplit("@", 1)[0]
            edges.append({"source": mod_name, "target": dep})
            nodes.add(dep)
    return {"tool": "go mod graph", "nodes": [{"id": n} for n in sorted(nodes)],
            "edges": edges[:300]}


def _graph_csproj(root: Path) -> dict | None:
    projects = [p for p in root.rglob("*.csproj")
                if not any(x in p.parts for x in ("node_modules", "obj", "bin"))]
    if not projects:
        return None
    nodes, edges = [], []
    for p in projects:
        name = p.stem
        nodes.append({"id": name})
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'<ProjectReference\s+Include="([^"]+)"', text, re.I):
            target = Path(m.group(1).replace("\\", "/")).stem
            edges.append({"source": name, "target": target})
    return {"tool": "csproj ProjectReference", "nodes": nodes, "edges": edges}


def _graph_python(root: Path) -> dict | None:
    """Python 本地模块 import 图（正则启发式）"""
    modules: dict[str, set] = {}
    py_files = [p for p in iter_files(root) if p.suffix == ".py"]
    if not py_files:
        return None
    names = {p.stem for p in py_files} | {
        p.relative_to(root).parts[0] for p in py_files if len(p.relative_to(root).parts) > 1}
    for p in py_files[:2000]:
        rel = str(p.relative_to(root).with_suffix("")).replace("/", ".")
        text = p.read_text(encoding="utf-8", errors="replace")
        deps = set()
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", text, re.M):
            top = m.group(1).split(".")[0]
            if top in names:
                deps.add(top)
        modules[rel] = deps
    if not modules:
        return None
    nodes = [{"id": n} for n in sorted(modules)]
    edges = [{"source": k, "target": t} for k, v in modules.items() for t in v if t != k]
    return {"tool": "python import heuristic", "nodes": nodes[:300], "edges": edges[:600]}


@collector
class DependenciesCollector(Collector):
    name = "dependencies"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        manifests = []
        external: dict[str, dict] = {}

        for name, parser, marker in (
                ("package.json", _parse_package_json, "package.json"),
                ("go.mod", _parse_go_mod, "go.mod"),
                ("*.csproj", _parse_csproj, None),
                ("requirements.txt/pyproject.toml", _parse_python, None)):
            detected = parser(root)
            has = any(detected.values())
            if has:
                manifests.append(name)
                for kind, deps in detected.items():
                    for dep, ver in deps.items():
                        external[dep] = {"version": ver, "kind": kind, "manifest": name}

        # 依赖图：按检测到的生态依次尝试
        graph = None
        graph_note = None
        if (root / "package.json").exists():
            graph = _graph_madge(root)
            if not graph:
                graph_note = "madge/node 不可用或解析失败：JS 模块级依赖图省略（REQ §3.3 允许并标注原因）"
        if not graph and (root / "go.mod").exists():
            graph = _graph_go(root)
            if not graph:
                graph_note = "go 工具链不可用：模块依赖图省略"
        if not graph and list(root.rglob("*.csproj")):
            graph = _graph_csproj(root)
        if not graph and list(root.rglob("*.py"))[:1]:
            graph = _graph_python(root)

        all_deps = {d: v for d, v in external.items()}
        unpinned = [d for d, v in all_deps.items()
                    if isinstance(v.get("version"), str)
                    and re.match(r"^(\^|~|>=|\*|latest|\()", v["version"].strip())]

        return {
            "manifests_detected": manifests or [not_found(
                "依赖清单", "未检测到 package.json/go.mod/*.csproj/requirements.txt；"
                          "若仓库确无外部依赖可忽略本提示")],
            "external_dependencies": all_deps,
            "dependency_count": {"total": len(all_deps),
                                 "runtime": sum(1 for v in all_deps.values() if v["kind"] == "runtime"),
                                 "development": sum(1 for v in all_deps.values() if v["kind"] == "development")},
            "unpinned_versions": {"count": len(unpinned), "packages": unpinned[:50]},
            "pinned_ratio": _pinned_ratio({d: v["version"] for d, v in all_deps.items()}),
            "dependency_graph": graph if graph else {
                "found": False,
                "reason": graph_note or "未识别到可生成依赖图的生态/工具",
                "suggestion": "安装对应工具链（node+madge / go / dotnet）后重试本分析",
            },
            "health_note": "已弃用/停止维护依赖检测需查询外部 registry（REQ §2.4 方案先确认），本期未纳入",
        }
