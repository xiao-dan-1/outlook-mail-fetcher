# Outlook Mail Fetcher

轻量级 Outlook 邮件拉取工具，支持 Web 控制台和 CLI。它通过 OAuth2 获取 access token，并使用 Outlook IMAP 拉取邮件，适合账号检查、邮件预览和本地调试。

## Features

- Web 控制台：粘贴账号、拉取邮件、即时预览。
- CLI：支持账号检查、模拟拉取、真实拉取、搜索和查看本地邮件。
- OAuth2 + IMAP：通过 XOAUTH2 登录 Outlook IMAP。
- 隐私友好：Web 结果只保存在当前浏览器会话内。
- Docker 部署：默认使用 GHCR 预构建镜像。

## Account Format

每行一个账号，字段使用 `----` 分隔：

```text
email----password----client_id----refresh_token
```

| 字段 | 说明 |
| --- | --- |
| `email` | Outlook 邮箱地址。 |
| `password` | 订单附带密码；IMAP 登录不直接使用。 |
| `client_id` | Microsoft OAuth 应用 ID。 |
| `refresh_token` | 用于换取 IMAP OAuth2 access token。 |

## Quick Start

### 容器启动

```powershell
docker compose up -d
```

打开 `http://127.0.0.1:8765/`。

### 本地启动

```powershell
python -m mail_receiver.web --host 127.0.0.1 --port 8765
```

如需默认账号文件：

```powershell
python -m mail_receiver.web --host 127.0.0.1 --port 8765 --account-file accounts.txt
```

## Docker

默认 GHCR 镜像：`ghcr.io/xiao-dan-1/outlook-mail-fetcher:latest`。

修改端口只改左侧宿主机端口：

```yaml
ports:
  - "9876:8765"
```

访问 `http://127.0.0.1:9876/`。

常用命令：

```powershell
docker compose up -d
docker compose logs -f outlook-mail-fetcher
docker compose down
```

### Update

```powershell
docker compose pull && docker compose up -d
git pull
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

第一行用于更新 GHCR 预构建镜像；后两行用于更新本地源码构建。

本地构建默认使用 `python:3.11-slim`；如需替换基础镜像，修改 `docker-compose.build.yml` 中的 `PYTHON_IMAGE`。

`mail.sqlite3` 是 CLI 持久化邮件时使用的本地 SQLite 数据库；Docker Web 部署不读取也不写入它。

## CLI

检查账号格式：

```powershell
python -m mail_receiver.cli inspect-accounts accounts.txt
```

使用模拟邮件跑通流程：

```powershell
python -m mail_receiver.cli fetch accounts.txt --mock --limit 3
python -m mail_receiver.cli search --query welcome
python -m mail_receiver.cli show 1
```

真实拉取邮件并写入 SQLite：

```powershell
python -m mail_receiver.cli fetch accounts.txt --limit 10 --debug
```

只处理一个账号：

```powershell
python -m mail_receiver.cli fetch accounts.txt --account user@outlook.com --limit 1 --debug
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--mailbox INBOX` | 邮箱目录，默认 `INBOX`。 |
| `--limit 20` | 每个账号最多拉取的邮件数。 |
| `--account user@outlook.com` | 只处理指定邮箱。 |
| `--mock` | 使用本地模拟邮件。 |
| `--db path\to\mail.sqlite3` | SQLite 数据库路径。 |
| `--debug` | 输出详细日志。 |

## Data and Privacy

- Web 控制台不写入 SQLite、`localStorage` 或 `sessionStorage`。
- Web 结果只保存在前端内存中；刷新页面会清空。
- CLI `fetch` 会把邮件摘要、正文预览和原始 RFC822 保存到 SQLite。
- 日志和界面只展示脱敏后的账号信息。

## Development
当前版本：`0.1.0`。发布版本：`git tag v0.1.0 && git push origin v0.1.0`，GitHub Actions 会发布同名 GHCR 镜像。

```powershell
python -m unittest discover -s tests
```

## License

MIT License. See [MIT License](LICENSE).
