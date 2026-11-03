# 代码审计架构与实现设计

> 基于 AUDIT-SPEC.md 的详细设计文档，用于指导第一期 MVP 的实现。

## 1. 系统架构

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  audit repo <path>  │  audit org <name>  │  audit config ...    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Orchestrator Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Repo Scanner │  │ Job Scheduler│  │  Result Aggregator   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Services Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Config       │  │ Language     │  │  Change Detector     │  │
│  │ Manager      │  │ Detector     │  │  (增量审计)          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Tool         │  │ File         │  │  Report Generator    │  │
│  │ Installer    │  │ Collector    │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Analyzer Plugin Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ ESLint       │  │ golangci-    │  │  SonarQube /         │  │
│  │ Analyzer     │  │ lint Analyzer│  │  dotnet Analyzer     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ reports/     │  │ audit/cache/ │  │  audit/config/       │  │
│  │ (报告存储)   │  │ (工具缓存)   │  │  (规则配置)          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心模块编号

| 编号 | 模块名称 | 职责 | 优先级 |
|------|----------|------|--------|
| M01 | CLI 入口 | 命令行参数解析、命令路由 | P0 |
| M02 | 配置管理器 | 加载/合并全局和仓库级配置 | P0 |
| M03 | 仓库扫描器 | 扫描组织下的仓库列表 | P0 |
| M04 | 语言检测器 | 检测仓库主要编程语言 | P0 |
| M05 | 文件收集器 | 根据配置收集待审计文件 | P0 |
| M06 | 变更检测器 | 检测增量审计的文件变更 | P1 |
| M07 | 工具安装器 | 安装/验证分析工具 | P0 |
| M08 | 分析器基类 | 定义分析器接口 | P0 |
| M09 | ESLint 分析器 | JavaScript/TypeScript 审计 | P0 |
| M10 | golangci-lint 分析器 | Go 审计 | P0 |
| M11 | SonarQube/dotnet 分析器 | C# 审计 | P0 |
| M12 | 报告生成器基类 | 定义报告生成接口 | P0 |
| M13 | JSON 报告器 | 生成 JSON 格式报告 | P0 |
| M14 | HTML 报告器 | 生成 HTML 可视化报告 | P1 |
| M15 | 终端摘要器 | 输出终端摘要信息 | P0 |
| M16 | 任务调度器 | 并行任务调度 | P1 |
| M17 | 结果聚合器 | 聚合多仓库审计结果 | P0 |
| M18 | AI 辅助模块 | 配置生成/结果解读 | P2 |

---

## 2. 目录结构设计

```
org-repo-util/
├── audit/                              # 审计功能主目录
│   ├── README.md                       # 审计功能文档
│   ├── requirements.txt                # Python 依赖
│   │
│   ├── bin/                            # 可执行入口
│   │   └── audit                       # 主程序入口（Python 脚本）
│   │
│   ├── core/                           # 核心服务
│   │   ├── __init__.py
│   │   ├── config_manager.py           # M02: 配置管理
│   │   ├── repo_scanner.py             # M03: 仓库扫描
│   │   ├── language_detector.py        # M04: 语言检测
│   │   ├── file_collector.py           # M05: 文件收集
│   │   ├── change_detector.py          # M06: 变更检测
│   │   ├── tool_installer.py           # M07: 工具安装
│   │   ├── job_scheduler.py            # M16: 任务调度
│   │   ├── result_aggregator.py        # M17: 结果聚合
│   │   ├── report_storage.py           # 报告存储
│   │   ├── index_generator.py          # 报告索引生成
│   │   └── audit_logger.py             # 审计日志记录器
│   │
│   ├── analyzers/                      # 分析器插件
│   │   ├── __init__.py
│   │   ├── base.py                     # M08: 分析器基类
│   │   ├── registry.py                 # 分析器注册表
│   │   ├── eslint/                     # M09: ESLint 分析器
│   │   │   ├── __init__.py
│   │   │   ├── analyzer.py
│   │   │   └── config.yaml             # 默认配置
│   │   ├── golangci/                   # M10: golangci-lint 分析器
│   │   │   ├── __init__.py
│   │   │   ├── analyzer.py
│   │   │   └── config.yaml
│   │   └── dotnet/                     # M11: .NET 分析器
│   │       ├── __init__.py
│   │       ├── analyzer.py
│   │       └── config.yaml
│   │
│   ├── reporters/                      # 报告生成器
│   │   ├── __init__.py
│   │   ├── base.py                     # M12: 报告器基类
│   │   ├── json_reporter.py            # M13: JSON 报告
│   │   ├── html_reporter.py            # M14: HTML 报告
│   │   ├── console_reporter.py         # M15: 终端摘要
│   │   └── templates/                  # HTML 模板
│   │       └── report.html.j2
│   │
│   ├── ai/                             # AI 辅助模块
│   │   ├── __init__.py
│   │   ├── client.py                   # AI API 客户端
│   │   ├── config_generator.py         # M18: 配置生成
│   │   └── result_interpreter.py       # M18: 结果解读
│   │
│   ├── config/                         # 默认配置
│   │   ├── global/
│   │   │   ├── rules.yaml              # 全局规则
│   │   │   └── toolchains.yaml         # 工具链配置
│   │   └── schemas/
│   │       ├── rules.schema.yaml       # 规则 Schema
│   │       └── toolchain.schema.yaml   # 工具链 Schema
│   │
│   ├── cache/                          # 缓存目录（.gitignore）
│   │   └── tools/                      # 工具安装缓存
│   │
│   └── tests/                          # 单元测试
│       ├── __init__.py
│       ├── test_config_manager.py
│       ├── test_language_detector.py
│       ├── test_analyzers.py
│       └── fixtures/                   # 测试数据
│           └── sample_repos/
│
├── reports/                            # 审计报告存储
│   ├── index.html                      # 报告索引页
│   ├── .gitkeep
│   └── <org>/<repo>/<timestamp>/
│
├── repos/                              # 已克隆的仓库
│   └── <org>/<repo>/
│
└── src/                                # 原有功能
    ├── main.fish
    └── commands/
```

---

## 3. 功能模块详细设计

### 3.1 M01: CLI 入口

**文件：** `audit/bin/audit`

**功能点：**
- M01.1 解析命令行参数
- M01.2 路由到对应命令处理器
- M01.3 输出帮助信息
- M01.4 处理全局选项（--verbose, --debug）

**命令定义：**
```
audit repo <path> [options]           # 审计单个仓库
audit org <name> [options]            # 审计组织下所有仓库
audit config show                     # 显示当前配置
audit config validate                 # 验证配置文件
audit tools install                   # 安装所有工具
audit tools list                      # 列出已安装工具
audit reports list                    # 列出历史报告
audit reports clean [--days N]        # 清理旧报告
audit reports index                   # 生成/更新报告索引页
```

**选项定义：**
```
repo/org 命令选项：
  --format <json|html|console>        # 输出格式（默认：console）
  --output <path>                     # 输出文件路径
  --branch <name>                     # 指定分支（默认：主分支）
  --incremental                       # 增量审计
  --parallel <N>                      # 并行数量（默认：1）
  --language <lang>                   # 只审计指定语言
  --skip-archived                     # 跳过 archived 仓库
  --verbose                           # 详细输出
  --timeout <seconds>                 # 单仓库超时（默认：600）
```

**待确认：**
- [ ] CLI 使用 Click 还是 argparse？（建议：Click，更易用）
- [ ] 是否需要支持配置文件指定（--config）？

---

### 3.2 M02: 配置管理器

**文件：** `audit/core/config_manager.py`

**功能点：**
- M02.1 加载全局配置
- M02.2 加载仓库级配置
- M02.3 合并配置（仓库级覆盖全局）
- M02.4 配置验证（Schema 校验）
- M02.5 提供配置访问接口

**类设计：**
```python
class ConfigManager:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.global_config: Dict = {}
        self.repo_config: Dict = {}
        self.merged_config: Dict = {}
    
    def load_global_config(self) -> Dict:
        """加载全局配置"""
        pass
    
    def load_repo_config(self, repo_path: str) -> Dict:
        """加载仓库级配置"""
        pass
    
    def merge_config(self) -> Dict:
        """合并配置，仓库级优先"""
        pass
    
    def validate_config(self, config: Dict) -> bool:
        """验证配置是否符合 Schema"""
        pass
    
    def get(self, key: str, default=None):
        """获取配置值"""
        pass
```

**配置合并策略：**
```
1. 加载全局配置 → base_config
2. 加载仓库级配置 → repo_config
3. 深度合并：
   - repo_config 中存在的 key 覆盖 base_config
   - repo_config 中不存在的 key 保留 base_config 的值
   - 数组类型的配置（如 exclude_patterns）采用追加而非替换
```

**待确认：**
- [ ] 配置合并时，数组是追加还是替换？（建议：追加，但提供 override 选项）
- [ ] 是否需要支持环境变量覆盖配置？

---

### 3.3 M03: 仓库扫描器

**文件：** `audit/core/repo_scanner.py`

**功能点：**
- M03.1 扫描组织下所有仓库
- M03.2 按模式过滤仓库名
- M03.3 跳过 archived 仓库
- M03.4 跳过空仓库
- M03.5 返回仓库信息列表

**类设计：**
```python
class RepoScanner:
    def __init__(self, gh_client):
        self.gh_client = gh_client
    
    def scan_org(self, org: str, pattern: str = None, 
                 skip_archived: bool = True) -> List[RepoInfo]:
        """扫描组织下的仓库"""
        pass
    
    def get_local_repos(self, org: str) -> List[RepoInfo]:
        """获取本地已克隆的仓库"""
        pass

class RepoInfo:
    name: str
    full_name: str
    visibility: str  # public/private
    archived: bool
    primary_language: str
    languages: Dict[str, float]
    local_path: str
```

**依赖：** 复用现有 `scan_repos` 函数（common.fish）或通过 `gh api` 实现

---

### 3.4 M04: 语言检测器

**文件：** `audit/core/language_detector.py`

**功能点：**
- M04.1 从 GitHub API 获取语言信息
- M04.2 从本地文件系统检测语言
- M04.3 确定主要语言
- M04.4 返回语言列表及比例

**类设计：**
```python
class LanguageDetector:
    # 语言到分析器的映射
    LANGUAGE_ANALYZER_MAP = {
        'javascript': 'eslint',
        'typescript': 'eslint',
        'go': 'golangci-lint',
        'c#': 'dotnet',
    }
    
    def detect_from_api(self, repo_info: RepoInfo) -> Dict[str, float]:
        """从 GitHub API 获取语言信息"""
        pass
    
    def detect_from_files(self, repo_path: str) -> Dict[str, float]:
        """从本地文件检测语言"""
        pass
    
    def get_primary_language(self, languages: Dict[str, float]) -> str:
        """获取主要语言"""
        pass
    
    def get_analyzer_for_language(self, language: str) -> str:
        """获取语言对应的分析器"""
        pass
```

**待确认：**
- [ ] 多种语言比例相近时，是都审计还是只审计比例最高的？
- [ ] 是否需要设置语言比例阈值？（如 < 10% 跳过）

---

### 3.5 M05: 文件收集器

**文件：** `audit/core/file_collector.py`

**功能点：**
- M05.1 根据语言配置收集文件
- M05.2 应用排除规则
- M05.3 跳过二进制文件
- M05.4 跳过大文件（可配置阈值）
- M05.5 处理文件编码

**类设计：**
```python
class FileCollector:
    def __init__(self, config: Dict):
        self.config = config
        self.exclude_patterns = config.get('exclude_patterns', [])
        self.max_file_size = config.get('max_file_size', 10 * 1024 * 1024)  # 10MB
    
    def collect(self, repo_path: str, language: str) -> List[str]:
        """收集指定语言的待审计文件"""
        pass
    
    def should_exclude(self, file_path: str) -> bool:
        """判断文件是否应被排除"""
        pass
    
    def is_binary(self, file_path: str) -> bool:
        """判断是否为二进制文件"""
        pass
```

**文件扩展名映射：**
```python
EXTENSION_MAP = {
    'javascript': ['.js', '.jsx', '.mjs'],
    'typescript': ['.ts', '.tsx'],
    'vue': ['.vue'],
    'go': ['.go'],
    'c#': ['.cs'],
}
```

**待确认：**
- [ ] 大文件阈值默认多少？（建议：10MB）
- [ ] 大文件是跳过还是分块处理？

---

### 3.6 M06: 变更检测器

**文件：** `audit/core/change_detector.py`

**功能点：**
- M06.1 获取上次审计时间戳
- M06.2 检测自上次审计后的文件变更
- M06.3 支持 git diff 方式
- M06.4 支持文件修改时间方式

**类设计：**
```python
class ChangeDetector:
    def __init__(self, repo_path: str, reports_dir: str):
        self.repo_path = repo_path
        self.reports_dir = reports_dir
    
    def get_last_audit_time(self) -> Optional[datetime]:
        """获取上次审计时间"""
        pass
    
    def get_changed_files_git(self, since: datetime) -> List[str]:
        """使用 git diff 获取变更文件"""
        pass
    
    def get_changed_files_mtime(self, since: datetime) -> List[str]:
        """使用文件修改时间获取变更文件"""
        pass
    
    def get_changed_files(self, since: datetime, method: str = 'git') -> List[str]:
        """获取变更文件"""
        pass
```

**待确认：**
- [ ] 增量审计检测方法：git diff 还是文件修改时间？（建议：git diff，更准确）
- [ ] 配置文件变更是否需要触发全量审计？

---

### 3.7 M07: 工具安装器

**文件：** `audit/core/tool_installer.py`

**功能点：**
- M07.1 检查工具是否已安装
- M07.2 检查工具版本
- M07.3 安装工具到缓存目录
- M07.4 验证安装成功

**类设计：**
```python
class ToolInstaller:
    def __init__(self, cache_dir: str = 'audit/cache/tools'):
        self.cache_dir = cache_dir
        self.toolchains_config = self._load_toolchains_config()
    
    def is_installed(self, tool: str) -> bool:
        """检查工具是否已安装"""
        pass
    
    def get_version(self, tool: str) -> Optional[str]:
        """获取已安装工具的版本"""
        pass
    
    def install(self, tool: str) -> bool:
        """安装工具"""
        pass
    
    def install_all(self, tools: List[str]) -> Dict[str, bool]:
        """批量安装工具"""
        pass
    
    def _install_npm(self, tool: str, version: str) -> bool:
        """通过 npm 安装"""
        pass
    
    def _install_binary(self, tool: str, version: str) -> bool:
        """下载二进制文件"""
        pass
    
    def _install_docker(self, tool: str, image: str) -> bool:
        """拉取 Docker 镜像"""
        pass
```

**安装方式支持：**
| 方式 | 适用工具 | 说明 |
|------|----------|------|
| npm | ESLint | `npm install -g` |
| binary | golangci-lint | 下载预编译二进制 |
| docker | SonarQube | `docker pull` |

**待确认：**
- [ ] 缓存目录位置？（建议：`audit/cache/tools`，可配置）
- [ ] 是否需要校验工具 checksum？

---

### 3.8 M08: 分析器基类

**文件：** `audit/analyzers/base.py`

**功能点：**
- M08.1 定义分析器接口
- M08.2 提供通用功能（结果格式化）
- M08.3 定义 Issue 数据结构

**类设计：**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

class Severity(Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    INFO = 'info'

@dataclass
class Issue:
    file: str
    line: int
    column: int
    severity: Severity
    message: str
    rule: str
    tool: str
    dimension: str  # code_style | security
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'file': self.file,
            'line': self.line,
            'column': self.column,
            'severity': self.severity.value,
            'message': self.message,
            'rule': self.rule,
            'tool': self.tool,
            'dimension': self.dimension,
            'suggestion': self.suggestion,
        }

@dataclass
class AnalysisResult:
    repo: str
    language: str
    analyzer: str
    issues: List[Issue]
    files_scanned: int
    lines_scanned: int
    duration_seconds: float
    error: Optional[str] = None

class BaseAnalyzer(ABC):
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
    def analyze(self, repo_path: str, files: List[str]) -> AnalysisResult:
        """执行分析"""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """返回支持的语言列表"""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """返回支持的文件扩展名"""
        pass
    
    def get_name(self) -> str:
        """返回分析器名称"""
        return self.name
```

---

### 3.9 M09: ESLint 分析器

**文件：** `audit/analyzers/eslint/analyzer.py`

**功能点：**
- M09.1 检查 ESLint 是否已安装
- M09.2 执行 ESLint 分析
- M09.3 解析 JSON 输出
- M09.4 转换为统一 Issue 格式
- M09.5 支持仓库自带配置

**类设计：**
```python
class ESLintAnalyzer(BaseAnalyzer):
    def __init__(self, config: Dict):
        super().__init__(config)
        self.name = 'eslint'
    
    def check_prerequisites(self) -> bool:
        """检查 ESLint 是否已安装"""
        result = subprocess.run(
            ['eslint', '--version'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    def analyze(self, repo_path: str, files: List[str]) -> AnalysisResult:
        """执行 ESLint 分析"""
        # 检查仓库是否有 eslint 配置
        has_repo_config = self._has_repo_config(repo_path)
        use_repo_config = self.config.get('use_repo_config', True)
        
        # 构建命令
        cmd = ['eslint', '--format', 'json']
        if has_repo_config and use_repo_config:
            # 使用仓库配置
            pass
        else:
            # 使用全局配置
            config_file = self._generate_config_file()
            cmd.extend(['--config', config_file])
        
        cmd.extend(files)
        
        # 执行分析
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=self.config.get('timeout', 300)
        )
        
        # 解析结果
        issues = self._parse_output(result.stdout)
        
        return AnalysisResult(
            repo=repo_path,
            language='javascript',
            analyzer='eslint',
            issues=issues,
            files_scanned=len(files),
            lines_scanned=self._count_lines(files),
            duration_seconds=result.elapsed_time if hasattr(result, 'elapsed_time') else 0
        )
    
    def _parse_output(self, output: str) -> List[Issue]:
        """解析 ESLint JSON 输出"""
        pass
    
    def _has_repo_config(self, repo_path: str) -> bool:
        """检查仓库是否有 ESLint 配置"""
        config_files = ['.eslintrc.js', '.eslintrc.json', '.eslintrc', '.eslintrc.yml']
        return any(os.path.exists(os.path.join(repo_path, f)) for f in config_files)
    
    def get_supported_languages(self) -> List[str]:
        return ['javascript', 'typescript']
    
    def get_supported_extensions(self) -> List[str]:
        return ['.js', '.jsx', '.ts', '.tsx', '.vue', '.mjs']
```

---

### 3.10 M10: golangci-lint 分析器

**文件：** `audit/analyzers/golangci/analyzer.py`

**功能点：**
- M10.1 检查 golangci-lint 是否已安装
- M10.2 执行 golangci-lint 分析
- M10.3 解析 JSON 输出
- M10.4 转换为统一 Issue 格式

**类似 ESLint 分析器的结构，主要差异：**
- 命令：`golangci-lint run --out-format json`
- 输出格式不同
- 需要在 Go 项目根目录执行

---

### 3.11 M11: .NET 分析器

**文件：** `audit/analyzers/dotnet/analyzer.py`

**功能点：**
- M11.1 检查 dotnet 工具是否已安装
- M11.2 执行 dotnet format 或 SonarQube 分析
- M11.3 解析输出
- M11.4 转换为统一 Issue 格式

**待确认：**
- [ ] 使用 dotnet-format 还是 SonarQube？（建议：先用 dotnet-format，更轻量）
- [ ] C# 项目是否需要先 `dotnet build`？

---

### 3.12 M12-M15: 报告生成器

**文件：** `audit/reporters/`

**功能点：**
- M12.1 定义报告器接口
- M13.1 生成 JSON 报告
- M14.1 生成 HTML 报告
- M15.1 生成终端摘要

**HTML 报告增强功能（MVP 已完成）：**
- ✅ 按严重级别筛选问题（Critical/High/Medium/Low/Info/All）
- ✅ 按规则名称筛选问题（下拉选择框）
- ✅ 分页显示大量问题（每页 50/100/200 条可选）
- ✅ 多条件组合筛选（严重级别 + 规则，AND 逻辑）
- ✅ 清除筛选功能（一键重置所有条件）
- ✅ 单仓库报告移除「审计仓库」统计项，组织报告保留
- ✅ JavaScript 实时 filtering，无页面刷新
- ✅ 响应式设计，适配桌面和移动端

**类设计：**
```python
class BaseReporter(ABC):
    @abstractmethod
    def generate(self, results: List[AnalysisResult], output_path: str):
        """生成报告"""
        pass

class JsonReporter(BaseReporter):
    def generate(self, results: List[AnalysisResult], output_path: str):
        """生成 JSON 报告"""
        report = {
            'metadata': {...},
            'summary': {...},
            'issues': [...]
        }
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

class HtmlReporter(BaseReporter):
    def __init__(self):
        self.env = jinja2.Environment(...)
    
    def generate(self, results: List[AnalysisResult], output_path: str):
        """生成 HTML 报告"""
        template = self.env.get_template('report.html.j2')
        html = template.render(results=results)
        with open(output_path, 'w') as f:
            f.write(html)

class ConsoleReporter(BaseReporter):
    def generate(self, results: List[AnalysisResult], output_path: str = None):
        """输出终端摘要"""
        for result in results:
            self._print_summary(result)
```

---

### 3.13 M16: 任务调度器

**文件：** `audit/core/job_scheduler.py`

**功能点：**
- M16.1 创建任务队列
- M16.2 并行执行任务
- M16.3 收集任务结果
- M16.4 处理任务超时
- M16.5 处理任务失败

**类设计：**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

class JobScheduler:
    def __init__(self, max_workers: int = 1, timeout: int = 600):
        self.max_workers = max_workers
        self.timeout = timeout
    
    def schedule(self, tasks: List[Callable]) -> List[TaskResult]:
        """调度执行任务"""
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(task): task for task in tasks}
            for future in as_completed(futures, timeout=self.timeout):
                task = futures[future]
                try:
                    result = future.result()
                    results.append(TaskResult(task=task, result=result, success=True))
                except Exception as e:
                    results.append(TaskResult(task=task, error=str(e), success=False))
        return results
```

---

### 3.14 M17: 结果聚合器

**文件：** `audit/core/result_aggregator.py`

**功能点：**
- M17.1 聚合多个仓库的审计结果
- M17.2 生成组织级别的汇总
- M17.3 统计各维度问题数量
- M17.4 生成失败列表

**类设计：**
```python
class ResultAggregator:
    def aggregate(self, results: List[AnalysisResult]) -> AggregateResult:
        """聚合审计结果"""
        return AggregateResult(
            total_repos=len(results),
            successful_repos=len([r for r in results if not r.error]),
            failed_repos=len([r for r in results if r.error]),
            total_issues=sum(len(r.issues) for r in results),
            by_severity=self._count_by_severity(results),
            by_dimension=self._count_by_dimension(results),
            by_tool=self._count_by_tool(results),
            failed_repo_list=self._get_failed_repos(results),
        )
```

---

### 3.15 报告索引生成器

**文件：** `audit/core/index_generator.py`

**功能点：**
- 生成 `reports/index.html` 索引页
- 按组织 > 仓库 > 最新报告组织内容
- 显示仓库统计信息（语言、问题数、最后审计时间）
- 提供搜索、排序功能
- 审计后自动更新索引

**类设计：**
```python
class IndexGenerator:
    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
    
    def generate_index(self) -> str:
        """生成索引页 HTML"""
        # 1. 扫描所有报告
        reports = self._scan_all_reports()
        
        # 2. 按组织分组
        orgs = self._group_by_org(reports)
        
        # 3. 渲染 HTML
        html = self._render_index(orgs)
        
        # 4. 写入文件
        output_path = self.reports_dir / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return str(output_path)
    
    def _scan_all_reports(self) -> List[Dict]:
        """扫描所有报告并提取元数据"""
        pass
    
    def _group_by_org(self, reports: List[Dict]) -> Dict[str, List[Dict]]:
        """按组织分组报告"""
        pass
    
    def _render_index(self, orgs: Dict[str, List[Dict]]) -> str:
        """渲染索引页 HTML（使用 Jinja2）"""
        pass
```

**索引页功能：**
- **统计概览**：总仓库数、总问题数、语言分布
- **搜索框**：JavaScript 实时过滤仓库名/语言
- **排序功能**：按问题数/语言/最后审计时间排序
- **响应式设计**：适配桌面和移动端

**触发时机：**
- 执行 `audit repo --save` 或 `audit org --save` 后自动更新
- 手动执行 `audit reports index` 命令

---

## 4. 数据流设计

### 4.1 单仓库审计流程

```
┌──────────────┐
│  输入参数    │
│  repo_path   │
│  options     │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M01: CLI 入口                                                 │
│ - 解析参数                                                    │
│ - 调用 audit_single_repo()                                    │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M02: 配置管理器                                               │
│ - 加载全局配置                                                │
│ - 加载仓库级配置                                              │
│ - 合并配置                                                    │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M04: 语言检测器                                               │
│ - 检测主要语言                                                │
│ - 返回语言和比例                                              │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M06: 变更检测器（增量审计时）                                  │
│ - 获取上次审计时间                                            │
│ - 获取变更文件列表                                            │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M05: 文件收集器                                               │
│ - 根据语言收集文件                                            │
│ - 应用排除规则                                                │
│ - 返回待审计文件列表                                          │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M07: 工具安装器                                               │
│ - 检查工具是否已安装                                          │
│ - 如未安装，自动安装                                          │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M09/M10/M11: 分析器                                          │
│ - 执行分析                                                    │
│ - 返回 AnalysisResult                                         │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M12/M13/M14/M15: 报告生成器                                   │
│ - 生成 JSON/HTML/Console 报告                                 │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ 输出报告到 reports/<org>/<repo>/<timestamp>/                   │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 批量审计流程

```
┌──────────────┐
│  输入参数    │
│  org         │
│  options     │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M03: 仓库扫描器                                               │
│ - 扫描组织下所有仓库                                          │
│ - 返回仓库列表                                                │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M16: 任务调度器                                               │
│ - 创建审计任务队列                                            │
│ - 并行执行审计任务                                            │
│   - 每个任务调用单仓库审计流程                                 │
│ - 收集结果                                                    │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ M17: 结果聚合器                                               │
│ - 聚合所有仓库结果                                            │
│ - 生成组织级别汇总                                            │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ 输出报告                                                      │
│ - 每个仓库独立报告                                            │
│ - 组织汇总报告                                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 已确认设计决策

### 5.1 架构设计相关

| 编号 | 问题 | 影响范围 | 决策方案 | 状态 |
|------|------|----------|----------|------|
| D01 | CLI 框架选择：Click vs argparse？ | M01 | **Click**（更易用，生态更好） | ✅ 已确认 |
| D02 | 配置合并时数组是追加还是替换？ | M02 | **追加**，提供 override 选项 | ✅ 已确认 |
| D03 | 是否需要支持环境变量覆盖配置？ | M02 | **是**（便于 CI/CD 集成） | ✅ 已确认 |
| D04 | 多种语言比例相近时，都审计还是只审计主要语言？ | M04 | **审计所有超过阈值的语言** | ✅ 已确认 |
| D05 | 语言比例阈值设置多少？ | M04 | **10%** | ✅ 已确认 |
| D06 | 大文件阈值默认多少？ | M05 | **10MB** | ✅ 已确认 |
| D07 | 大文件是跳过还是分块处理？ | M05 | **跳过**，记录警告 | ✅ 已确认 |
| D08 | 增量审计检测方法：git diff vs 文件修改时间？ | M06 | **git diff**（更准确） | ✅ 已确认 |
| D09 | 配置文件变更是否需要触发全量审计？ | M06 | **是** | ✅ 已确认 |
| D10 | 工具缓存目录位置？ | M07 | **audit/cache/tools** | ✅ 已确认 |
| D11 | 是否需要校验工具 checksum？ | M07 | **第一期不做**（后续迭代） | ✅ 已确认 |
| D12 | C# 使用 dotnet-format 还是 SonarQube？ | M11 | **dotnet-format**（更轻量） | ✅ 已确认 |

### 5.2 实现细节相关

| 编号 | 问题 | 影响范围 | 决策方案 | 状态 |
|------|------|----------|----------|------|
| D13 | 并行执行使用多线程还是多进程？ | M16 | **多线程**（IO 密集型任务） | ✅ 已确认 |
| D14 | 单仓库超时时间默认多少？ | M16 | **600 秒** | ✅ 已确认 |
| D15 | 超时后是否生成部分报告？ | M16 | **否**，记录错误并继续 | ✅ 已确认 |
| D16 | HTML 报告是否需要交互式图表？ | M14 | **第一期不需要**（静态表格） | ✅ 已确认 |
| D17 | 报告保留天数默认多少？ | - | **30 天** | ✅ 已确认 |
| D18 | 是否需要支持报告导出（如 PDF）？ | - | **第一期不需要** | ✅ 已确认 |

### 5.3 MVP 实施总结（2026-11-03 完成）

**已完成功能：**
- ✅ CLI 完整功能（repo/org/config/tools/reports 命令）
- ✅ 三种分析器（ESLint、golangci-lint、dotnet-format）
- ✅ 三种报告格式（JSON、HTML、Console）
- ✅ 报告存储与索引（reports/<org>/<repo>/<timestamp>/ + index.html）
- ✅ 增量审计（--incremental）
- ✅ 并行审计（--parallel N）
- ✅ HTML 报告交互优化（筛选、分页、多条件组合）
- ✅ 报告索引页（搜索、排序、自动更新）

**关键实现决策：**
| 编号 | 问题 | 决策方案 | 备注 |
|------|------|----------|------|
| M01 | ESLint 配置策略 | 优先使用仓库配置，回退到最小化配置 | 避免 plugin missing 错误 |
| M02 | golangci-lint 版本兼容 | 自动检测版本并使用对应参数 | 支持 v1 和 v2 格式 |
| M03 | HTML 报告结构 | 统计卡片使用 .stats-card，仓库详情使用 .repo-card | 避免 CSS 类冲突导致 JS 崩溃 |
| M04 | 大量问题处理 | 前端分页 + 实时 filtering | 支持 10000+ 问题流畅展示 |
| M05 | 报告索引更新 | 审计后自动更新 + 手动命令 | 兼顾便利性和灵活性 |

**基准测试结果：**
| 仓库 | 语言 | 耗时 | 问题数 | 状态 |
|------|------|------|--------|------|
| fe-casamiel-admin | JavaScript | 0.69s | 207 | ✅ |
| be-casamiel-applet-mall | C# | 24.64s | 13,484 | ✅ |
| be-promotion-center | Go | 1.74s | 738 | ✅ |

**E2E 验证：**
- ✅ Playwright + Chromium 浏览器测试
- ✅ HTML 报告分页、筛选功能正常
- ✅ 报告索引页搜索、排序功能正常
- ✅ 无 JavaScript 错误

---

## 6. 技术依赖

### 6.1 Python 依赖

```
# requirements.txt
click>=8.0.0          # CLI 框架
pyyaml>=6.0           # YAML 解析
jinja2>=3.0.0         # HTML 模板
rich>=12.0.0          # 终端美化
requests>=2.28.0      # HTTP 请求（AI API）
jsonschema>=4.0.0     # 配置验证
```

### 6.2 外部工具依赖

| 工具 | 版本 | 用途 | 安装方式 |
|------|------|------|----------|
| Node.js | >=18.0.0 | ESLint 运行时 | nvm |
| ESLint | 8.56.0 | JS/TS 分析 | npm |
| Go | >=1.21.0 | golangci-lint 运行时 | binary |
| golangci-lint | 1.55.2 | Go 分析 | binary |
| dotnet SDK | 7.0+ | C# 分析 | binary |
| Git | >=2.30.0 | 增量审计 | system |

---

## 7. 审计日志功能（第二期增强 ✅）

**实现时间：** 2026-11-03  
**模块文件：** `audit/core/audit_logger.py`

### 7.1 功能概述

审计日志功能用于记录审计过程中遇到的警告和错误信息，便于问题排查和审计质量分析。

**核心特性：**
- ✅ 同时输出到控制台和文件
- ✅ 记录 WARNING 及以上级别的日志（WARNING、ERROR、CRITICAL）
- ✅ 日志文件保存在报告目录下（与 report.json 同级）
- ✅ 支持详细模式（verbose）显示更多信息

### 7.2 日志内容

**记录的事件类型：**
1. **工具安装问题**
   - 依赖安装失败（npm install、go get、dotnet restore）
   - 工具版本不兼容
   - 网络超时

2. **配置问题**
   - 缺少必要的配置文件
   - 配置文件格式错误
   - 规则冲突

3. **执行问题**
   - 分析器执行超时
   - 解析错误
   - 文件访问异常

### 7.3 日志格式

**控制台输出：**
```
WARNING: 未找到 node_modules，尝试安装依赖: repos/augmn/fe-casamiel-admin
WARNING: 依赖安装失败，跳过依赖扫描
```

**文件输出（report.log）：**
```
2026-11-03 19:24:43 - audit.execution - WARNING - 未找到 node_modules，尝试安装依赖: repos/augmn/fe-casamiel-admin
2026-11-03 19:25:45 - audit.execution - WARNING - 依赖安装失败，跳过依赖扫描
```

### 7.4 使用方式

```bash
# 执行审计并保存报告（自动生成 report.log）
audit repo <repo-path> --save

# 日志文件位置
reports/<org>/<repo>/<timestamp>/report.log
```

### 7.5 自动依赖安装（第二期增强 ✅）

**问题：** Node.js 项目未安装依赖会影响审计质量（无法加载项目特定的 ESLint 插件和规则）。

**解决方案：** 在审计前自动检测并安装项目依赖。

**实现逻辑：**
1. 检查项目是否存在 `package.json`
2. 检查 `node_modules` 目录是否存在
3. 如果不存在，执行 `npm install --legacy-peer-deps`
4. 安装成功：使用项目配置进行审计
5. 安装失败：使用回退配置进行审计，并在日志中记录警告

**支持的工具：**
- ✅ npm（Node.js）
- ✅ go mod（Go）
- ✅ dotnet restore（.NET）

---

## 8. 实施计划

### 8.1 第一期 MVP（已完成 ✅）

**完成时间：** 2026-11-03  
**任务总数：** 123 个  
**完成率：** 100%

**实现内容：**
- 基础框架搭建（CLI、配置管理、语言检测、文件收集）
- 三种分析器（ESLint、golangci-lint、dotnet-format）
- 报告系统（JSON、HTML、Console、存储、索引）
- 增强功能（增量审计、并行审计、HTML 交互优化）

**详细记录：** 见 `AUDIT-DEV-PLAN-0_mvp_completed.md`

### 8.2 第二期规划（进行中）

**目标：** 质量提升与功能扩展

**规划方向：**
- 误报率优化（规则调优、AI 辅助筛选）
- 依赖安全扫描（npm audit、dependabot 集成）
- AI 辅助功能（配置生成、结果解读）
- CI/CD 集成（GitHub Actions、GitLab CI）
- 更多语言支持（Dart、Python、Shell）

**详细计划：** 见 `AUDIT-DEV-PLAN-1.md`

### 8.3 模块实现顺序（原始规划，供参考）

| 阶段 | 模块 | 编号 | 依赖 | 说明 |
|------|------|------|------|------|
| 阶段一 | 基础框架搭建 | - | - | 项目骨架和核心服务 |
| | M01: CLI 入口 | M01.1-4 | - | 命令行接口 |
| | M02: 配置管理器 | M02.1-5 | - | 配置加载和合并 |
| | M08: 分析器基类 | M08.1-3 | - | 分析器接口定义 |
| | M04: 语言检测器 | M04.1-4 | - | 语言识别 |
| | M05: 文件收集器 | M05.1-5 | M04 | 文件筛选 |
| | M03: 仓库扫描器 | M03.1-5 | - | 仓库列表获取 |
| 阶段二 | 分析器实现 | - | 阶段一 | 三种语言的分析器 |
| | M07: 工具安装器 | M07.1-4 | - | 工具管理 |
| | M09: ESLint 分析器 | M09.1-5 | M07, M08 | JS/TS 审计 |
| | M10: golangci-lint 分析器 | M10.1-4 | M07, M08 | Go 审计 |
| | M11: .NET 分析器 | M11.1-4 | M07, M08 | C# 审计 |
| 阶段三 | 报告与集成 | - | 阶段二 | 报告生成和结果聚合 |
| | M12: 报告生成器基类 | M12.1 | - | 报告接口 |
| | M13: JSON 报告器 | M13.1 | M12 | JSON 输出 |
| | M15: 终端摘要器 | M15.1 | M12 | 终端输出 |
| | M14: HTML 报告器 | M14.1 | M12 | HTML 输出 |
| | M17: 结果聚合器 | M17.1-4 | - | 多仓库聚合 |
| | 集成测试 | - | All | 阶段验收 |
| 阶段四 | 增强功能 | - | 阶段三 | 高级特性 |
| | M06: 变更检测器 | M06.1-4 | - | 增量审计 |
| | M16: 任务调度器 | M16.1-5 | - | 并行执行 |
| | 批量审计集成 | - | M03, M16, M17 | 组织级审计 |
| | 文档编写 | - | - | 使用文档 |

### 8.4 里程碑检查点

| 里程碑 | 验收条件 | 交付物 |
|--------|----------|--------|
| M1: 框架就绪 | 阶段一所有任务完成 | 可运行的 CLI 骨架，配置管理，语言检测 |
| M2: 单语言审计 | ESLint 分析器完成并测试 | 可审计 JS/TS 项目，输出 JSON |
| M3: 全语言支持 | 三种分析器全部完成 | 支持 JS/TS、Go、C#，HTML 报告 |
| M4: MVP 完成 | 所有功能就绪，文档完整 | 增量审计、并行审计、完整文档 |

---

## 8. 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| ESLint 配置冲突 | 高 | 中 | 优先使用仓库配置，提供回退选项 |
| 工具安装失败 | 中 | 高 | 提供手动安装指南，支持 Docker 模式 |
| 大型仓库超时 | 中 | 中 | 支持增量审计，可配置超时 |
| 分析结果误报多 | 中 | 高 | 提供规则配置，AI 辅助筛选（后续） |
| 并行任务内存溢出 | 低 | 高 | 限制并行数，分批处理 |

---

**最后更新：** 2026-11-03  
**版本：** 1.2  
**状态：** MVP 已完成 ✅ (123/123 任务)，第二期规划中
