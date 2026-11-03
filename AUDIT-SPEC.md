# 代码审计功能规格说明

## 1. 概述

### 1.1 目的

对代码仓库进行静态分析，识别代码中存在的问题和漏洞，重点关注：
- 代码规范性
- 代码安全性
- 质量属性（可靠性、健壮性、鲁棒性、兼容性、性能）
- 渗透测试（静态扫描）

### 1.2 范围

**第一期（MVP）：**
- 代码规范性检查
- 代码安全性检查
- 静态分析（不涉及运行时分析）

**后续扩展：**
- 质量属性深度分析
- 依赖漏洞扫描
- 渗透测试规则

### 1.3 目标语言（基于 augmn 组织统计）

**第一期支持：**
- **JavaScript/TypeScript** — 前端项目（Vue、React）
- **Go** — 后端微服务
- **C#** — 后端服务（.NET）

**后续扩展：**
- Dart（Flutter APP）
- Python（数据/运维脚本）
- Shell（运维脚本）

## 2. 功能需求

### 2.1 核心功能

1. **单仓库审计**
   - 对指定的单个代码仓库执行完整审计流程
   - 支持自动识别主要编程语言
   - 根据语言选择对应的分析工具
   - **支持增量审计**：只审计自上次审计后变更的文件，提升效率
   - **支持分支/标签指定**：可审计特定分支、tag 或 commit，默认审计主分支

2. **批量审计**
   - 对整个组织的所有仓库执行审计
   - 支持按仓库名模式过滤
   - 支持跳过 archived 仓库
   - **支持并行审计**：类似 sync 命令的 `-j/--jobs` 参数，可并行审计多个仓库
   - **部分失败处理**：某个仓库审计失败时，继续审计其他仓库，记录异常信息并最终输出失败列表

3. **规则管理**
   - 全局规则：适用于所有仓库的通用规则
   - 仓库级规则：针对特定仓库的定制规则（优先级高于全局）

4. **工具链管理**
   - 自动安装所需分析工具
   - 工具版本锁定，确保可复现
   - 支持本地运行和容器化运行

5. **报告生成**
   - JSON 格式（程序可解析）
   - HTML 报告（可视化展示）
   - 终端摘要（快速查看）

6. **AI 辅助**
   - 辅助生成/修改配置文件
   - 辅助解读审计结果
   - 不自动修复问题

### 2.2 审计维度

**第一期实现：**

| 维度 | 说明 | 示例 |
|------|------|------|
| 代码规范性 | 编码风格、最佳实践 | ESLint、golangci-lint |
| 代码安全性 | 安全漏洞、敏感信息泄露 | SonarQube、gosec |

**后续扩展：**

| 维度 | 说明 | 示例 |
|------|------|------|
| 可靠性 | 错误处理、边界条件 | 自定义规则 |
| 健壮性 | 异常处理、容错能力 | 自定义规则 |
| 性能 | 性能瓶颈、资源泄漏 | 静态性能分析 |
| 依赖安全 | 已知漏洞依赖 | npm audit、dependabot |

## 3. 技术设计

### 3.1 架构设计

```
org-repo-util/
├── audit/                          # 审计功能模块
│   ├── bin/                        # 可执行入口
│   │   └── audit                   # 主程序（Python/Go）
│   ├── config/                     # 配置管理
│   │   ├── global/                 # 全局规则
│   │   │   ├── rules.yaml          # 全局规则定义
│   │   │   └── toolchains.yaml     # 全局工具链配置
│   │   └── schemas/                # 配置 Schema
│   │       ├── rules.schema.yaml
│   │       └── toolchain.schema.yaml
│   ├── analyzers/                  # 分析器插件
│   │   ├── base.py                 # 分析器基类
│   │   ├── eslint/                 # ESLint 分析器
│   │   │   ├── analyzer.py
│   │   │   ├── config.yaml         # ESLint 配置模板
│   │   │   └── rules.yaml          # ESLint 规则映射
│   │   ├── golangci/               # golangci-lint 分析器
│   │   │   ├── analyzer.py
│   │   │   ├── config.yaml
│   │   │   └── rules.yaml
│   │   ├── sonarqube/              # SonarQube 分析器
│   │   │   ├── analyzer.py
│   │   │   ├── config.yaml
│   │   │   └── rules.yaml
│   │   └── ...
│   ├── reporters/                  # 报告生成器
│   │   ├── base.py                 # 报告器基类
│   │   ├── json_reporter.py        # JSON 报告
│   │   ├── html_reporter.py        # HTML 报告
│   │   └── console_reporter.py     # 终端摘要
│   ├── ai/                         # AI 辅助模块
│   │   ├── config_generator.py     # 配置生成
│   │   └── result_interpreter.py   # 结果解读
│   └── utils/                      # 工具函数
│       ├── language_detector.py    # 语言检测
│       ├── tool_installer.py       # 工具安装
│       └── repo_scanner.py         # 仓库扫描
└── repos/                          # 已克隆的仓库
    └── augmn/
        └── <repo>/
            └── .audit-config.yaml  # 仓库级规则（可选）
```

### 3.2 配置文件设计

#### 3.2.1 全局规则 (`audit/config/global/rules.yaml`)

```yaml
# 全局审计规则
version: "1.0"

# 通用配置
general:
  # 严重级别定义
  severity_levels:
    - critical    # 严重：必须立即修复
    - high        # 高：尽快修复
    - medium      # 中：计划修复
    - low         # 低：建议修复
    - info        # 信息：仅供参考
  
  # 默认排除的文件/目录
  exclude_patterns:
    - "node_modules/"
    - "vendor/"
    - "dist/"
    - "build/"
    - ".git/"
    - "*.min.js"
    - "*.min.css"
  
  # 审计维度开关
  dimensions:
    code_style: true        # 代码规范性
    security: true          # 代码安全性
    reliability: false      # 可靠性（后续扩展）
    performance: false      # 性能（后续扩展）

# 语言特定规则
languages:
  javascript:
    enabled: true
    primary_tools:
      - eslint
    file_patterns:
      - "*.js"
      - "*.jsx"
      - "*.ts"
      - "*.tsx"
      - "*.vue"
    
    # ESLint 规则配置
    tools:
      eslint:
        enabled: true
        config_override: null  # 如果 repo 有 .eslintrc，使用 repo 的
        rules:
          # 代码规范性
          no-unused-vars: error
          no-console: warn
          eqeqeq: error
          
          # 安全性
          no-eval: error
          no-implied-eval: error
          no-new-func: error
  
  go:
    enabled: true
    primary_tools:
      - golangci-lint
    file_patterns:
      - "*.go"
    
    tools:
      golangci-lint:
        enabled: true
        linters:
          enable:
            - govet        # 代码正确性
            - errcheck     # 错误检查
            - staticcheck  # 静态分析
            - gosimple     # 代码简化
            - gosec        # 安全检查
          disable: []
        
        # 严重级别映射
        severity_mapping:
          gosec: high
          errcheck: medium
  
  csharp:
    enabled: true
    primary_tools:
      - sonarqube
    file_patterns:
      - "*.cs"
    
    tools:
      sonarqube:
        enabled: true
        # SonarQube 配置
        project_key: auto  # 自动生成
        quality_profile: "Default"
```

#### 3.2.2 仓库级规则 (`<repo>/.audit-config.yaml`)

```yaml
# 仓库级审计配置（优先级高于全局）
version: "1.0"

# 继承全局规则
inherit: global

# 覆盖全局配置
overrides:
  general:
    exclude_patterns:
      - "generated/"      # 额外排除
  
  languages:
    javascript:
      tools:
        eslint:
          rules:
            no-console: off  # 覆盖全局规则
            custom-rule: error

# 仓库特定工具配置
tools:
  eslint:
    # 配置优先级：仓库自带配置 > .audit-config.yaml > 全局配置
    # 如果仓库有 .eslintrc.js，优先使用仓库的
    config_file: ".eslintrc.js"  # 指定配置文件
    use_repo_config: true  # 默认 true，优先使用仓库自带的配置

# 额外启用的分析器
additional_analyzers:
  - custom-security-scanner
```

**工具配置优先级说明：**
1. **仓库自带的工具配置**（如 `.eslintrc.js`、`.golangci.yml`）— 最高优先级
2. **仓库级 `.audit-config.yaml`** — 次优先级
3. **全局 `audit/config/global/rules.yaml`** — 最低优先级

如果仓库已有工具配置文件，默认使用仓库的配置，除非 `.audit-config.yaml` 中明确设置 `use_repo_config: false`。

#### 3.2.3 工具链配置 (`audit/config/global/toolchains.yaml`)

```yaml
# 全局工具链配置
version: "1.0"

# 工具定义
tools:
  eslint:
    version: "8.56.0"
    install_method: npm
    install_command: "npm install -g eslint@{version}"
    runtime: node
    runtime_version: ">=18.0.0"
    
    # 运行方式
    execution:
      mode: local  # local | docker | hybrid
      command: "eslint --format json {files}"
      working_dir: "{repo_root}"
  
  golangci-lint:
    version: "1.55.2"
    install_method: binary
    install_command: "curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(go env GOPATH)/bin v{version}"
    runtime: go
    runtime_version: ">=1.21.0"
    
    execution:
      mode: local
      command: "golangci-lint run --out-format json"
      working_dir: "{repo_root}"
  
  sonarqube:
    version: "community"
    install_method: docker
    docker_image: "sonarqube:community"
    
    execution:
      mode: docker
      docker_config:
        image: "sonarqube:community"
        ports:
          - "9000:9000"
        volumes:
          - "{repo_root}:/usr/src"
      command: "sonar-scanner"

# 运行时环境
runtimes:
  node:
    version: "20.10.0"
    install_method: nvm
  go:
    version: "1.21.5"
    install_method: binary
  python:
    version: "3.11.7"
    install_method: pyenv
```

### 3.3 分析器插件设计

#### 3.3.1 分析器基类

```python
# audit/analyzers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseAnalyzer(ABC):
    """分析器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__
    
    @abstractmethod
    def check_prerequisites(self) -> bool:
        """检查工具是否已安装"""
        pass
    
    @abstractmethod
    def install(self) -> bool:
        """安装工具"""
        pass
    
    @abstractmethod
    def analyze(self, repo_path: str, files: List[str]) -> List[Dict]:
        """
        执行分析
        
        Returns:
            List of issues:
            [
                {
                    "file": "path/to/file.js",
                    "line": 10,
                    "column": 5,
                    "severity": "error",
                    "message": "Unexpected console statement",
                    "rule": "no-console",
                    "tool": "eslint"
                }
            ]
        """
        pass
    
    def get_supported_languages(self) -> List[str]:
        """返回支持的语言列表"""
        return []
    
    def get_supported_extensions(self) -> List[str]:
        """返回支持的文件扩展名"""
        return []
```

#### 3.3.2 分析器示例（ESLint）

```python
# audit/analyzers/eslint/analyzer.py
import json
import subprocess
from typing import List, Dict, Any
from ..base import BaseAnalyzer

class ESLintAnalyzer(BaseAnalyzer):
    """ESLint 分析器"""
    
    def check_prerequisites(self) -> bool:
        try:
            result = subprocess.run(
                ["eslint", "--version"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def install(self) -> bool:
        version = self.config.get("version", "8.56.0")
        cmd = f"npm install -g eslint@{version}"
        result = subprocess.run(cmd, shell=True)
        return result.returncode == 0
    
    def analyze(self, repo_path: str, files: List[str]) -> List[Dict]:
        # 构建命令
        cmd = ["eslint", "--format", "json"] + files
        
        # 执行分析
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        # 解析结果
        issues = []
        if result.stdout:
            eslint_output = json.loads(result.stdout)
            for file_result in eslint_output:
                for msg in file_result.get("messages", []):
                    issues.append({
                        "file": file_result["filePath"],
                        "line": msg.get("line", 0),
                        "column": msg.get("column", 0),
                        "severity": self._map_severity(msg.get("severity", 1)),
                        "message": msg.get("message", ""),
                        "rule": msg.get("ruleId", "unknown"),
                        "tool": "eslint"
                    })
        
        return issues
    
    def _map_severity(self, eslint_severity: int) -> str:
        mapping = {1: "warning", 2: "error"}
        return mapping.get(eslint_severity, "info")
    
    def get_supported_languages(self) -> List[str]:
        return ["javascript", "typescript"]
    
    def get_supported_extensions(self) -> List[str]:
        return [".js", ".jsx", ".ts", ".tsx", ".vue"]
```

### 3.4 报告格式与存储

#### 3.4.1 报告存储策略

**存储位置：** `reports/` 目录（与 `repos/` 同级）

**目录结构：**
```
reports/
├── augmn/                          # 按组织分组
│   ├── be-trade-center/            # 按仓库分组
│   │   ├── 2026-11-03_10-30-00/    # 按审计时间戳分组
│   │   │   ├── report.json         # JSON 格式报告
│   │   │   ├── report.html         # HTML 格式报告
│   │   │   └── summary.txt         # 终端摘要（可选）
│   │   ├── 2026-11-04_14-20-00/
│   │   │   └── ...
│   │   └── latest -> 2026-11-04_14-20-00  # 符号链接指向最新
│   ├── be-payment-center/
│   │   └── ...
│   └── summary.json                # 组织级别的汇总报告
└── reports.json                    # 所有审计记录的索引
```

**命名规则：**
- 时间戳格式：`YYYY-MM-DD_HH-MM-SS`
- 每个审计会话一个独立目录
- `latest` 符号链接方便快速访问最新报告

**保留策略：**
- 默认保留最近 30 天的报告
- 可通过配置调整保留天数
- 提供清理命令手动删除旧报告

#### 3.4.2 JSON 报告

```json
{
  "metadata": {
    "org": "augmn",
    "repo": "be-trade-center",
    "audit_time": "2026-11-03T10:30:00Z",
    "duration_seconds": 45,
    "analyzer_version": "1.0.0"
  },
  "summary": {
    "total_issues": 23,
    "by_severity": {
      "critical": 0,
      "high": 3,
      "medium": 12,
      "low": 8
    },
    "by_tool": {
      "golangci-lint": 23
    },
    "by_dimension": {
      "code_style": 15,
      "security": 8
    }
  },
  "issues": [
    {
      "file": "internal/service/order.go",
      "line": 45,
      "column": 10,
      "severity": "high",
      "message": "G104: Errors unhandled",
      "rule": "errcheck",
      "tool": "gosec",
      "dimension": "security",
      "suggestion": "Handle the error returned by this function call"
    }
  ],
  "files_scanned": 156,
  "lines_scanned": 12345
}
```

#### 3.4.2 HTML 报告

- 使用模板引擎生成
- 包含统计图表
- 支持按严重级别、工具、文件过滤
- 可展开查看详细问题

#### 3.4.3 终端摘要

```
🔍 Auditing: be-trade-center
   Language: Go (99.2%)
   Files: 156 | Lines: 12,345

📊 Summary:
   Total Issues: 23
   ├─ Critical: 0
   ├─ High:     3  ⚠️
   ├─ Medium:   12
   └─ Low:      8

🛠️  By Tool:
   golangci-lint: 23 issues

📁 Top Files:
   internal/service/order.go      8 issues
   internal/handler/payment.go    5 issues
   internal/repository/user.go    4 issues

✅ Audit completed in 45s
📄 Report: reports/be-trade-center-20261103.html
```

## 4. 实施计划

### 4.1 第一期（MVP）

**目标：** 支持 JavaScript/TypeScript、Go、C# 的基础审计

**任务分解：**

1. **基础框架搭建** (Week 1)
   - [ ] 项目结构初始化
   - [ ] 配置管理模块
   - [ ] 语言检测模块
   - [ ] 分析器基类设计

2. **分析器实现** (Week 2-3)
   - [ ] ESLint 分析器（JavaScript/TypeScript）
   - [ ] golangci-lint 分析器（Go）
   - [ ] SonarQube 分析器（C#）或使用 dotnet-format

3. **报告生成** (Week 3)
   - [ ] JSON 报告器
   - [ ] 终端摘要报告器
   - [ ] HTML 报告器（基础版）

4. **CLI 集成** (Week 4)
   - [ ] 命令行参数解析
   - [ ] 单仓库审计命令
   - [ ] 批量审计命令
   - [ ] 与现有 `fish src/main.fish` 集成

5. **文档与测试** (Week 4)
   - [ ] 使用文档
   - [ ] 配置示例
   - [ ] 单元测试

### 4.2 后续扩展

**第二期：**
- 依赖漏洞扫描
- 质量属性分析
- AI 辅助配置生成

**第三期：**
- 渗透测试规则
- CI/CD 集成
- 历史趋势分析

## 5. 工具选型

### 5.1 第一期工具

| 语言 | 工具 | 用途 | 安装方式 |
|------|------|------|----------|
| JavaScript/TypeScript | ESLint | 代码规范 + 安全 | npm |
| Go | golangci-lint | 代码规范 + 安全 | binary |
| C# | SonarQube Scanner | 代码规范 + 安全 | docker |

**备选方案（C#）：**
- dotnet-format（官方工具，轻量）
- Roslyn analyzers（自定义规则）

### 5.2 后续扩展工具

| 用途 | 工具 | 说明 |
|------|------|------|
| 依赖扫描 | npm audit, Snyk | 已知漏洞 |
| 密钥检测 | git-secrets, trufflehog | 敏感信息 |
| 通用 SAST | Semgrep | 多语言支持 |

## 6. 使用示例

### 6.1 命令行使用

```bash
# 审计单个仓库
./audit/bin/audit repo repos/augmn/be-trade-center

# 审计整个组织
./audit/bin/audit org augmn

# 指定输出格式
./audit/bin/audit repo repos/augmn/be-trade-center --format html --output report.html

# 只审计特定语言
./audit/bin/audit org augmn --language go

# 跳过 archived 仓库
./audit/bin/audit org augmn --skip-archived
```

### 6.2 配置文件示例

**全局规则 (`audit/config/global/rules.yaml`):**
```yaml
version: "1.0"
general:
  severity_levels: [critical, high, medium, low, info]
  exclude_patterns:
    - "node_modules/"
    - "vendor/"
  dimensions:
    code_style: true
    security: true

languages:
  go:
    enabled: true
    tools:
      golangci-lint:
        enabled: true
        linters:
          enable: [govet, errcheck, staticcheck, gosec]
```

**仓库级规则 (`repos/augmn/be-trade-center/.audit-config.yaml`):**
```yaml
version: "1.0"
inherit: global
overrides:
  general:
    exclude_patterns:
      - "generated/"
```

## 7. 技术栈

**实现语言：** Python 3.11+

**理由：**
- 丰富的生态（分析工具、报告生成）
- 易于集成各种 CLI 工具
- AI API 集成方便

**依赖：**
- `pyyaml` — 配置解析
- `jinja2` — HTML 报告模板
- `click` — CLI 框架
- `requests` — AI API 调用
- `rich` — 终端美化

**AI 集成：**
- Claude API（主选）
- OpenAI API（备选）

## 8. 风险与挑战

### 8.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 工具安装失败 | 无法执行分析 | 提供手动安装指南；支持容器化运行 |
| 分析结果误报 | 降低可信度 | 支持规则配置；AI 辅助筛选 |
| 大型仓库性能 | 审计时间长 | 支持增量审计；并行处理 |

### 8.2 运营风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 规则过于严格 | 开发阻力 | 分阶段引入；提供修复建议 |
| 维护成本 | 持续投入 | 模块化设计；易于扩展 |

## 9. 成功标准

- [ ] 能成功审计 augmn 组织中 80% 的活跃仓库
- [ ] 误报率 < 20%
- [ ] 单仓库审计时间 < 5 分钟
- [ ] 生成的报告清晰可读，包含修复建议

## 10. 附录

### 10.1 参考资料

- [ESLint 规则文档](https://eslint.org/docs/rules/)
- [golangci-lint 文档](https://golangci-lint.run/)
- [SonarQube 文档](https://docs.sonarqube.org/)
- [OWASP 代码审计指南](https://owasp.org/www-project-code-review-guide/)

### 10.2 术语表

- **SAST**: Static Application Security Testing（静态应用安全测试）
- **Linter**: 代码风格检查工具
- **Severity**: 问题严重级别
- **False Positive**: 误报（工具报告的问题实际不存在）

## 11. 待确认问题

> 以下问题需要在后续迭代中确认，当前按默认假设推进。

### 11.1 审计范围与触发

**增量审计：**
- [ ] 如何检测文件变更？（基于 git diff？文件修改时间？）
- [ ] 增量审计时，配置文件变更是否需要触发全量审计？
- [ ] 增量审计结果如何与历史结果合并？

**分支/标签支持：**
- [ ] 审计非主分支时，是否需要与主分支结果对比？
- [ ] 是否需要支持审计多个分支？

**Monorepo 处理：**
- [ ] 如何识别 monorepo？（检测多个 package.json？多个 go.mod？）
- [ ] monorepo 的子项目是否需要独立配置？

### 11.2 语言检测策略

**多语言混合：**
- [ ] 多种语言比例相近时，是都审计还是只审计比例最高的？
- [ ] 是否需要设置语言比例阈值？（如 < 10% 的语言跳过）

**配置优先：**
- [ ] 如果 `.audit-config.yaml` 明确指定了语言，是否优先使用配置而非自动检测？（建议：是）

**生成代码：**
- [ ] 如何自动识别生成的代码？（文件名模式？文件头注释？）
- [ ] 是否需要提供配置项让用户指定生成代码的目录？

### 11.3 工具链管理

**安装缓存：**
- [ ] 工具安装后是否需要缓存？（建议：是，避免重复安装）
- [ ] 缓存目录在哪里？（`~/.audit-cache/`？`audit/.cache/`？）

**版本升级：**
- [ ] 工具版本如何升级？手动修改配置文件还是自动检测新版本？
- [ ] 是否需要锁定文件（类似 `package-lock.json`）？

**离线环境：**
- [ ] 是否需要支持离线环境下的工具安装？（预下载工具包）

### 11.4 结果处理

**误报处理：**
- [ ] 是否需要支持标记某些问题为"误报"或"已接受风险"？（当前：暂不需要）
- [ ] 如果后续需要，如何存储误报标记？

**结果对比：**
- [ ] 是否需要与上次审计结果对比，显示新增/已修复的问题？
- [ ] 对比时如何处理文件路径变更？

**问题聚合：**
- [ ] 相同规则的多个问题是否需要聚合显示？（如"10 处未处理的错误"）

### 11.5 错误处理与恢复

**断点续传：**
- [ ] 长时间审计中断后，是否支持从断点继续？
- [ ] 如何记录审计进度？

**超时控制：**
- [ ] 单个仓库审计是否需要超时限制？（建议：是，默认 10 分钟）
- [ ] 超时后是否生成部分报告？

### 11.6 性能优化

**大文件处理：**
- [ ] 超大文件（如 > 10MB）是否需要特殊处理？跳过还是分块？
- [ ] 是否需要配置文件大小阈值？

**文件数量限制：**
- [ ] 是否需要限制单次审计的文件数量？（防止内存溢出）

### 11.7 与现有工作流集成

**Git Hooks：**
- [ ] 是否支持 pre-commit hook，在提交前自动审计？
- [ ] Hook 审计范围？（仅变更文件？全量？）

**Issue Tracker：**
- [ ] 是否需要将审计发现的问题自动创建为 GitHub Issues？
- [ ] 如何避免重复创建？

### 11.8 合规与治理

**合规检查：**
- [ ] 是否需要检查开源许可证合规性？
- [ ] 是否需要检查依赖是否符合公司政策？

**审计日志：**
- [ ] 是否需要记录谁在什么时候执行了审计？
- [ ] 审计日志存储在哪里？

### 11.9 团队协作

**多用户支持：**
- [ ] 团队成员是否可以有不同的配置偏好？
- [ ] 配置如何共享？

**审计指标：**
- [ ] 是否需要生成团队级别的审计指标？（如"本月修复了 50 个问题"）

### 11.10 高级功能

**自定义规则：**
- [ ] 是否需要支持用 YAML 定义简单的自定义规则？（不写代码）

**规则市场：**
- [ ] 是否需要从社区导入规则包？

**AI 自动修复：**
- [ ] 是否需要预留 AI 自动修复接口？（第一期不做）

**漏洞情报：**
- [ ] 是否需要集成 CVE 数据库，实时推送新发现的漏洞？

### 11.11 边界情况

**空仓库：**
- [ ] 如何处理空仓库或没有代码的仓库？（建议：跳过并记录）

**符号链接：**
- [ ] 如何处理符号链接？跟随还是跳过？（建议：跳过，防止循环）

**文件编码：**
- [ ] 如何处理非 UTF-8 编码的文件？（建议：跳过并记录警告）

**二进制文件：**
- [ ] 如何识别并跳过二进制文件？（建议：基于文件扩展名和 magic number）

**权限问题：**
- [ ] 如果某些文件没有读取权限，如何处理？（建议：跳过并记录警告）

### 11.12 安全考虑

**工具供应链安全：**
- [ ] 如何确保安装的工具没有被篡改？（校验 checksum）
- [ ] 是否需要维护工具 checksum 数据库？

**审计工具本身的安全：**
- [ ] 审计工具是否会泄露代码？（特别是使用在线服务时）
- [ ] 是否需要禁用所有网络请求？

**凭证处理：**
- [ ] 如果代码中包含硬编码的凭证，报告中如何脱敏？
- [ ] 是否需要集成凭证扫描工具？

**沙箱执行：**
- [ ] 是否需要在沙箱中运行分析工具？（防止恶意代码）

### 11.13 测试策略

**测试仓库集：**
- [ ] 是否需要维护一组测试仓库，用于验证审计功能？
- [ ] 测试仓库如何维护？

**回归测试：**
- [ ] 如何确保新规则不会破坏旧功能？

**性能基准：**
- [ ] 是否需要建立性能基准，监控审计时间？

---

**最后更新：** 2026-11-03  
**状态：** 第一期需求已确认，待确认问题将在实施过程中逐步明确

