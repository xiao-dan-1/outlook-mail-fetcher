# Outlook Mail Fetcher 模块化与并发架构设计

日期：2026-07-18

## 背景

当前项目同时提供 Web 控制台和 CLI，通过 OAuth2 与 Outlook IMAP 拉取邮件。核心功能完整，但批量流程分别散落在 Web 和 CLI 中，`imap_client.py` 同时承担协议访问与邮件内容解析，前端验证码识别逻辑缺少统一、可独立扩展的规则边界，多账号拉取仍按顺序执行。

本次重构的目标是把“高内聚、低耦合、优雅命名、轻量插件化、支持多账号并发”转化为可测试、可提交和可回归的工程结果。重构必须保持现有前端界面和 Docker 启动方式；内部 Python API、CLI 内部实现和 SQLite 实现允许调整，但应尽量保持已有用户可见行为。

## 范围与非目标

### 范围

- 拆分账号拉取、邮件解析、批量调度和持久化职责。
- 让 Web 与 CLI 复用同一个批量拉取应用服务。
- 为邮件正文解析和验证码识别建立稳定的规则接口与注册表。
- 使用有界线程池并发处理多个邮箱账号。
- 为依赖方向、规则扩展、并发隔离、结果顺序和失败行为增加测试。
- 每完成一个目标，运行与该目标匹配的测试，并创建独立 Git 提交。
- 全部目标完成后运行全量自动化测试、Docker 本地构建回归和真实 Outlook 账号回归。

### 非目标

- 不建设可安装第三方包、自动发现目录、热加载或版本协商的完整插件平台。
- 不把阻塞式 `imaplib` 和 `urllib` 全面改写为 `asyncio`。
- 不重新设计前端页面、交互流程或视觉样式。
- 不改变 `docker compose up -d` 和本地源码构建的既有使用方式。
- 不为尚不存在的邮件服务商提前实现通用多供应商框架。

## 总体架构

依赖方向固定为：

```text
Web / CLI / Docker 入口
          |
          v
   BatchFetchService
          |
          +--> AccountMailFetcher 接口
          |        |
          |        +--> OutlookAccountMailFetcher
          |                 +--> OAuth token refresh
          |                 +--> Outlook IMAP
          |                 +--> MessageParser
          |
          +--> MailRepository 接口（CLI 持久化时使用）
                   |
                   +--> SQLiteMailRepository
```

核心业务模块不得导入 Web 请求处理器、CLI 参数对象或具体 HTTP 类型。入口层负责创建具体实现并注入应用服务。

## 目标一：高内聚

### 模块职责

- `accounts.py`：账号输入、格式验证和脱敏。
- `oauth.py`：OAuth2 token 刷新。
- `message_parsing.py`：RFC822、MIME、正文、日期和字符集解析。
- `mail_fetching.py`：单个账号的 Outlook IMAP 访问与拉取诊断。
- `application.py`：多个账号的调度、结果汇总和错误隔离。
- `repositories.py`：持久化接口定义。
- `storage.py`：SQLite 存储实现与迁移。
- `web.py`：HTTP 路由、JSON 校验和响应适配。
- `cli.py`：命令行参数和终端输出适配。

文件名可以在实施计划阶段根据现有代码迁移成本微调，但职责边界不得合并回 Web、CLI 或单个大型协议模块。

### 验收标准

- MIME 邮件解析可在没有 IMAP 客户端的情况下独立调用和测试。
- 批量账号遍历、失败汇总和并发调度只存在于应用服务。
- Web 和 CLI 不再分别实现批量拉取循环。
- 核心模块可以使用假拉取器、假解析器和假存储进行单元测试。

## 目标二：低耦合

### 接口边界

使用 Python `Protocol` 或等价的小型显式接口定义以下边界：

- `AccountMailFetcher.fetch(account, options) -> FetchAccountResult`
- `MessageParser.parse(raw_message, context) -> EmailRecord`
- `MailRepository.save_many(records) -> int`

应用服务只依赖这些接口。具体 Outlook、SQLite 实现在入口组合阶段注入。

### 数据模型

- `FetchOptions` 表示单账号拉取参数。
- `FetchAccountResult` 表示单账号成功或失败结果、邮件列表、耗时和诊断。
- `BatchFetchResult` 表示保持输入顺序的完整批量结果。
- Web 层负责把结果映射为当前前端期待的 JSON 结构。
- CLI 层负责保存邮件和输出终端摘要。

### 验收标准

- 应用服务不导入 `imaplib`、`sqlite3`、`BaseHTTPRequestHandler` 或 `argparse.Namespace`。
- `web.py` 和 `cli.py` 通过同一个应用服务执行批量拉取。
- 测试包含依赖方向保护，防止核心模块反向依赖入口层。
- 修改一种具体实现不要求修改应用服务主流程。

## 目标三：优雅命名

### 命名规则

- 类型名称表达业务角色：`BatchFetchService`、`AccountMailFetcher`、`MessageParser`、`MailRepository`。
- 结果类型明确作用范围：`FetchAccountResult`、`BatchFetchResult`。
- 动作函数使用一致动词：邮件网络获取统一使用 `fetch`，持久化使用 `save`，内容解释使用 `parse` 或 `extract`。
- 布尔字段使用 `is_`、`has_`、`should_`、`include_` 等前缀。
- 避免在核心架构中新增 `Manager`、`Helper`、`Utils`、`Processor`、`data` 等含义不清的名称。
- 保留公开兼容名称时，应通过薄适配层完成，并在代码中标明迁移目的。

### 验收标准

- 新增的公共类型和方法符合上述词汇表。
- Web、CLI、应用层和测试对同一概念使用相同名称。
- 测试名称描述行为与结果，不描述实现步骤。
- 通过代码审查式搜索确认没有新增被禁止的模糊核心名称。

## 目标四：轻量插件化

### 验证码规则

验证码识别采用规则注册表。每条规则接收标准化邮件视图并返回匹配结果或空值。匹配结果至少包含：

- `code`
- `provider`
- `confidence`
- `rule_id`

规则具有稳定标识和显式优先级。注册表按优先级执行；单条规则的“不匹配”不影响后续规则。现有提供商识别与通用回退规则迁移到该结构中。

前端仍保持原生 JavaScript，不引入打包器。规则和注册表放在可被 Node 测试直接加载的模块中，`app.js` 只调用统一识别入口。

### 邮件解析规则

后端先建立 `MessageParser` 接口和一个默认 RFC822/MIME 实现。只有当确实出现第二个解析实现时，才增加多解析器注册表；本次不引入动态发现机制。

### 验收标准

- 新增验证码规则只需要新增规则实现并注册，不修改识别调度循环。
- 规则优先级、回退、异常隔离和结果字段均有测试。
- 现有验证码识别行为保持通过。
- 邮件拉取逻辑只依赖 `MessageParser` 接口，不依赖解析器内部函数。
- 不存在目录扫描、动态导入或外部插件安装逻辑。

## 目标五：多账号并发拉取

### 并发模型

由于 OAuth、IMAP 和现有标准库接口均为阻塞式，使用 `concurrent.futures.ThreadPoolExecutor` 实现账号级并发。

- `BatchFetchService` 接收 `max_workers`。
- 默认并发数为 `min(4, max(1, account_count))`。
- 配置必须有合理上限，避免一次请求创建过多线程。
- 一个任务只处理一个账号，并拥有独立 token 请求、IMAP 连接、解析器调用、诊断和异常结果。
- 工作线程负责网络拉取和邮件解析，不共享 SQLite 连接。
- CLI 在批量任务完成后按输入顺序集中写入 SQLite，避免写锁竞争。
- Web 返回的账号行和邮件分组保持输入账号顺序，前端 JSON 结构保持兼容。

### 错误与取消语义

- 一个账号失败不会令其他账号失败。
- `stop_on_error=false` 时收集全部结果。
- `stop_on_error=true` 时首次观察到失败后取消尚未开始的任务；已经开始的任务允许结束并被纳入结果。
- 失败结果必须记录阶段、可见错误、耗时和已有诊断。
- 并发调度层不得记录或返回未脱敏的凭据。

### 验收标准

- 使用同步屏障或活动任务计数证明至少两个账号任务真实重叠执行，不使用脆弱的固定耗时阈值作为唯一证据。
- `max_workers=1` 与旧的顺序行为一致。
- 并发完成顺序不同于输入顺序时，最终结果仍保持输入顺序。
- 单账号失败、全部失败、部分失败、零账号和取消待执行任务均有测试。
- 并发 Web 请求之间不共享可变的批量状态。

## 前端与 Docker 兼容性

- `index.html`、现有主要控件、视觉结构和交互行为保持不变。
- `/api/config`、`/api/accounts`、`/api/check` 和 `/api/fetch` 的前端所需字段保持兼容。
- `docker compose up -d` 继续使用 GHCR 镜像。
- `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build` 继续构建并运行本地源码。
- Docker 健康检查继续访问 `/api/config`。

## 测试与提交策略

每个目标使用独立提交，提交前必须运行对应测试：

1. 高内聚与低耦合：核心应用服务、解析器、Web、CLI、存储和 IMAP 测试。
2. 优雅命名：相关单元测试、元数据测试和模糊名称/依赖方向检查。
3. 轻量插件化：验证码 Node 测试、前端运行时测试、邮件解析测试。
4. 多账号并发：应用服务并发测试、Web 测试、CLI 测试和失败隔离测试。

每个阶段提交前还要检查 Git diff，确保没有包含现有未跟踪的产品设计审计目录或真实账号数据。

## 最终回归

全部目标完成后执行以下回归：

1. 使用 CI 对齐的 Python 3.11 运行 `python -m unittest discover -s tests`。
2. 使用 Node 22 或兼容版本运行 `node --test tests/*.test.js`。
3. 构建本地 Docker 镜像并启动服务。
4. 检查 Docker 健康状态及 `/api/config`。
5. 通过 Web API 使用 mock 账号执行账号解析和多账号并发拉取，验证响应兼容性。
6. 使用 CLI mock 流程验证拉取、SQLite 保存、搜索和查看。
7. 在用户提供或本地已有且明确授权使用的真实账号凭据下，至少对两个 Outlook 账号执行真实 OAuth2、IMAP 登录和有限量邮件拉取；不得在输出、日志或提交中暴露凭据和邮件原文。

若没有获得可用且被授权的真实账号凭据，第 7 项不能以 mock 或自动化测试替代，必须明确报告为等待外部凭据的最终回归项。

## 完成定义

- 五个架构目标的验收标准全部由当前代码和测试证明。
- 每个实施目标具有独立、可审查的 Git 提交。
- 前端界面及 Docker 启动方式保持兼容。
- CI 对齐的 Python 和 Node 全量测试通过。
- Docker 本地构建与健康检查通过。
- 真实双账号 Outlook 回归通过，或在缺少授权凭据时明确保持目标未完成。
- 工作区中原有未跟踪文件未被删除、覆盖或误提交。
