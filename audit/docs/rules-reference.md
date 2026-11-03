# 审计规则参考文档

> 自动生成于 2026-11-03 18:04:16
> 规则总数: 22

---

## 目录

- [dotnet-format](#dotnet-format)
  - [WHITESPACE](#whitespace)
  - [CA1002](#ca1002)
  - [CA2227](#ca2227)
  - [CA1062](#ca1062)
  - [CA1056](#ca1056)
  - [CA5394](#ca5394)
  - [CA5358](#ca5358)
- [eslint](#eslint)
  - [no-unused-vars](#no-unused-vars)
  - [no-undef](#no-undef)
  - [no-console](#no-console)
  - [eqeqeq](#eqeqeq)
  - [no-eval](#no-eval)
  - [no-implied-eval](#no-implied-eval)
  - [no-new-func](#no-new-func)
- [golangci-lint](#golangci-lint)
  - [govet](#govet)
  - [errcheck](#errcheck)
  - [staticcheck](#staticcheck)
  - [gosec](#gosec)
  - [gosimple](#gosimple)
  - [protogetter](#protogetter)
  - [gofmt](#gofmt)
  - [gofumpt](#gofumpt)

---

## dotnet-format

**语言:** C#

### WHITESPACE

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | INFO |
| **维度** | code_style |
| **文档** | [https://docs.microsoft.com/en-us/dotnet/core/tools/dotnet-format](https://docs.microsoft.com/en-us/dotnet/core/tools/dotnet-format) |

**说明:** 空白格式问题

**修复建议:** 运行 dotnet format 自动修复格式问题

### CA1002

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1002](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1002) |

**说明:** 不要使用泛型 List<T>

**修复建议:** 使用 Collection<T> 替代 List<T> 作为公开 API 的返回类型

### CA2227

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca2227](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca2227) |

**说明:** 集合属性应为只读

**修复建议:** 将集合属性改为只读，提供 Add/Remove 方法而非直接设置

### CA1062

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1062](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1062) |

**说明:** 验证公开方法的非空参数

**修复建议:** 在使用参数前检查是否为 null，抛出 ArgumentNullException

### CA1056

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1056](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca1056) |

**说明:** URI 属性不应为字符串

**修复建议:** 使用 System.Uri 类型替代 string 表示 URI

### CA5394

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | HIGH |
| **维度** | security |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5394](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5394) |

**说明:** 不要使用不安全的随机数生成器

**修复建议:** 使用 System.Security.Cryptography.RandomNumberGenerator 替代 System.Random

### CA5358

| 属性 | 值 |
|------|-----|
| **工具** | dotnet-format |
| **语言** | C# |
| **严重级别** | HIGH |
| **维度** | security |
| **文档** | [https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5358](https://docs.microsoft.com/en-us/visualstudio/code-quality/ca5358) |

**说明:** 审查 ECB 密码模式的使用

**修复建议:** ECB 模式不安全，使用 CBC 或 GCM 模式替代

## eslint

**语言:** JavaScript/TypeScript

### no-unused-vars

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | HIGH |
| **维度** | code_style |
| **文档** | [https://eslint.org/docs/rules/no-unused-vars](https://eslint.org/docs/rules/no-unused-vars) |

**说明:** 禁止未使用的变量

**修复建议:** 删除未使用的变量，或在变量名前加 _ 前缀表示有意忽略

### no-undef

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | HIGH |
| **维度** | code_style |
| **文档** | [https://eslint.org/docs/rules/no-undef](https://eslint.org/docs/rules/no-undef) |

**说明:** 禁止使用未声明的变量

**修复建议:** 确保变量已正确声明，或使用 typeof 检查变量是否存在

### no-console

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://eslint.org/docs/rules/no-console](https://eslint.org/docs/rules/no-console) |

**说明:** 禁止使用 console 语句

**修复建议:** 使用专业的日志库（如 winston、pino）替代 console，或在生产环境中移除

### eqeqeq

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://eslint.org/docs/rules/eqeqeq](https://eslint.org/docs/rules/eqeqeq) |

**说明:** 要求使用 === 和 !==

**修复建议:** 使用严格相等运算符 === 和 !== 替代 == 和 !=

### no-eval

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | CRITICAL |
| **维度** | security |
| **文档** | [https://eslint.org/docs/rules/no-eval](https://eslint.org/docs/rules/no-eval) |

**说明:** 禁止使用 eval()

**修复建议:** eval() 存在安全风险，使用 Function 构造函数或 JSON.parse() 替代

### no-implied-eval

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | CRITICAL |
| **维度** | security |
| **文档** | [https://eslint.org/docs/rules/no-implied-eval](https://eslint.org/docs/rules/no-implied-eval) |

**说明:** 禁止隐式 eval()

**修复建议:** 避免使用 setTimeout/setInterval 的字符串参数形式

### no-new-func

| 属性 | 值 |
|------|-----|
| **工具** | eslint |
| **语言** | JavaScript/TypeScript |
| **严重级别** | CRITICAL |
| **维度** | security |
| **文档** | [https://eslint.org/docs/rules/no-new-func](https://eslint.org/docs/rules/no-new-func) |

**说明:** 禁止使用 new Function()

**修复建议:** Function 构造函数与 eval 类似，存在安全风险

## golangci-lint

**语言:** Go

### govet

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | HIGH |
| **维度** | code_style |
| **文档** | [https://pkg.go.dev/cmd/vet](https://pkg.go.dev/cmd/vet) |

**说明:** Go vet 检查代码正确性

**修复建议:** 修复 govet 报告的问题，通常是 Printf 格式不匹配、 unreachable code 等

### errcheck

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | HIGH |
| **维度** | code_style |
| **文档** | [https://github.com/kisielk/errcheck](https://github.com/kisielk/errcheck) |

**说明:** 检查未处理的错误返回值

**修复建议:** 处理所有错误返回值，或使用 _ = 明确表示有意忽略

### staticcheck

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | HIGH |
| **维度** | code_style |
| **文档** | [https://staticcheck.io/](https://staticcheck.io/) |

**说明:** 静态分析检查

**修复建议:** 修复 staticcheck 报告的问题，包括性能、正确性、简洁性等

### gosec

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | HIGH |
| **维度** | security |
| **文档** | [https://github.com/securego/gosec](https://github.com/securego/gosec) |

**说明:** 安全漏洞检查

**修复建议:** 修复 gosec 报告的安全问题，如 SQL 注入、弱随机数等

### gosimple

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://github.com/dominikh/go-tools](https://github.com/dominikh/go-tools) |

**说明:** 代码简化建议

**修复建议:** 按照建议简化代码，如使用更简洁的语法

### protogetter

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | MEDIUM |
| **维度** | code_style |
| **文档** | [https://github.com/ghostiam/protogetter](https://github.com/ghostiam/protogetter) |

**说明:** 检查 proto 字段直接访问（应使用 getter）

**修复建议:** 使用 proto 消息的 getter 方法访问字段，而非直接访问

### gofmt

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | INFO |
| **维度** | code_style |
| **文档** | [https://pkg.go.dev/cmd/gofmt](https://pkg.go.dev/cmd/gofmt) |

**说明:** 代码格式化检查

**修复建议:** 运行 gofmt -w 自动修复格式问题

### gofumpt

| 属性 | 值 |
|------|-----|
| **工具** | golangci-lint |
| **语言** | Go |
| **严重级别** | INFO |
| **维度** | code_style |
| **文档** | [https://github.com/mvdan/gofumpt](https://github.com/mvdan/gofumpt) |

**说明:** 更严格的代码格式化

**修复建议:** 运行 gofumpt -w 自动修复格式问题
