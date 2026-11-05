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


# ---------- M7 扩展：Dart / Java / Ruby ----------

def _parse_pubspec(root: Path) -> dict:
    """Dart/Flutter pubspec.yaml"""
    p = root / "pubspec.yaml"
    if not p.exists():
        return {"runtime": {}, "development": {}}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception:
        return {"runtime": {}, "development": {}}
    def _norm(d):
        out = {}
        for name, spec in (d or {}).items():
            if isinstance(spec, dict):
                out[name] = spec.get("version") or "(source-ref)"
            else:
                out[name] = str(spec) if spec else "(any)"
        return out
    return {"runtime": _norm(data.get("dependencies")),
            "development": _norm(data.get("dev_dependencies"))}


def _parse_pom(root: Path) -> dict:
    """Java Maven pom.xml（含 modules 的 dependency 段；属性引用版本标注）"""
    deps = {}
    poms = [root / "pom.xml"] + [p for p in root.glob("*/pom.xml") if p != root / "pom.xml"]
    for pom in poms[:10]:
        if not pom.exists():
            continue
        text = pom.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
                r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>"
                r"(?:\s*<version>([^<]+)</version>)?", text, re.S):
            gid, aid, ver = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip()
            key = f"{gid}:{aid}"
            deps[key] = ver if ver and not ver.startswith("$") else "(property-ref)"
    return {"runtime": deps, "development": {}}


def _parse_gradle(root: Path) -> dict:
    """Java/Kotlin Gradle build 文件（implementation/api/testImplementation 声明）"""
    deps, dev = {}, {}
    files = list(root.glob("build.gradle*")) + list(root.glob("*/build.gradle*"))
    pat = re.compile(
        r"(implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly)"
        r"[\s(]+['\"]([\w.\-]+):([\w.\-]+):([\w.\-+${}]+)['\"]")
    for f in files[:10]:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(text):
            kind, gid, aid, ver = m.groups()
            key = f"{gid}:{aid}"
            ver_clean = ver if not ver.startswith("$") else "(property-ref)"
            (dev if "test" in kind.lower() else deps)[key] = ver_clean
    return {"runtime": deps, "development": dev}


def _parse_gemfile(root: Path) -> dict:
    """Ruby Gemfile（声明）+ Gemfile.lock（精确版本优先，OSV 可查）"""
    deps = {}
    lock = root / "Gemfile.lock"
    if lock.exists():
        text = lock.read_text(encoding="utf-8", errors="replace")
        in_specs = False
        for line in text.splitlines():
            if line.strip() == "specs:":
                in_specs = True
                continue
            if in_specs:
                m = re.match(r"^ {4}(\S+) \(([\d.]+[\w.]*)\)", line)
                if m:
                    deps[m.group(1)] = m.group(2)
                elif line.strip() and not line.startswith("    "):
                    in_specs = False
    gemfile = root / "Gemfile"
    if gemfile.exists() and not deps:
        for m in re.finditer(r"gem\s+['\"]([\w.\-]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?",
                             gemfile.read_text(encoding="utf-8", errors="replace")):
            deps[m.group(1)] = m.group(2) or "(unpinned)"
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


def _graph_dart(root: Path) -> dict | None:
    """Dart 包级依赖图：pubspec name → import 'package:x/...'"""
    pubspec = root / "pubspec.yaml"
    if not pubspec.exists():
        return None
    try:
        import yaml
        self_name = (yaml.safe_load(pubspec.read_text(errors="replace")) or {}).get("name")
    except Exception:
        self_name = None
    if not self_name:
        return None
    imports: set[str] = set()
    count = 0
    for p in root.rglob("*.dart"):
        if any(x in p.parts for x in (".git", "build", ".dart_tool")):
            continue
        count += 1
        if count > 1500:
            break
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"import\s+'package:([\w_]+)/", text):
            if m.group(1) != self_name:
                imports.add(m.group(1))
    nodes = [{"id": self_name}] + [{"id": i} for i in sorted(imports)]
    edges = [{"source": self_name, "target": i} for i in sorted(imports)]
    return {"tool": "pubspec + package import", "nodes": nodes, "edges": edges}


def _graph_shell(root: Path) -> dict | None:
    """Shell source/. 调用图（脚本级）"""
    scripts = [p for p in root.rglob("*.sh")
               if not any(x in p.parts for x in ("node_modules", ".git", "vendor"))][:300]
    if len(scripts) < 2:
        return None
    nodes, edges = [], []
    names = {p.name for p in scripts}
    for p in scripts:
        rel = str(p.relative_to(root))
        nodes.append({"id": rel})
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"^\s*(?:source|\.)\s+[\"']?([^\s\"';#]+)", text, re.M):
            target = m.group(1).split("/")[-1].replace("$", "")
            for cand in names:
                if cand.endswith(target) or target.endswith(cand):
                    tgt_rel = str(next(p2 for p2 in scripts if p2.name == cand).relative_to(root))
                    if tgt_rel != rel:
                        edges.append({"source": rel, "target": tgt_rel})
                    break
    if not edges:
        return {"tool": "shell source graph", "nodes": nodes[:100], "edges": [],
                "note": "未检测到脚本间 source 调用（独立脚本集）"}
    return {"tool": "shell source graph", "nodes": nodes[:150], "edges": edges[:300]}


def _graph_java(root: Path) -> dict | None:
    """Java Maven 多模块图（parent → modules）"""
    pom = root / "pom.xml"
    if not pom.exists():
        return None
    text = pom.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<artifactId>([^<]+)</artifactId>", text)
    parent = m.group(1).strip() if m else "parent"
    modules = re.findall(r"<module>([^<]+)</module>", text)
    if not modules:
        return None
    nodes = [{"id": parent}] + [{"id": mod.strip()} for mod in modules]
    edges = [{"source": parent, "target": mod.strip()} for mod in modules]
    return {"tool": "maven modules", "nodes": nodes, "edges": edges}


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

        for name, parser in (
                ("package.json", _parse_package_json),
                ("go.mod", _parse_go_mod),
                ("*.csproj", _parse_csproj),
                ("requirements.txt/pyproject.toml", _parse_python),
                ("pubspec.yaml", _parse_pubspec),
                ("pom.xml", _parse_pom),
                ("build.gradle", _parse_gradle),
                ("Gemfile.lock", _parse_gemfile)):
            detected = parser(root)
            has = any(detected.values())
            if has:
                manifests.append(name)
                for kind, deps in detected.items():
                    for dep, ver in deps.items():
                        external[dep] = {"version": ver, "kind": kind, "manifest": name}

        # 依赖图：按检测到的生态依次尝试（M7 扩展 Dart/Java/Shell）
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
        if not graph and list(root.rglob("*.csproj"))[:1]:
            graph = _graph_csproj(root)
        if not graph and (root / "pubspec.yaml").exists():
            graph = _graph_dart(root)
        if not graph and (root / "pom.xml").exists():
            graph = _graph_java(root)
        if not graph and next(root.rglob("*.py"), None):
            graph = _graph_python(root)
        if not graph and next(root.rglob("*.sh"), None):
            graph = _graph_shell(root)

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
