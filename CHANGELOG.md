# Changelog

本项目的更新记录写在这里；发布时把当前版本号、日期和用户可感知的变更列清楚。

## [0.1.2] - 2026-07-12

### Added

- 新增 `docs/api.md`，集中说明 Web 控制台 HTTP API、请求字段、响应格式和 curl 示例。
- 前端验证码解析新增 provider registry，支持按服务商扩展规则。
- 新增 xAI/Grok 验证码识别，支持 `E5J-6IG` 这类字母数字加中横线的确认码。

### Changed

- 验证码摘要和控制台当前验证码会显示服务商标签，例如 `xAI · xAI 确认码 · 高置信`。

### Fixed

- xAI/Grok 专用解析必须先命中服务商身份，避免把普通 OpenAI 或通用验证码邮件误标为 xAI。
