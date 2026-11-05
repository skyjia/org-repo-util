"""collect.security — 安全性分析（REQ §3.5）

audit 桥接 + OSV 查询式漏洞匹配（纯 HTTP，不执行代码）+ 危险模式静态启发式。
OSV 不可达 → 降级标注（REQ 第 7 章）。
"""

from __future__ import annotations

import re
from pathlib import Path

from analysis.collectors.audit_bridge import load_audit_report, split_issues_by_dimension, summarize_issues
from analysis.collectors.base import (
    Collector, collector, is_test_path, iter_files, not_found, read_lines,
)

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_MAX_QUERIES = 200

# manifest → OSV 生态（M7 扩展：Pub/Maven/RubyGems）
OSV_ECOSYSTEM_BY_MANIFEST = {
    "package.json": "npm",
    "package-lock.json": "npm",
    "go.mod": "Go",
    "*.csproj": "NuGet",
    "packages.lock.json": "NuGet",
    "requirements.txt/pyproject.toml": "PyPI",
    "uv.lock": "PyPI",
    "poetry.lock": "PyPI",
    "pubspec.yaml": "Pub",
    "pom.xml": "Maven",
    "build.gradle": "Maven",
    "Gemfile": "RubyGems",
    "Gemfile.lock": "RubyGems",
}

# (名称, 正则, 严重度, 适用扩展名集合, 说明)
DANGER_PATTERNS = [
    ("private_key_material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
     "critical", None, "私钥材料入库"),
    ("hardcoded_secret", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|passwd|password|token)\b\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
     "high", None, "疑似硬编码凭据（需人工复核：可能是示例/测试值）"),
    ("dangerous_eval", re.compile(r"\beval\s*\("), "high",
     {".js", ".jsx", ".ts", ".tsx", ".py", ".rb", ".php"}, "动态代码执行"),
    ("py_os_system", re.compile(r"\bos\.system\s*\("), "high", {".py"}, "shell 命令执行"),
    ("py_subprocess_shell", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), "high",
     {".py"}, "shell=True 注入风险"),
    ("py_pickle", re.compile(r"\bpickle\.loads?\s*\("), "high", {".py"}, "反序列化风险"),
    ("js_shell_exec", re.compile(r"(child_process[^\n]*\bexec(Sync)?\s*\()|(\bexecSync\s*\()"),
     "high", {".js", ".jsx", ".ts", ".tsx"}, "shell 命令执行"),
    ("js_inner_html", re.compile(r"\.innerHTML\s*=[^=]"), "medium",
     {".js", ".jsx", ".ts", ".tsx", ".vue"}, "XSS 风险（innerHTML 赋值）"),
    ("js_dangerous_html", re.compile(r"dangerouslySetInnerHTML"), "medium",
     {".jsx", ".tsx"}, "XSS 风险（React dangerouslySetInnerHTML）"),
    ("go_text_template", re.compile(r'"text/template"'), "medium", {".go"},
     "未转义模板（应使用 html/template）"),
    ("go_exec_command", re.compile(r"exec\.Command(Context)?\s*\([^)]*\+"), "high", {".go"},
     "命令拼接注入风险"),
    ("cs_sql_concat", re.compile(r"(FromSqlRaw|ExecuteSqlRaw|CommandText)\s*[=(][^\n]*\"\s*\+"),
     "high", {".cs"}, "SQL 拼接注入风险"),
    ("sql_select_no_limit", re.compile(r"(?i)select\s+.+\s+from\s+(?!.*\blimit\b)[\w`\"]+\s*[\"';)]"),
     "low", {".py", ".js", ".ts", ".go", ".cs", ".java"}, "SELECT 无 LIMIT（潜在全表拉取）"),
    ("weak_hash", re.compile(r"\b(?:md5|sha1)\s*\("), "low", None,
     "弱哈希（若用于口令存储应升级 bcrypt/argon2）"),
    # ---- M7 多语言扩展 ----
    ("py_yaml_unsafe_load", re.compile(r"yaml\.load\s*\((?![^)]*Loader\s*=)"), "high", {".py"},
     "yaml.load 未指定安全 Loader（反序列化 RCE 风险，应用 safe_load）"),
    ("py_ssl_verify_disabled", re.compile(r"verify\s*=\s*False"), "medium", {".py"},
     "禁用 SSL 证书校验"),
    ("py_ssti_risk", re.compile(r"render_template_string\s*\(|jinja2\.Template\s*\("), "high", {".py"},
     "动态模板渲染（SSTI 风险，确认模板源非用户输入）"),
    ("shell_eval", re.compile(r"^\s*eval\s+[\"'$]"), "high", {".sh", ".bash"},
     "shell eval 动态执行"),
    ("shell_curl_pipe_exec", re.compile(r"(curl|wget)\s[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh"),
     "critical", {".sh", ".bash", ".md"}, "远程脚本直接管道执行（curl|bash）"),
    ("shell_rm_unquoted_var", re.compile(r"rm\s+(-[rf]+\s+)+[^\"']*\$\{?\w"), "high", {".sh", ".bash"},
     "rm -rf 使用未引号变量（变量为空时展开风险）"),
    ("shell_chmod_777", re.compile(r"chmod\s+(-R\s+)?777"), "medium", {".sh", ".bash"},
     "chmod 777（过宽权限）"),
    ("dart_process_run", re.compile(r"Process\.(run|start|runSync)\s*\("), "high", {".dart"},
     "进程执行（确认参数非用户可控）"),
    ("dart_mirrors", re.compile(r"import\s+'dart:mirrors'"), "medium", {".dart"},
     "dart:mirrors 动态反射"),
    ("java_runtime_exec", re.compile(r"Runtime\.getRuntime\(\)\s*\.exec\s*\(|new\s+ProcessBuilder\s*\("),
     "high", {".java"}, "命令执行（确认参数非用户可控）"),
    ("java_deserialization", re.compile(r"new\s+ObjectInputStream\s*\("), "high", {".java"},
     "Java 原生反序列化（RCE 风险，避免不可信数据）"),
    ("java_sql_concat", re.compile(r"(createStatement\(\)|executeQuery|executeUpdate)\s*\([^)]*\"\s*\+"),
     "high", {".java"}, "SQL 字符串拼接（注入风险，应用 PreparedStatement）"),
    ("ruby_eval", re.compile(r"\b(eval|instance_eval|class_eval|module_eval)\s*[\(\"']"), "high", {".rb"},
     "Ruby 动态执行"),
    ("ruby_marshal_load", re.compile(r"Marshal\.load\s*\("), "high", {".rb"},
     "Marshal 反序列化（RCE 风险）"),
    ("ruby_system_interp", re.compile(r"\b(system|exec|%x)\s*[\(\"'].*#\{"), "medium", {".rb"},
     "命令字符串插值（注入风险）"),
]

MAX_HITS_PER_PATTERN = 100


def _osv_query(deps: dict[str, dict]) -> dict:
    """OSV querybatch：仅精确版本（REQ §3.5 查询式匹配）；生态映射见 OSV_ECOSYSTEM_BY_MANIFEST"""
    queries = []
    meta = []
    for name, info in deps.items():
        ver = str(info.get("version", "")).strip()
        eco = OSV_ECOSYSTEM_BY_MANIFEST.get(info.get("manifest", ""))
        if not eco or not re.match(r"^v?\d+\.\d+", ver):
            continue  # 范围版本/未知生态跳过
        queries.append({"package": {"name": name.lstrip("v") if eco == "Go" else name,
                                    "ecosystem": eco},
                        "version": ver.lstrip("v") if eco == "Go" else ver})
        meta.append({"name": name, "version": ver, "ecosystem": eco})
        if len(queries) >= OSV_MAX_QUERIES:
            break
    if not queries:
        return not_found("依赖漏洞匹配", "manifest 中无精确版本依赖可查询（范围版本无法离线匹配）；"
                                        "建议提交 lock 文件以获得精确漏洞匹配")
    try:
        import requests
        resp = requests.post(OSV_BATCH_URL, json={"queries": queries}, timeout=45)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        return {"found": False, "degraded": True,
                "reason": f"OSV API 不可达: {type(e).__name__}: {e}",
                "suggestion": "联网恢复后重跑 collect.security 子任务（analyze retry）"}

    # querybatch 为轻量响应（仅 id/modified，无 severity）；按包聚合避免条目数误导
    affected: dict[str, dict] = {}
    total_entries = 0
    for m, res in zip(meta, results):
        for v in (res or {}).get("vulns", []) or []:
            total_entries += 1
            key = f"{m['name']}@{m['version']}"
            pkg = affected.setdefault(key, {
                "package": m["name"], "version": m["version"],
                "ecosystem": m["ecosystem"], "vuln_ids": [], "urls": []})
            pkg["vuln_ids"].append(v.get("id"))
            pkg["urls"].append(f"https://osv.dev/vulnerability/{v.get('id')}")
    return {
        "found": True,
        "queried": len(queries),
        "affected_package_count": len(affected),
        "vulnerability_entries": total_entries,
        "affected_packages": sorted(affected.values(),
                                    key=lambda p: -len(p["vuln_ids"]))[:50],
        "severity_note": "querybatch 轻量响应不含 severity 字段；精确严重度需逐条查询 "
                         "osv.dev/vulnerability/{id} 详情（后续可增强）",
        # 兼容旧字段（截断展示用）
        "vulnerable": [
            {"package": p["package"], "version": p["version"], "id": vid,
             "severity": None, "url": f"https://osv.dev/vulnerability/{vid}"}
            for p in affected.values() for vid in p["vuln_ids"][:3]
        ][:100],
    }


@collector
class SecurityCollector(Collector):
    name = "security"

    def collect(self, ctx) -> dict:
        root: Path = ctx.repo_path
        out: dict = {}

        # ---- 1. audit 安全扫描桥接 ----
        audit = load_audit_report(ctx.org, ctx.repo)
        _, sec_issues = split_issues_by_dimension(audit)
        if audit.get("found"):
            out["audit_security"] = {
                "source": "audit",
                "audit_generated_at": audit.get("audit_generated_at"),
                "staleness_note": audit.get("staleness_note"),
                **summarize_issues(sec_issues),
            }
        else:
            out["audit_security"] = not_found("audit 安全扫描结果",
                                              audit.get("suggestion", ""))

        # ---- 2. OSV 依赖漏洞（依赖 dependencies 子任务产物） ----
        deps_out = ctx.read_dependency_output("collect.dependencies") or {}
        deps = deps_out.get("external_dependencies", {})
        out["dependency_vulnerabilities"] = _osv_query(deps) if deps else not_found(
            "依赖漏洞匹配", "未采集到外部依赖清单")

        # ---- 2b. ruff bandit（S 系列）安全规则：优先复用 quality 产物，避免二次运行 ----
        quality_out = ctx.read_dependency_output("collect.quality") or {}
        bandit = ((quality_out.get("local_lint") or {}).get("ruff") or {}).get("bandit_security_rules")
        if bandit is None:
            from analysis.collectors.lint_tools import run_ruff
            ruff_res = run_ruff(root)
            bandit = (ruff_res or {}).get("bandit_security_rules")
        out["python_bandit_rules"] = bandit or not_found(
            "ruff bandit 规则结果", "非 Python 仓库或 ruff 不可用")

        # ---- 3. 危险模式静态启发式 ----
        hits_by_pattern: dict[str, list] = {}
        for path in iter_files(root):
            rel = path.relative_to(root)
            ext = path.suffix.lower()
            if ext not in {".js", ".jsx", ".ts", ".tsx", ".vue", ".py", ".go", ".cs",
                           ".java", ".rb", ".php", ".sh", ".bash", ".dart", ".kt",
                           ".yml", ".yaml", ".json",
                           ".sql", ".html", ".xml", ".conf", ".env", ".toml", ".md"}:
                continue
            lines = read_lines(path)
            if lines is None:
                continue
            applicable = [p for p in DANGER_PATTERNS
                          if p[3] is None or ext in p[3]]
            if not applicable:
                continue
            for i, line in enumerate(lines):
                if len(line) > 500:
                    continue
                for name, pat, sev, _exts, note in applicable:
                    bucket = hits_by_pattern.setdefault(name, [])
                    if len(bucket) >= MAX_HITS_PER_PATTERN:
                        continue
                    if pat.search(line):
                        bucket.append({
                            "file": str(rel), "line": i + 1, "severity": sev,
                            "note": note, "is_test_file": is_test_path(rel),
                            "evidence": line.strip()[:160],
                        })

        # 按 pattern 声明 severity 聚合全量计数（评分用，不受 sample 截断影响）
        pattern_sev = {p[0]: p[2] for p in DANGER_PATTERNS}
        sev_counter: dict[str, int] = {}
        for pname, bucket in hits_by_pattern.items():
            sev = pattern_sev.get(pname, "medium")
            sev_counter[sev] = sev_counter.get(sev, 0) + len(bucket)

        out["static_heuristics"] = {
            "boundary_note": "静态正则启发式，存在误报可能，命中项需人工复核（REQ §3.5）",
            "patterns_matched": {k: len(v) for k, v in hits_by_pattern.items()},
            "by_severity": sev_counter,
            "hits": {k: v[:20] for k, v in hits_by_pattern.items()},
        }

        # ---- 4. 安全最佳实践 checklist（轻量规则） ----
        practices = {
            "lockfile_present": any((root / f).exists() for f in
                                    ("package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                                     "go.sum", "packages.lock.json", "uv.lock",
                                     "poetry.lock", "Cargo.lock")),
            "gitignore_covers_env": False,
            "env_file_committed": any((root / f).exists() for f in
                                      (".env", ".env.local", ".env.production")),
            "no_private_key_files": not any(
                p.suffix in (".pem", ".key", ".p12", ".pfx")
                for p in root.rglob("*") if p.is_file()
                and not any(x in p.parts for x in ("node_modules", ".git", "vendor"))),
        }
        gi = root / ".gitignore"
        if gi.exists():
            text = gi.read_text(encoding="utf-8", errors="replace")
            practices["gitignore_covers_env"] = bool(re.search(r"\.env", text))
        out["best_practices"] = practices

        # ---- 5. 仓库内已有安全测试报告（REQ §2.2-4） ----
        sec_reports = [str(p.relative_to(root)) for p in root.rglob("*")
                       if p.is_file() and not any(x in p.parts for x in ("node_modules", ".git"))
                       and re.search(r"(security|pentest|audit)[-_]?(report|scan)", p.name, re.I)]
        out["existing_security_reports"] = (
            {"found": True, "files": sec_reports[:10]} if sec_reports
            else not_found("安全性测试报告",
                           "仓库中未发现安全扫描/渗透测试报告产物；建议将 SAST/DAST 报告归档入库或在 CI 中生成"))
        return out
