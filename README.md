# Outlook 邮件调试台

面向 Outlook 账号清单的本地调试工具，用于快速验证账号格式、OAuth2 refresh token、Outlook IMAP 连接和邮件拉取结果。

项目包含两种使用方式：

- **Web 调试台**：在浏览器中粘贴账号后自动解析账号，拉取邮件，并在当前会话内查看邮件列表与详情。Web 调试台只做即时预览，不写入本地数据库；刷新页面会清空本次结果。
- **命令行工具**：解析账号、模拟拉取、真实拉取、搜索和查看本地 SQLite 中保存的邮件。命令行 `fetch` 会写入 SQLite。

## 账号格式

账号文本每行 1 个账号，字段用 `----` 分隔：

```text
email----password----client_id----refresh_token
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `email` | Outlook 邮箱地址。 |
| `password` | 订单附带密码；当前 IMAP 登录使用 OAuth2，不直接使用该字段。 |
| `client_id` | Microsoft OAuth 应用 ID。 |
| `refresh_token` | 用于换取 IMAP OAuth2 access token 的刷新令牌。 |

## Web 调试台

启动本地服务：

```powershell
python -m mail_receiver.web --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

可选：指定默认账号文件。

```powershell
python -m mail_receiver.web --host 127.0.0.1 --port 8765 --account-file accounts.txt
```

### Web 调试流程

1. 在 **账号管理** 中粘贴一行或多行账号；账号格式提示已合并到输入框占位文案中。
2. 输入后默认启用隐私保护，界面会遮蔽敏感字段；格式完整时会自动解析账号，账号状态区只展示邮箱和拉取状态。
3. 设置 **邮箱目录**，默认 `INBOX`。
4. 设置 **每账号最多**，默认 `1`。
5. 如需调试原始邮件内容，可开启 **下载完整原文**；默认关闭时使用快速预览模式，避免下载每封完整 RFC822 原文拖慢批量拉取。
6. 在账号状态列表中选择一个账号；默认拉取范围为 **选中账号**，避免一次拉取全部账号。
7. 如需批量调试，切换到 **全部账号** 后再点击 **拉取邮件**。
8. 拉取后，账号状态列表也用于切换右侧 **邮件结果**：每个账号的邮件只显示在自己的结果桶中，切换账号不会清掉其他账号已经拉取到的结果。
9. 在 **邮件结果** 中点击邮件列表项，右侧阅读区会显示主题、发件人、收件人、账号、目录、时间和正文预览；左侧邮件行也会显示所属账号，便于区分多账号结果。
10. **运行日志** 会按最新优先展示账号解析、拉取、成功或失败事件；拉取事件会显示账号总耗时、下载字节数，以及 OAuth、连接、认证、选目录、拉取、解析等阶段耗时，便于判断到底慢在 IMAP FETCH 下载还是 MIME 解析。

### Web 调试台特性

- 无需前端构建步骤，Python 服务会直接提供 `mail_receiver/static` 下的静态页面。
- 支持浅色/深色主题，并会记住上次选择。
- 账号输入框保持每个账号一行显示，超长账号横向滚动，避免 `refresh_token` 自动折行影响批量检查。
- 邮件列表、阅读区、空状态、加载状态、错误状态和窄屏布局均在前端实现；新版界面弱化装饰色块，放大收件箱列表区域，并让阅读区元信息更紧凑。
- Web 拉取结果只保存在前端内存中，并按账号邮箱分桶；不会写入 `mail_store.sqlite3`、`localStorage` 或 `sessionStorage`，刷新页面或重新粘贴账号会清空结果。
- 不提供账号文件拖拽导入；如需文件输入，请使用命令行或启动服务时指定 `--account-file`。

### 本次界面变更摘要

- 标题文案统一为 **账号管理**、**控制台**、**运行日志** 和 **邮件结果**，移除了额外的小标题标签，降低视觉噪声。
- 移除了独立的账号格式提示条，改为在输入框占位文案中说明 `邮箱----密码----客户端 ID----刷新令牌`。
- 账号状态紧凑布局不再限制 1～2 个账号，存在账号且尚未展示邮件结果、或已有会话状态时都会保持控制区紧凑。
- 邮件工作台左侧收件箱列表宽度从 `clamp(300px, 32%, 360px)` 调整为 `clamp(390px, 42%, 520px)`，便于查看更多邮件摘要。
- 阅读区摘要、正文卡片、运行日志和统计标签改为更克制的边框与背景样式，减少强调色，仅保留当前选中邮件等关键状态提示。
- 控制台新增 **选中账号 / 全部账号** 拉取范围；默认只拉取账号状态列表中选中的账号，显式切换后才会批量拉取全部账号；点击账号只切换右侧展示，不会自动把拉取范围改回 **选中账号**。
- 控制台新增 **下载完整原文** 开关；默认关闭时只拉取邮件前 16KB 作为快速预览，开启后才下载每封完整 RFC822 原文。
- 账号状态和运行日志新增拉取诊断：每个账号显示总耗时、下载量和最慢阶段，日志显示完整阶段拆分，方便定位完整 RFC822 下载变慢的问题。
- 邮件结果改为前端内存中的按账号分桶展示，单独拉取一个账号时会覆盖该账号结果但保留其他账号结果；邮件列表行增加所属账号标识，摘要中的账号数改为当前可见结果实际涉及的账号数，减少多账号结果混淆。

## Docker 一键部署

Docker 部署默认使用 GHCR 预构建镜像，不在部署机器上构建 Python 基础镜像，也不挂载任何账号文件；账号信息仍在浏览器页面中粘贴，结果只保存在当前前端会话内。

默认镜像：

```text
ghcr.io/xiao-dan-1/outlook-mail-fetcher:latest
```

启动服务：

```powershell
docker compose up -d
```

打开：

```text
http://127.0.0.1:8765/
```

如需修改访问端口，直接改 `docker-compose.yml` 的左侧宿主机端口：

```yaml
ports:
  - "9876:8765"
```

端口含义是 `宿主机端口:容器内部端口`。右侧 `8765` 是容器内 Web 服务端口，通常不需要改；上面的配置访问地址为：

```text
http://127.0.0.1:9876/
```

查看日志：

```powershell
docker compose logs -f outlook-mail-fetcher
```

停止并移除容器：

```powershell
docker compose down
```

如果需要在本机从源码构建镜像，而不是拉取 GHCR 预构建镜像，可以使用本地构建覆盖文件：

```powershell
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

本地构建会使用 `Dockerfile` 中的 `PYTHON_IMAGE` 参数，默认基础镜像为 `python:3.11-slim`。如果你有可访问的自建/内网 Python 基础镜像，可以修改 `docker-compose.build.yml`：

```yaml
build:
  args:
    PYTHON_IMAGE: python:3.11-slim
```

把 `PYTHON_IMAGE` 的值替换成你的基础镜像地址即可。

`mail.sqlite3` 是命令行工具保存邮件时使用的本地 SQLite 数据库；Docker Web 部署不读取也不写入它。只使用 Web 调试台时可以忽略这个文件；如果里面有命令行拉取过的历史邮件数据，按需保留。镜像构建上下文会通过 `.dockerignore` 排除本地数据库、环境变量文件、测试目录和本地账号文本文件，避免把调试数据打进镜像。

## 命令行工具

### 解析账号

```powershell
python -m mail_receiver.cli inspect-accounts accounts.txt
```

输出账号数量，并以脱敏形式显示密码和 refresh token。

### 使用模拟邮件跑通本地链路

```powershell
python -m mail_receiver.cli fetch accounts.txt --mock --limit 3
python -m mail_receiver.cli search --query welcome
python -m mail_receiver.cli show 1
```

### 真实拉取并写入 SQLite

```powershell
python -m mail_receiver.cli fetch accounts.txt --limit 10 --debug
```

只调试一个账号：

```powershell
python -m mail_receiver.cli fetch accounts.txt --account user@outlook.com --limit 1 --debug
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--mailbox INBOX` | 指定邮箱目录，默认 `INBOX`。 |
| `--limit 20` | 每个账号最多拉取的邮件数。 |
| `--account user@outlook.com` | 只处理指定邮箱。 |
| `--mock` | 使用本地模拟邮件，不访问 Outlook。 |
| `--stop-on-error` | 任一账号失败后立即停止；默认会继续处理后续账号并汇总失败。 |
| `--db path\to\mail.sqlite3` | 指定 SQLite 数据库路径；默认 `mail_store.sqlite3`。 |
| `--debug` | 输出详细日志，便于排查 OAuth/IMAP 问题。 |

### 搜索和查看本地邮件

搜索本地 SQLite：

```powershell
python -m mail_receiver.cli search --query keyword --limit 20
```

查看某封邮件摘要：

```powershell
python -m mail_receiver.cli show 1
```

查看原始 RFC822 内容：

```powershell
python -m mail_receiver.cli show 1 --raw
```

## 设计与数据边界

- 账号解析只做格式校验和脱敏展示，避免在日志和 UI 中泄漏敏感字段。
- OAuth2 默认使用 `https://login.microsoftonline.com/consumers/oauth2/v2.0/token` 刷新 access token。
- IMAP 默认使用 `outlook.office365.com:993` 和 `XOAUTH2` 认证。
- Web 调试台前端调用 `/api/accounts` 和 `/api/fetch`，返回的是当前请求结果；服务端仍保留 `/api/check` 以兼容已有接口。
- 命令行 `fetch` 会把邮件原始 RFC822、正文预览、主题、发件人、收件人、日期等字段保存到 SQLite。
- 本地搜索基于 SQLite `LIKE`，适合调试排查；后续可升级到 FTS5。

## 回归测试

```powershell
python -m unittest discover -s tests
```

当前测试覆盖账号解析、OAuth/IMAP 流程封装、SQLite 存储、Web API、静态 UI 结构和响应式样式约束。
