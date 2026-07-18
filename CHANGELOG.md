# Changelog

本项目的更新记录写在这里；发布时把当前版本号、日期和用户可感知的变更列清楚。

## [0.1.3] - 2026-07-18

### Added

- Web API 新增 `raw_message_complete` 完整性标记；`include_raw=true` 时新增无损 RFC822 字节字段 `raw_message_base64`。
- IMAP 邮箱目录新增 Modified UTF-7 编码与安全引用，支持中文、日文、Emoji、引号和反斜杠目录名。
- 新增 47 项 Node.js 前端行为测试，并接入 Python `unittest` discovery；GitHub Actions 现在先运行 Python 3.11 和 Node.js 22 测试，再构建或发布镜像。

### Changed

- 最近邮件拉取改为 UID 搜索、数值排序去重和单次 UID FETCH，降低邮件删除或序号变化造成的错取风险。
- CLI 的 `--db`、`--debug` 可放在子命令前后；`show --raw` 直接输出无损原始字节；负数 `limit` 会被拒绝。
- SQLite 账号身份改为 ASCII 大小写不敏感，并加强旧库索引、事务回滚和自增序列迁移；历史库若存在仅账号大小写不同、其余邮件身份相同的重复记录，迁移时保留 ID 最小的一条。
- Web JSON 参数改为严格类型校验，拉取 `limit` 限制为 `0..100`，请求体限制为 1 MiB 和 5 秒总读取期限。
- 内联提交 `account_text` 时，Web 响应中的 `account_file` 从字符串 `"None"` 修正为 JSON `null`。

### Fixed

- 修复跨账号同 ID 邮件选错、账号编辑后旧请求污染新会话、重复拉取与失败重试竞态，以及网络失败后账号长期停留在处理中。
- 修复残缺账号凭据仍可发起请求、浏览器存储不可用时主题初始化失败、邮件列表 ARIA 选择状态残留等前端问题。
- 修复未知 MIME charset、空白纯文本遮蔽 HTML、附件正文混入预览，以及 IMAP FETCH trailer 元数据串到其他邮件的问题。
- 修复无效 JSON、错误 `Content-Length`、慢速或不完整请求体、错误 HTTP 状态码和 UID 拉取阶段分类。
- 修复 CLI 与 Web 日志中的控制字符注入，并保留普通文本界面的可读转义。
- 修复窄屏日志标签遮挡内容，以及邮箱地址数字被误识别为验证码；例如正文 `987243` 不再被收件人地址中的 `1400` 覆盖。

## [0.1.2] - 2026-07-12

### Added

- 新增 `docs/api.md`，集中说明 Web 控制台 HTTP API、请求字段、响应格式和 curl 示例。
- 前端验证码解析新增 provider registry，支持按服务商扩展规则。
- 新增 xAI/Grok 验证码识别，支持 `E5J-6IG` 这类字母数字加中横线的确认码。

### Changed

- 验证码摘要和控制台当前验证码会显示服务商标签，例如 `xAI · xAI 确认码 · 高置信`。

### Fixed

- xAI/Grok 专用解析必须先命中服务商身份，避免把普通 OpenAI 或通用验证码邮件误标为 xAI。
