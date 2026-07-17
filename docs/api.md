# API Reference

本文档描述 Outlook Mail Fetcher Web 控制台使用的本地 HTTP API。默认服务地址：

```text
http://127.0.0.1:8765
```

所有 JSON 响应都使用 `Content-Type: application/json; charset=utf-8`。除静态文件外，错误响应统一为：

```json
{
  "error": "错误信息"
}
```

常见状态码：

| 状态码 | 含义 |
| --- | --- |
| `200` | 请求成功 |
| `400` | 请求参数或账号格式错误 |
| `403` | 静态文件路径越界 |
| `404` | 路径、资源或指定账号不存在 |
| `408` | JSON 请求体读取超时 |
| `413` | JSON 请求体超过 1 MiB 上限 |
| `500` | 服务端执行失败 |

POST 接口的 JSON 请求体最大为 1 MiB，并须在默认 5 秒总读取期限内完整到达，否则返回 `408`；客户端提前结束、实际字节数少于 `Content-Length` 时返回 `400`。

## Account input

账号可以通过 `account_text` 直接提交，也可以通过服务启动参数 `--account-file` 或接口参数 `account_file` 指定文件。

账号文本格式为每行一个账号，字段用 `----` 分隔：

```text
email----password----client_id----refresh_token
```

接口返回账号信息时会脱敏 `password` 和 `refresh_token`。

## Shared request fields

多个 POST 接口共用以下字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `account_text` | string | 否 | 无 | 多行账号文本；优先级高于 `account_file` |
| `account_file` | string | 否 | 启动时的 `--account-file` | 账号文件路径 |
| `account` | string | 否 | 无 | 只处理指定邮箱 |
| `mailbox` | string | 否 | `INBOX` | IMAP 邮箱目录 |
| `limit` | integer | 否 | fetch 为 `20`，前端默认 `1` | 每个账号最多拉取的邮件数，范围 `0..100` |
| `imap_host` | string | 否 | `outlook.office365.com` | IMAP 主机 |
| `imap_port` | integer | 否 | `993` | IMAP SSL 端口 |
| `imap_timeout` | integer | 否 | `8` | IMAP 超时时间，秒 |
| `token_endpoint` | string | 否 | Microsoft OAuth token endpoint | OAuth2 token endpoint |
| `token_timeout` | integer | 否 | `8` | OAuth2 请求超时时间，秒 |
| `scope` | string | 否 | Outlook IMAP scope | OAuth2 refresh scope |
| `stop_on_error` | boolean | 否 | `false` | 遇到单个账号失败后是否停止 |

## GET /api/config

返回前端初始化需要的版本和默认配置。

### Response

```json
{
  "version": "0.1.2",
  "account_file": null,
  "defaults": {
    "mailbox": "INBOX",
    "limit": 1,
    "imap_host": "outlook.office365.com",
    "imap_port": 993,
    "imap_timeout": 8,
    "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "token_timeout": 8,
    "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
  }
}
```

## GET /api/accounts

从账号文件解析账号。通常用于服务启动时带了 `--account-file` 的场景。

### Query parameters

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account_file` | string | 否 | 覆盖启动时的账号文件路径 |

### Response

```json
{
  "account_file": "accounts.txt",
  "count": 1,
  "accounts": [
    {
      "line": 1,
      "email": "user@outlook.com",
      "password": "pa********rd",
      "client_id": "client-id",
      "refresh_token": "refresh_********_token"
    }
  ]
}
```

## POST /api/accounts

从请求体中的 `account_text` 或 `account_file` 解析账号，不连接 Outlook。

### Request

```json
{
  "account_text": "user@outlook.com----password----client-id----refresh-token"
}
```

### Response

```json
{
  "account_file": null,
  "count": 1,
  "accounts": [
    {
      "line": 1,
      "email": "user@outlook.com",
      "password": "pa********rd",
      "client_id": "client-id",
      "refresh_token": "refresh-********-token"
    }
  ]
}
```

## POST /api/check

检查账号 OAuth2/IMAP 登录和邮箱目录可用性，但不拉取邮件内容。

### Request

```json
{
  "account_text": "user@outlook.com----password----client-id----refresh-token",
  "mailbox": "INBOX",
  "account": "user@outlook.com",
  "stop_on_error": false
}
```

### Response

```json
{
  "accounts": 1,
  "ok": 1,
  "failed": 0,
  "rows": [
    {
      "email": "user@outlook.com",
      "ok": true,
      "stage": "imap",
      "mailbox": "INBOX",
      "message_count": 12,
      "error": null
    }
  ]
}
```

失败账号会保留在 `rows` 中，`ok` 为 `false`，`stage` 可能为：

| stage | 说明 |
| --- | --- |
| `oauth` | OAuth2 refresh token 或 token endpoint 失败 |
| `connect` | IMAP 连接失败 |
| `auth` | XOAUTH2 认证失败 |
| `select` | 邮箱目录选择失败 |
| `fetch` | 拉取邮件失败 |
| `unknown` | 其他错误 |

## POST /api/fetch

拉取邮件并返回本次会话的账号结果和邮件列表。Web 控制台只把结果保存在浏览器内存中；该接口不会写入 SQLite。

### Request

```json
{
  "account_text": "user@outlook.com----password----client-id----refresh-token",
  "mailbox": "INBOX",
  "limit": 1,
  "account": "user@outlook.com",
  "include_raw": false,
  "mock": false,
  "stop_on_error": false
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `include_raw` | boolean | `true` 时返回 `raw_message` 可读文本视图和 `raw_message_base64` 无损字节表示，同时不限制预览下载大小 |
| `mock` | boolean | `true` 时使用本地模拟邮件，不连接 Outlook |

### Response

```json
{
  "account_file": null,
  "accounts": 1,
  "fetched": 1,
  "failed": 0,
  "rows": [
    {
      "email": "user@outlook.com",
      "ok": true,
      "fetched": 1,
      "elapsed_ms": 1200,
      "error": null,
      "timings": {
        "oauth_ms": 100,
        "connect_ms": 200,
        "auth_ms": 150,
        "select_ms": 80,
        "fetch_ms": 600,
        "parse_ms": 70
      },
      "raw_bytes": 4096,
      "downloaded_bytes": 4096,
      "message_count": 1
    }
  ],
  "messages": [
    {
      "id": 1,
      "account_email": "user@outlook.com",
      "mailbox": "INBOX",
      "uid": 123,
      "uidvalidity": 456,
      "message_id": "<message@example.com>",
      "subject": "安全验证码 123456",
      "sender": "Security <security@example.com>",
      "recipients": "user@outlook.com",
      "sent_at": "2026-07-12T12:00:00+08:00",
      "body_preview": "您的验证码是 123456",
      "raw_message_complete": true
    }
  ]
}
```

`messages[]` 中的 `raw_message_complete` 始终存在。它表示本次 IMAP 拉取到的 `raw_message` 字节是否覆盖整封邮件；默认预览模式可能只下载前缀，因此该值可能为 `false`。

当 `include_raw` 为 `true` 时，`messages[]` 中会额外包含：

```json
{
  "raw_message": "Subject: Raw\r\n\r\ncaf�",
  "raw_message_base64": "U3ViamVjdDogUmF3DQoNCmNhZuk="
}
```

`raw_message` 是为兼容现有调用方保留的 UTF-8 可读文本视图。无法按 UTF-8 解码的原始字节会替换为 `U+FFFD`，因此该字段可能有损。`raw_message_base64` 是权威、无损的 RFC822 字节表示；调用方应对它进行 Base64 解码来恢复服务器实际返回的原始字节，并结合 `raw_message_complete` 判断这些字节是否覆盖整封邮件。

## curl examples

### Parse pasted accounts

```powershell
curl.exe -X POST http://127.0.0.1:8765/api/accounts `
  -H "Content-Type: application/json" `
  -d "{\"account_text\":\"user@outlook.com----password----client-id----refresh-token\"}"
```

### Fetch one mailbox message with mock data

```powershell
curl.exe -X POST http://127.0.0.1:8765/api/fetch `
  -H "Content-Type: application/json" `
  -d "{\"account_text\":\"user@outlook.com----password----client-id----refresh-token\",\"mailbox\":\"INBOX\",\"limit\":1,\"mock\":true}"
```
