const { createOperationGate, createRequestFailureState, createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;

const state = {
  config: null,
  accounts: [],
  accountStatus: new Map(),
  failedRows: [],
  messagesByAccount: new Map(),
  selectedMessageKey: null,
  selectedAccountEmail: "",
  activeAccountEmail: "",
  fetchScope: "selected",
  parsedText: "",
  busy: false,
  accountPrivacy: true,
};

const sessionRequests = createSessionCoordinator();
const mailOperationGate = createOperationGate();

const THEME_STORAGE_KEY = "mailReceiverTheme";
const AUTO_PARSE_DELAY_MS = 300;
const VERIFICATION_KEYWORD_PATTERN = /验证码|验证代码|校验码|动态码|verification|verify|code|otp|passcode|security code/i;
// Provider-specific rules run before the generic fallback. Add new providers above "generic".
const VERIFICATION_PROVIDERS = [
  {
    id: "xai",
    label: "xAI",
    source: "xAI 确认码",
    identityPatterns: [/x\.ai/i, /xai/i, /grok/i],
    keywords: [/confirmation code/i, /verification code/i, /security code/i],
    codePatterns: [
      {
        pattern: /(?<![A-Z0-9])([A-Z0-9]{3}[-\s][A-Z0-9]{3})(?![A-Z0-9])/i,
        preserveSeparator: true,
        validator: /^[A-Z0-9]{6}$/i,
      },
      {
        pattern: /(?:confirmation code|verification code|security code|验证码)[^A-Z0-9]{0,48}([A-Z0-9][A-Z0-9\s-]{2,10}[A-Z0-9])/i,
        preserveSeparator: true,
        validator: /^[A-Z0-9]{4,8}$/i,
      },
    ],
  },
  {
    id: "generic",
    label: "通用",
    source: "关键词附近",
    keywords: [VERIFICATION_KEYWORD_PATTERN],
    codePatterns: [
      {
        pattern: /(?<!\d)(\d[\d\s-]{2,10}\d)(?!\d)/,
        validator: /^\d{4,8}$/,
      },
    ],
    fallbackCodePatterns: [
      {
        pattern: /(?<!\d)(\d{4,8})(?!\d)/,
        source: "正文数字",
        confidence: "medium",
        validator: /^\d{4,8}$/,
      },
    ],
  },
];
let autoParseTimer = null;

const el = {
  statusLine: document.getElementById("statusLine"),
  statusModule: document.getElementById("statusModule"),
  appVersionBadge: document.getElementById("appVersionBadge"),
  themeToggle: document.getElementById("themeToggle"),
  fetchBtn: document.getElementById("fetchBtn"),
  currentCodeSummary: document.getElementById("currentCodeSummary"),
  accountTextInput: document.getElementById("accountTextInput"),
  privacyToggle: document.getElementById("privacyToggle"),
  inputQuality: document.getElementById("inputQuality"),
  mailboxInput: document.getElementById("mailboxInput"),
  limitInput: document.getElementById("limitInput"),
  rawFetchToggle: document.getElementById("rawFetchToggle"),
  selectedScopeBtn: document.getElementById("selectedScopeBtn"),
  allScopeBtn: document.getElementById("allScopeBtn"),
  operationNote: document.getElementById("operationNote"),
  accountCount: document.getElementById("accountCount"),
  accountList: document.getElementById("accountList"),
  accountInputPanel: document.querySelector(".account-input-panel"),
  controlColumn: document.querySelector(".control-column"),
  mailSummary: document.getElementById("mailSummary"),
  mailList: document.getElementById("mailList"),
  mailDetail: document.getElementById("mailDetail"),
  runLog: document.getElementById("runLog"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  logDrawerToggle: document.getElementById("logDrawerToggle"),
};

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  el.themeToggle?.setAttribute("aria-pressed", String(nextTheme === "dark"));
}

function initTheme() {
  let savedTheme = null;
  try {
    savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    savedTheme = null;
  }
  applyTheme(savedTheme || "light");
}

function toggleTheme() {
  const currentTheme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const nextTheme = currentTheme === "dark" ? "light" : "dark";
  try {
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  } catch {
    // The active theme remains usable when browser storage is unavailable.
  }
  applyTheme(nextTheme);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeReadableText(value) {
  return String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatMailDate(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function formatElapsedTime(elapsedMs) {
  const value = Number(elapsedMs);
  if (!Number.isFinite(value) || value < 0) {
    return "耗时未知";
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)}s`;
}

function formatBytes(byteCount) {
  const value = Number(byteCount);
  if (!Number.isFinite(value) || value < 0) {
    return "大小未知";
  }
  if (value < 1024) {
    return `${Math.round(value)}B`;
  }
  const units = ["KB", "MB", "GB"];
  let scaled = value / 1024;
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  return `${scaled.toFixed(scaled < 10 ? 1 : 0)}${units[unitIndex]}`;
}

const TIMING_STAGE_ORDER = [
  ["oauth", "OAuth"],
  ["connect", "连接"],
  ["auth", "认证"],
  ["select", "选目录"],
  ["fetch", "拉取"],
  ["parse", "解析"],
];

function timingEntries(timings = {}) {
  return TIMING_STAGE_ORDER
    .map(([stage, label]) => {
      const elapsedMs = Number(timings?.[`${stage}_ms`]);
      if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
        return null;
      }
      return { stage, label, elapsed_ms: elapsedMs };
    })
    .filter(Boolean);
}

function formatTimingBreakdown(timings = {}) {
  const entries = timingEntries(timings);
  if (!entries.length) {
    return "阶段未知";
  }
  return entries.map((entry) => `${entry.label} ${formatElapsedTime(entry.elapsed_ms)}`).join(" / ");
}

function senderDisplayName(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "未知发件人";
  }
  const match = raw.match(/^(.+?)\s*<[^>]+>$/);
  return (match?.[1] || raw).replace(/^["']|["']$/g, "").trim() || raw;
}

function senderAddress(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  const match = raw.match(/<([^>]+)>/);
  return (match?.[1] || raw).replace(/^mailto:/i, "").trim() || raw;
}

function senderInitial(value) {
  const displayName = senderDisplayName(value).replace(/^[^A-Za-z0-9\u4e00-\u9fff]+/, "").trim();
  return (Array.from(displayName)[0] || "邮").toUpperCase();
}

function firstReadableValue(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function addReadableBlockBreaks(documentFragment) {
  for (const node of documentFragment.querySelectorAll("br")) {
    node.replaceWith(document.createTextNode("\n"));
  }
  for (const node of documentFragment.querySelectorAll("p, div, section, article, header, footer, main, aside, blockquote, li, tr, h1, h2, h3, h4, h5, h6")) {
    node.append(document.createTextNode("\n"));
  }
}

function cleanReadableMailSource(source) {
  if (!source) {
    return "";
  }

  if (/<[a-z][\s\S]*>/i.test(source) && window.DOMParser) {
    const documentFragment = new DOMParser().parseFromString(source, "text/html");
    for (const node of documentFragment.querySelectorAll("head, style, script, noscript, template, meta, link")) {
      node.remove();
    }
    addReadableBlockBreaks(documentFragment);
    const readableBody = documentFragment.body?.innerText || documentFragment.body?.textContent || "";
    const readableDocument = documentFragment.documentElement?.innerText || documentFragment.documentElement?.textContent || "";
    return normalizeReadableText(readableBody || readableDocument || source.replace(/<[^>]+>/g, " "));
  }

  return normalizeReadableText(
    source
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function readableMailPreview(mail) {
  const source = firstReadableValue(
    mail.body_preview,
    mail.snippet,
    mail.preview,
    mail.body_text,
    mail.text_body,
    mail.plain_text,
    mail.body_html,
    mail.html_body,
    mail.html,
  );
  return cleanReadableMailSource(source);
}

function readableMailText(mail) {
  const source = firstReadableValue(
    mail.body_text,
    mail.text_body,
    mail.plain_text,
    mail.body_preview,
    mail.body_html,
    mail.html_body,
    mail.html,
  );
  return cleanReadableMailSource(source);
}

function verificationSearchText(mail) {
  return [
    mail.subject,
    mail.body_preview,
    mail.snippet,
    mail.preview,
    readableMailPreview(mail),
    readableMailText(mail),
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join("\n");
}

function verificationIdentityText(mail, searchText = verificationSearchText(mail)) {
  return [mail.sender, mail.recipients, searchText]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join("\n");
}

function normalizeVerificationCode(value, options = {}) {
  const raw = String(value || "").trim();
  if (options.preserveSeparator) {
    return raw
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .toUpperCase();
  }
  return raw.replace(/[\s-]+/g, "").toUpperCase();
}

function compactCodeValue(value) {
  return normalizeVerificationCode(value);
}

function compactComparableCode(value) {
  return String(value || "").replace(/[\s-]+/g, "").toUpperCase();
}

function providerMatchesText(provider, text) {
  return !provider.identityPatterns?.length || provider.identityPatterns.some((pattern) => pattern.test(text));
}

function providerKeywordWindows(text, provider) {
  const windows = [];
  for (const keyword of provider.keywords || []) {
    const keywordMatch = text.match(keyword);
    if (!keywordMatch) {
      continue;
    }
    const windowStart = Math.max(0, keywordMatch.index - 64);
    const windowEnd = Math.min(text.length, keywordMatch.index + 180);
    windows.push({
      text: text.slice(windowStart, windowEnd),
      source: provider.source || "关键词附近",
      confidence: "high",
    });
  }
  return windows;
}

function codeCandidateFromRule(provider, rule, windowInfo) {
  const match = windowInfo.text.match(rule.pattern);
  if (!match) {
    return null;
  }
  const rawCode = match[1] || match[0];
  const code = normalizeVerificationCode(rawCode, rule);
  const comparableCode = compactComparableCode(code);
  if (rule.validator && !rule.validator.test(comparableCode)) {
    return null;
  }
  return {
    code,
    source: rule.source || windowInfo.source,
    confidence: rule.confidence || windowInfo.confidence,
    provider: provider.id,
    providerLabel: provider.label,
  };
}

function providerVerificationCandidate(provider, text, identityText = text) {
  if (provider.identityPatterns?.length && !providerMatchesText(provider, identityText)) {
    return null;
  }

  for (const windowInfo of providerKeywordWindows(text, provider)) {
    for (const rule of provider.codePatterns || []) {
      const candidate = codeCandidateFromRule(provider, rule, windowInfo);
      if (candidate) {
        return candidate;
      }
    }
  }

  for (const rule of provider.fallbackCodePatterns || []) {
    const candidate = codeCandidateFromRule(provider, rule, {
      text,
      source: rule.source || "正文数字",
      confidence: rule.confidence || "medium",
    });
    if (candidate) {
      return candidate;
    }
  }
  return null;
}

function extractVerificationCode(mail) {
  const text = verificationSearchText(mail);
  if (!text) {
    return {
      code: "",
      source: "未找到可读内容",
      confidence: "none",
    };
  }

  const identityText = verificationIdentityText(mail, text);
  for (const provider of VERIFICATION_PROVIDERS) {
    const candidate = providerVerificationCandidate(provider, text, identityText);
    if (candidate) {
      return candidate;
    }
  }

  return {
    code: "",
    source: "未识别验证码",
    confidence: "none",
  };
}

function selectedMail() {
  return findMessageByKey(allSessionMessages(), state.selectedMessageKey);
}

function verificationRows() {
  return allSessionMessages()
    .map((mail) => ({ mail, verification: extractVerificationCode(mail) }))
    .filter((row) => row.verification.code);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function requestIsStale(revision, error) {
  return !sessionRequests.isCurrent(revision) || error?.name === "AbortError";
}

function recordRequestFailure(email, error) {
  const failure = createRequestFailureState(email, error);
  state.accountStatus.set(email, failure.status);
  const failedByEmail = new Map(state.failedRows.map((row) => [row.email, row]));
  failedByEmail.set(email, failure.row);
  state.failedRows = Array.from(failedByEmail.values());
  renderAccounts(state.accounts);
}

function failureInsight(message, stage = "") {
  const detail = String(message || "").trim();
  const lowerDetail = detail.toLowerCase();
  const normalizedStage = String(stage || "").toLowerCase();

  if (
    normalizedStage === "oauth"
    || lowerDetail.includes("invalid_grant")
    || detail.includes("AADSTS7000012")
    || lowerDetail.includes("different tenant")
  ) {
    return {
      title: "OAuth 授权失败",
      summary: "刷新令牌不可用于当前租户。",
      nextStep: "检查 client ID、租户与 refresh token 是否来自同一账号或租户，然后重试失败账号。",
      detail: detail || "没有返回更多技术细节。",
    };
  }

  if (lowerDetail.includes("timeout") || detail.includes("超时")) {
    return {
      title: "连接超时",
      summary: "邮件服务器没有在预期时间内响应。",
      nextStep: "检查网络、邮箱目录和账号授权后重试失败账号。",
      detail: detail || "没有返回更多技术细节。",
    };
  }

  if (lowerDetail.includes("authentication") || detail.includes("认证") || detail.includes("授权")) {
    return {
      title: "账号认证失败",
      summary: "当前账号未通过邮件服务认证。",
      nextStep: "重新确认密码、客户端 ID 与刷新令牌后重试失败账号。",
      detail: detail || "没有返回更多技术细节。",
    };
  }

  return {
    title: "拉取失败",
    summary: detail ? detail.replace(/\s+/g, " ").slice(0, 96) : "当前账号未能完成邮件拉取。",
    nextStep: "检查账号格式、邮箱目录和授权状态后重试失败账号。",
    detail: detail || "没有返回更多技术细节。",
  };
}

function failureLogMessage(email, message, stage = "") {
  const insight = failureInsight(message, stage);
  const accountLabel = email || "当前账号";
  return `${accountLabel}: ${insight.title}：${insight.summary} ${insight.nextStep}`;
}

function latestFailureMessage() {
  if (state.failedRows.length) {
    return state.failedRows[0].error || "";
  }
  const failedStatus = Array.from(state.accountStatus.values()).find((status) => status?.kind === "fail");
  return failedStatus?.error || "";
}

function failureSummaryText(message = latestFailureMessage()) {
  const insight = failureInsight(message);
  return `${insight.title}：${insight.summary}\n下一步：${insight.nextStep}`;
}

function failureAccessibilityLabel(status) {
  if (!status) {
    return "待拉取";
  }
  if (status.kind !== "fail") {
    return accountStatusLabel(status);
  }
  const insight = failureInsight(status.error, status.stage);
  return `失败，${statusStageLabel(status.stage)}，耗时 ${formatElapsedTime(status.elapsed_ms)}，${insight.title}，${insight.summary}`;
}

function compactStatusText(text, tone = "ready") {
  const raw = String(text ?? "").trim();
  if (!raw) {
    return "待命";
  }

  const completeLabel = "完成 ·";
  const readLabel = "读取 ·";
  const failLabel = "失败 ·";
  const firstNumber = raw.match(/\d+/)?.[0] || "";
  const fetchMatch = raw.match(/拉取完成：邮件\s*(\d+)，[^\d]*(\d+)/);
  if (raw.includes("拉取完成")) {
    const fetched = fetchMatch?.[1] || firstNumber || "0";
    const failed = Number(fetchMatch?.[2] || 0);
    return failed > 0 ? `${completeLabel} ${fetched} 封 / 失败 ${failed}` : `${completeLabel} ${fetched} 封`;
  }

  const readMatch = raw.match(/已读取\s*(\d+)\s*个账号/);
  if (readMatch) {
    return `${readLabel} ${readMatch[1]} 个`;
  }

  if (raw.includes("正在拉取")) {
    return "拉取中";
  }
  if (raw.includes("正在读取")) {
    return "读取中";
  }

  if (tone === "error" || raw.endsWith("失败")) {
    const action = raw.replace(/失败$/, "").replace(/^账号/, "").trim() || "操作";
    return `${failLabel} ${action}`;
  }

  return raw.length > 8 ? `${raw.slice(0, 7)}…` : raw;
}

function setStatus(text, tone = "ready") {
  const safeTone = ["ready", "busy", "success", "error", "warning"].includes(tone) ? tone : "ready";
  text = String(text ?? "");
  if (el.statusLine) {
    el.statusLine.textContent = text;
    el.statusLine.dataset.fullStatus = text;
    el.statusLine.dataset.compactStatus = compactStatusText(text, safeTone);
    el.statusLine.title = text;
  }
  if (!el.statusModule) {
    return;
  }
  el.statusModule.dataset.status = safeTone;
  el.statusModule.setAttribute("aria-label", `系统状态：${text}`);
  el.statusModule.classList.remove("is-ready", "is-busy", "is-success", "is-error", "is-warning");
  el.statusModule.classList.add(`is-${safeTone}`);
}

function inspectAccountText(value) {
  const lines = String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  let validLines = 0;
  let invalidLines = 0;
  for (const line of lines) {
    const parts = line.split("----").map((part) => part.trim());
    const looksValid = parts.length === 4
      && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(parts[0] || "")
      && parts.slice(1).every(Boolean);
    if (looksValid) {
      validLines += 1;
    } else {
      invalidLines += 1;
    }
  }
  return {
    totalLines: lines.length,
    validLines,
    invalidLines,
    quality: lines.length === 0 ? 0 : Math.round((validLines / lines.length) * 100),
  };
}

function renderInputQuality() {
  const report = inspectAccountText(el.accountTextInput.value);
  if (!state.accounts.length && el.accountCount) {
    el.accountCount.textContent = report.totalLines ? `${report.totalLines} 行待解析` : "0 个账号";
  }
  if (!el.inputQuality) {
    return;
  }
  const tone = report.totalLines === 0 ? "idle" : report.invalidLines ? "warn" : "good";
  const hint = report.totalLines === 0
    ? "粘贴后会自动读取账号。"
    : report.invalidLines
      ? `${report.invalidLines} 行格式需要检查`
      : "格式完整后会自动读取账号。";
  el.inputQuality.innerHTML = `
    <div class="quality-meter" aria-hidden="true">
      <span style="width: ${escapeHtml(report.quality)}%"></span>
    </div>
    <div class="quality-copy">
      <span class="quality-chip is-${tone}">${report.totalLines ? `${escapeHtml(report.validLines)} / ${escapeHtml(report.totalLines)} 行有效` : "等待输入"}</span>
      <span>${escapeHtml(hint)}</span>
    </div>
  `;
}

function clearScheduledAccountParse() {
  if (autoParseTimer) {
    window.clearTimeout(autoParseTimer);
    autoParseTimer = null;
  }
}

function shouldAutoParseAccountText() {
  const report = inspectAccountText(el.accountTextInput.value);
  return report.totalLines > 0 && report.invalidLines === 0;
}

function hasAccountSessionState() {
  return state.busy
    || state.accounts.length > 0
    || state.accountStatus.size > 0
    || state.failedRows.length > 0
    || state.messagesByAccount.size > 0
    || Boolean(state.selectedMessageKey || state.selectedAccountEmail || state.activeAccountEmail || state.parsedText);
}

function scheduleAccountParse() {
  clearScheduledAccountParse();
  if (!shouldAutoParseAccountText()) {
    const report = inspectAccountText(el.accountTextInput.value);
    if (hasAccountSessionState()) {
      rejectInvalidAccountInput(report);
    }
    return;
  }
  const scheduledText = el.accountTextInput.value.trim();
  if (state.accounts.length && state.parsedText === scheduledText) {
    return;
  }
  autoParseTimer = window.setTimeout(() => {
    autoParseTimer = null;
    if (el.accountTextInput.value.trim() !== scheduledText) {
      scheduleAccountParse();
      return;
    }
    parseInput({ source: "auto" });
  }, AUTO_PARSE_DELAY_MS);
}

function hasAccountInput() {
  return Boolean(el.accountTextInput.value.trim());
}

function hasValidAccountInput() {
  const report = inspectAccountText(el.accountTextInput.value);
  return report.totalLines > 0 && report.invalidLines === 0;
}

function resetAccountPrivacyWhenEmpty() {
  if (!hasAccountInput()) {
    state.accountPrivacy = true;
  }
}

function syncAccountPrivacy() {
  const hasInput = hasAccountInput();
  el.accountTextInput.dataset.private = String(state.accountPrivacy && hasAccountInput());
  el.privacyToggle.disabled = !hasInput;
  el.privacyToggle.setAttribute("aria-disabled", String(!hasInput));
  el.privacyToggle.setAttribute("aria-pressed", String(state.accountPrivacy));
  el.privacyToggle.textContent = !hasInput ? "隐私保护" : state.accountPrivacy ? "显示原文" : "隐藏敏感字段";
  el.privacyToggle.title = !hasInput ? "输入后自动遮蔽敏感字段" : state.accountPrivacy ? "临时显示粘贴的账号原文" : "遮蔽密码、客户端 ID 与刷新令牌";
}

function syncActionAvailability() {
  const hasInput = hasAccountInput();
  const hasValidInput = hasValidAccountInput();
  for (const button of [
    el.fetchBtn,
  ].filter(Boolean)) {
    button.setAttribute("aria-busy", String(state.busy));
    button.classList.toggle("is-busy", state.busy);
    button.disabled = state.busy || !hasValidInput;
    button.setAttribute("aria-disabled", String(state.busy || !hasValidInput));
    button.title = !hasInput ? "请先粘贴账号信息" : hasValidInput ? "" : "请检查账号格式";
  }
  syncFetchScopeControls();
}

function setBusy(busy, text = "") {
  state.busy = busy;
  for (const button of [
    el.fetchBtn,
  ].filter(Boolean)) {
    button.setAttribute("aria-busy", String(busy));
    button.classList.toggle("is-busy", busy);
  }
  syncActionAvailability();
  if (text) {
    setStatus(text, "busy");
  }
}

function payloadBase() {
  const accountText = el.accountTextInput.value.trim();
  if (!accountText) {
    throw new Error("请先粘贴账号信息");
  }
  if (!hasValidAccountInput()) {
    throw new Error("请检查账号格式");
  }
  return {
    account_text: accountText,
  };
}

function normalizeLimit(value) {
  const numericValue = Number.parseInt(value, 10);
  if (!Number.isFinite(numericValue)) {
    return 1;
  }
  return Math.min(100, Math.max(0, numericValue));
}

function ensureSelectedAccount(accounts = state.accounts) {
  if (!accounts.length) {
    state.selectedAccountEmail = "";
    return "";
  }
  const selectedStillExists = accounts.some((account) => account.email === state.selectedAccountEmail);
  if (!selectedStillExists) {
    state.selectedAccountEmail = accounts[0].email;
  }
  return state.selectedAccountEmail;
}

function messagesForAccount(email) {
  return state.messagesByAccount.get(email) || [];
}

function allSessionMessages() {
  return Array.from(state.messagesByAccount.values()).flat();
}

function visibleMessages() {
  return state.activeAccountEmail ? messagesForAccount(state.activeAccountEmail) : allSessionMessages();
}

function ensureActiveAccount(accounts = state.accounts) {
  if (!accounts.length) {
    state.activeAccountEmail = "";
    return "";
  }
  const activeStillExists = accounts.some((account) => account.email === state.activeAccountEmail);
  if (!activeStillExists) {
    const firstAccountWithMessages = accounts.find((account) => messagesForAccount(account.email).length);
    state.activeAccountEmail = firstAccountWithMessages?.email || ensureSelectedAccount(accounts) || accounts[0].email;
  }
  return state.activeAccountEmail;
}

function selectedFetchAccountEmail() {
  if (state.fetchScope !== "selected") {
    return "";
  }
  return ensureSelectedAccount();
}

function scopeDescription() {
  const limit = normalizeLimit(el.limitInput?.value);
  const rawMode = Boolean(el.rawFetchToggle?.checked);
  const rawCopy = rawMode ? "已开启完整原文下载，速度会变慢。" : "快速预览模式，每封最多取 16KB。";
  const rawCompact = rawMode ? "完整原文" : "快速预览";
  if (!state.accounts.length) {
    return {
      label: "会话模式",
      full: `先粘贴账号；解析完成后默认使用当前账号，避免一次拉取全部账号。${rawCopy}`,
      compact: `先解析账号 · 默认单号 · ${rawCompact}`,
    };
  }
  if (state.fetchScope === "all") {
    const possibleTotal = state.accounts.length * limit;
    return {
      label: "当前范围",
      full: `全部 ${state.accounts.length} 个账号；每账号最多 ${limit} 封，预计最多 ${possibleTotal} 封。${rawCopy}`,
      compact: `全部 ${state.accounts.length} 号 · 最多 ${possibleTotal} 封 · ${rawCompact}`,
    };
  }
  const selected = ensureSelectedAccount();
  return {
    label: "当前范围",
    full: `当前账号 ${selected}；每账号最多 ${limit} 封。${rawCopy}`,
    compact: `${selected || "未选择"} · 最多 ${limit} 封 · ${rawCompact}`,
  };
}

function syncFetchScopeControls() {
  const hasAccounts = state.accounts.length > 0;
  const isSelectedScope = state.fetchScope === "selected";
  const controlsDisabled = state.busy || !hasAccounts;
  if (el.selectedScopeBtn) {
    el.selectedScopeBtn.classList.toggle("is-active", isSelectedScope);
    el.selectedScopeBtn.setAttribute("aria-pressed", String(isSelectedScope));
    el.selectedScopeBtn.disabled = controlsDisabled;
    el.selectedScopeBtn.setAttribute("aria-disabled", String(controlsDisabled));
  }
  if (el.allScopeBtn) {
    el.allScopeBtn.classList.toggle("is-active", !isSelectedScope);
    el.allScopeBtn.setAttribute("aria-pressed", String(!isSelectedScope));
    el.allScopeBtn.disabled = controlsDisabled;
    el.allScopeBtn.setAttribute("aria-disabled", String(controlsDisabled));
  }
  if (el.operationNote) {
    const description = scopeDescription();
    el.operationNote.title = description.full;
    el.operationNote.setAttribute("aria-label", `${description.label}：${description.full}`);
    el.operationNote.innerHTML = `
      <span>${escapeHtml(description.label)}</span>
      <strong>
        <span class="operation-note-full">${escapeHtml(description.full)}</span>
        <span class="operation-note-compact" aria-hidden="true">${escapeHtml(description.compact)}</span>
      </strong>
    `;
  }
}

function setFetchScope(scope) {
  state.fetchScope = scope === "all" ? "all" : "selected";
  syncFetchScopeControls();
}

function selectAccount(email) {
  state.activeAccountEmail = email;
  state.selectedAccountEmail = email;
  state.selectedMessageKey = null;
  renderAccounts(state.accounts);
  renderResults(visibleMessages());
  selectInitialMessage(visibleMessages());
  syncFetchScopeControls();
  setStatus("已选择账号", "ready");
}

function actionPayload(accountEmail = selectedFetchAccountEmail()) {
  const payload = {
    ...payloadBase(),
    mailbox: el.mailboxInput.value.trim() || "INBOX",
    limit: normalizeLimit(el.limitInput.value),
  };
  if (el.rawFetchToggle?.checked) {
    payload.include_raw = true;
  }
  const selectedAccountEmail = accountEmail;
  if (selectedAccountEmail) {
    payload.account = selectedAccountEmail;
  }
  return payload;
}

function syncLogActions() {
  const hasLogs = Boolean(el.runLog?.children.length);
  el.clearLogBtn.disabled = !hasLogs;
  el.clearLogBtn.setAttribute("aria-disabled", String(!hasLogs));
  el.clearLogBtn.title = hasLogs ? "清空当前运行记录" : "暂无运行记录";
  el.logDrawerToggle.classList.toggle("has-log-events", hasLogs);
  el.logDrawerToggle.setAttribute("aria-label", hasLogs ? `查看运行日志，${el.runLog.children.length} 条记录` : "查看运行日志");
}

function focusRunLog() {
  if (!el.runLog) {
    return;
  }
  if (!el.runLog.hasAttribute("tabindex")) {
    el.runLog.setAttribute("tabindex", "-1");
  }
  el.runLog.scrollIntoView({ block: "nearest", behavior: "smooth" });
  el.runLog.focus({ preventScroll: true });
}

function splitLogMessage(message) {
  const raw = String(message || "").trim();
  const match = raw.match(/^([^：:]{2,72})\s*[：:]\s*(.+)$/);
  if (!match) {
    return {
      context: "",
      detail: raw || "事件已记录",
    };
  }
  return {
    context: match[1].trim(),
    detail: match[2].trim() || raw,
  };
}

function addLog(message, kind = "") {
  const row = document.createElement("div");
  const level = kind === "fail" ? "错误" : kind === "ok" ? "成功" : "信息";
  const logParts = splitLogMessage(message);
  const timestamp = new Date();
  const displayTime = timestamp.toLocaleTimeString();
  const contextLabel = logParts.context || "会话事件";
  row.className = `activity-event ${kind || "info"}`.trim();
  row.setAttribute("role", "listitem");
  row.setAttribute("aria-label", `${level}，${displayTime}，${contextLabel}，${logParts.detail}`);
  row.innerHTML = `
    <div class="activity-event-body">
      <div class="activity-event-meta">
        <span class="activity-event-kind">${escapeHtml(level)}</span>
        <strong class="activity-event-account ${logParts.context ? "" : "is-muted"}" title="${escapeHtml(contextLabel)}">${escapeHtml(contextLabel)}</strong>
        <time class="activity-event-time" datetime="${escapeHtml(timestamp.toISOString())}">${escapeHtml(displayTime)}</time>
      </div>
      <span class="activity-event-message" title="${escapeHtml(logParts.detail)}">${escapeHtml(logParts.detail)}</span>
    </div>
  `;
  el.runLog.prepend(row);
  syncLogActions();
}

function appendLog(message, kind = "") {
  addLog(message, kind);
}

function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.inset = "0 auto auto 0";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  try {
    if (!document.execCommand("copy")) {
      throw new Error("copy command returned false");
    }
  } finally {
    textarea.remove();
  }
}

async function writeClipboardText(email) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(email);
    return;
  }
  fallbackCopyText(email);
}

async function copyAccountEmail(email) {
  try {
    await writeClipboardText(email);
    setStatus("已复制邮箱账号", "success");
    appendLog(`已复制 ${email}`, "ok");
  } catch (error) {
    setStatus("复制失败", "error");
    appendLog(`复制失败：${error.message}`, "fail");
  }
}

async function copyFailureSummary() {
  try {
    await writeClipboardText(failureSummaryText());
    setStatus("已复制错误摘要", "success");
    appendLog("已复制错误摘要", "ok");
  } catch (error) {
    setStatus("复制错误摘要失败", "error");
    appendLog(`复制错误摘要失败：${error.message}`, "fail");
  }
}

function renderOperationCodeSummary(currentMail) {
  if (!el.currentCodeSummary) {
    return;
  }
  const verification = currentMail ? extractVerificationCode(currentMail) : { code: "", source: "等待邮件", confidence: "none" };
  const currentCode = verification.code;
  const hasCode = Boolean(currentCode);
  const title = currentCode || (currentMail ? "未识别验证码" : "等待邮件");
  const providerPrefix = verification.providerLabel ? `${verification.providerLabel} · ` : "";
  const detail = currentMail
    ? `${providerPrefix}${verification.source} · ${confidenceLabel(verification.confidence)}`
    : "拉取后随选中邮件更新";

  el.currentCodeSummary.className = "operation-code-summary operation-verification-card verification-card";
  el.currentCodeSummary.classList.toggle("has-code", hasCode);
  el.currentCodeSummary.classList.toggle("is-empty", !currentMail);
  el.currentCodeSummary.title = currentCode ? `验证码摘要 ${currentCode}` : title;
  el.currentCodeSummary.setAttribute("aria-label", currentCode ? `验证码摘要：${currentCode}，${detail}` : `验证码摘要：${title}，${detail}`);
  el.currentCodeSummary.innerHTML = `
    <div class="verification-card-copy">
      <span class="verification-eyebrow">验证码摘要</span>
      <strong class="verification-code-value" title="${currentCode ? escapeHtml(currentCode) : escapeHtml(title)}">${escapeHtml(title)}</strong>
      <span class="verification-source">${escapeHtml(detail)}</span>
    </div>
    <button type="button" class="button secondary copy-current-code-inline" data-code-action="copy-current" ${hasCode ? "" : "disabled aria-disabled=\"true\""}>
      复制验证码
    </button>
  `;
  el.currentCodeSummary.querySelector("[data-code-action=\"copy-current\"]")?.addEventListener("click", copyCurrentVerificationCode);
}

function syncSessionActions() {
  renderOperationCodeSummary(selectedMail());
}

async function copyCurrentVerificationCode() {
  const mail = selectedMail();
  const verification = mail ? extractVerificationCode(mail) : { code: "" };
  if (!verification.code) {
    setStatus("未识别验证码", "warning");
    return;
  }
  try {
    await writeClipboardText(verification.code);
    setStatus("已复制当前验证码", "success");
    appendLog(`验证码已复制：${mail.account_email || "当前邮件"}`, "ok");
  } catch (error) {
    setStatus("复制验证码失败", "error");
    appendLog(`复制验证码失败：${error.message}`, "fail");
  }
}

async function retryFailedAccounts() {
  const failedEmails = state.failedRows.map((row) => row.email).filter(Boolean);
  if (!failedEmails.length) {
    setStatus("暂无失败账号", "ready");
    return;
  }
  const operationToken = mailOperationGate.tryStart();
  if (operationToken === null) {
    return;
  }
  const operationRevision = sessionRequests.currentRevision();
  let pendingEmail = "";
  try {
    const parsed = await ensureParsed();
    if (!parsed || !sessionRequests.isCurrent(operationRevision)) {
      return;
    }
    setBusy(true, "正在重试失败账号");
    const summary = { fetched: 0, failed: 0 };
    for (const email of failedEmails) {
      const account = state.accounts.find((item) => item.email === email);
      if (!account) {
        continue;
      }
      state.accountStatus.set(email, { kind: "busy" });
      renderAccounts(state.accounts);
      setStatus(`正在重试 ${email}`, "busy");
      pendingEmail = account.email;
      const accountData = await fetchOneAccount(account);
      if (!sessionRequests.isCurrent(operationRevision)) {
        return;
      }
      pendingEmail = "";
      renderFetchResult(accountData);
      summary.fetched += accountData.fetched;
      summary.failed += accountData.failed;
    }
    setStatus(`重试完成：邮件 ${summary.fetched}，失败 ${summary.failed}`, summary.failed ? "warning" : "success");
  } catch (error) {
    if (requestIsStale(operationRevision, error)) {
      return;
    }
    if (pendingEmail) {
      recordRequestFailure(pendingEmail, error);
    }
    addLog(`重试失败：${error.message}`, "fail");
    setStatus("重试失败", "error");
  } finally {
    if (mailOperationGate.finish(operationToken) && sessionRequests.isCurrent(operationRevision)) {
      setBusy(false);
      syncSessionActions();
    }
  }
}

function toggleLogDrawer() {
  const panel = document.querySelector(".run-log-panel");
  const nextOpen = !panel?.classList.contains("is-open");
  panel?.classList.toggle("is-open", nextOpen);
  panel?.classList.toggle("is-collapsed", !nextOpen);
  el.logDrawerToggle?.setAttribute("aria-expanded", String(nextOpen));
  if (el.logDrawerToggle) {
    el.logDrawerToggle.textContent = nextOpen ? "收起" : "日志";
  }
}

function mailEmptyIconMarkup() {
  return `<span class="mail-empty-icon"><svg class="icon" aria-hidden="true"><use href="#icon-outlook"></use></svg></span>`;
}

function mailListEmptyMarkup() {
  return `
    <div class="mail-empty-panel mail-list-empty-state" aria-label="空邮件列表引导">
      <div class="mail-empty-copy">
        ${mailEmptyIconMarkup()}
        <div>
          <strong>等待邮件</strong>
          <span>拉取后显示邮件与验证码。</span>
        </div>
      </div>
      <div class="mail-empty-rows" aria-hidden="true">
        <div class="mail-empty-row is-preview-selected">
          <span class="mail-row-status-dot"></span>
          <div>
            <span class="mail-empty-row-subject"></span>
            <span class="mail-empty-row-meta"></span>
          </div>
          <span class="mail-empty-row-time"></span>
        </div>
        <div class="mail-empty-row is-muted">
          <span class="mail-row-status-dot"></span>
          <div>
            <span class="mail-empty-row-subject"></span>
            <span class="mail-empty-row-meta"></span>
          </div>
          <span class="mail-empty-row-time"></span>
        </div>
        <div class="mail-empty-row is-muted">
          <span class="mail-row-status-dot"></span>
          <div>
            <span class="mail-empty-row-subject"></span>
            <span class="mail-empty-row-meta"></span>
          </div>
          <span class="mail-empty-row-time"></span>
        </div>
      </div>
    </div>
  `;
}

function mailReaderPlaceholderMarkup(title = "邮件详情", description = "选中邮件后显示正文和验证码摘要。") {
  return `
    <div class="mail-detail-placeholder mail-empty-hero" aria-label="阅读区占位预览">
      ${mailEmptyIconMarkup()}
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(description)}</span>
      <div class="placeholder-reader-frame" aria-hidden="true">
        <div class="placeholder-meta-grid">
          <span>当前会话预览</span>
          <span>关键头信息</span>
        </div>
        <div class="placeholder-line"></div>
        <div class="placeholder-line short"></div>
      </div>
    </div>
  `;
}

function renderMailDetailPlaceholder() {
  setMailBusyState(false);
  el.mailDetail.innerHTML = mailReaderPlaceholderMarkup();
}

function setMailBusyState(isBusy) {
  if (isBusy) {
    el.mailList.setAttribute("aria-busy", "true");
    el.mailDetail.setAttribute("aria-busy", "true");
  } else {
    el.mailList.removeAttribute("aria-busy");
    el.mailDetail.removeAttribute("aria-busy");
  }
}

function syncMailListSemantics(isPopulated) {
  el.mailList.removeAttribute("aria-activedescendant");
  if (isPopulated) {
    el.mailList.setAttribute("role", "listbox");
    el.mailList.setAttribute("aria-label", "邮件列表");
    return;
  }
  state.selectedMessageKey = null;
  el.mailList.removeAttribute("role");
  el.mailList.removeAttribute("aria-label");
}

function mailSkeletonRowMarkup(tone = "") {
  return `
    <div class="mail-skeleton-row ${tone}" aria-hidden="true">
      <span class="mail-skeleton-dot"></span>
      <div class="mail-skeleton-copy">
        <span class="skeleton-text-line is-strong"></span>
        <span class="skeleton-text-line is-medium"></span>
        <span class="skeleton-text-line is-short"></span>
      </div>
      <span class="mail-skeleton-meta"></span>
    </div>
  `;
}

function mailLoadingRailMarkup() {
  return `
    <div class="mail-loading-rail" aria-hidden="true">
      <span class="mail-loading-step is-active"><i></i>连接账号</span>
      <span class="mail-loading-step"><i></i>同步邮件</span>
      <span class="mail-loading-step"><i></i>准备阅读区</span>
    </div>
  `;
}

function mailErrorDetailMarkup(detail) {
  const insight = failureInsight(detail);
  return `
    <div class="mail-error-detail" aria-label="错误详情">
      <span>${escapeHtml(insight.title)}</span>
      <strong class="mail-error-code">${escapeHtml(insight.summary)}</strong>
      <p class="mail-error-next-step">${escapeHtml(insight.nextStep)}</p>
      <details class="mail-error-technical">
        <summary>查看技术详情</summary>
        <code>${escapeHtml(insight.detail)}</code>
      </details>
    </div>
  `;
}

function mailErrorDiagnosticsMarkup(detail) {
  const insight = failureInsight(detail);
  return `
    <div class="mail-error-diagnostics" aria-label="恢复建议">
      <div class="mail-error-diagnostic-item">
        <span>恢复建议</span>
        <strong title="重新授权或调整账号后重试">${escapeHtml(insight.nextStep)}</strong>
      </div>
      <div class="mail-error-diagnostic-item">
        <span>保留运行记录</span>
        <strong>失败上下文已写入事件流</strong>
      </div>
    </div>
  `;
}

function mailErrorActionsMarkup() {
  return `
    <div class="mail-error-actions">
      <button type="button" class="button secondary mail-error-retry">
        <svg class="icon" aria-hidden="true"><use href="#icon-play"></use></svg>
        重新拉取失败账号
      </button>
      <button type="button" class="button ghost mail-error-copy">
        复制错误摘要
      </button>
      <button type="button" class="button ghost mail-error-log-link">
        查看运行记录
      </button>
    </div>
  `;
}

function renderMailLoadingState(label) {
  renderMailSummary([], { kind: "loading", label });
  setMailBusyState(true);
  syncMailListSemantics(false);
  el.mailList.classList.remove("empty");
  el.mailList.innerHTML = `
    <div class="mail-loading-state" role="status" aria-live="polite" aria-busy="true" aria-label="${escapeHtml(label)}">
      <div class="mail-loading-header">
        <span class="mail-loading-orb" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span>正在建立连接、同步摘要并准备阅读区。</span>
        </div>
      </div>
      ${mailLoadingRailMarkup()}
      <div class="mail-loading-list" aria-hidden="true">
        ${mailSkeletonRowMarkup("is-primary")}
        ${mailSkeletonRowMarkup("is-muted")}
        ${mailSkeletonRowMarkup("")}
      </div>
    </div>
  `;
  el.mailDetail.innerHTML = `
    <div class="mail-detail-loading" role="status" aria-live="polite" aria-busy="true" aria-label="${escapeHtml(label)}详情骨架">
      <div class="detail-loading-status">
        <span class="mail-loading-orb" aria-hidden="true"></span>
        <div>
          <strong>准备阅读区</strong>
          <span>保持详情布局稳定，邮件到达后自动展开正文预览。</span>
        </div>
      </div>
      <div class="detail-skeleton-header" aria-hidden="true">
        <span class="skeleton-text-line is-title"></span>
        <span class="skeleton-text-line is-meta"></span>
      </div>
      <div class="detail-skeleton-summary" aria-hidden="true">
        <span class="detail-skeleton-block"><i></i><b></b></span>
        <span class="detail-skeleton-block"><i></i><b></b></span>
        <span class="detail-skeleton-block"><i></i><b></b></span>
      </div>
      <div class="reader-toolbar reader-toolbar-skeleton" aria-hidden="true">
        <span class="reader-stat skeleton-chip"></span>
        <span class="reader-stat skeleton-chip"></span>
        <span class="reader-stat skeleton-chip"></span>
      </div>
      <div class="detail-meta-card sender-identity-card sender-skeleton-card" aria-hidden="true">
        <span class="sender-avatar skeleton-avatar"></span>
        <div class="sender-copy">
          <span class="skeleton-text-line is-strong"></span>
          <span class="skeleton-text-line is-medium"></span>
          <span class="skeleton-text-line is-short"></span>
        </div>
      </div>
      <section class="body-card body-skeleton-card" aria-hidden="true">
        <div class="body-card-title"><span class="skeleton-text-line is-label"></span></div>
        <div class="body-skeleton-lines">
          <span class="skeleton-text-line"></span>
          <span class="skeleton-text-line"></span>
          <span class="skeleton-text-line is-medium"></span>
        </div>
      </section>
    </div>
  `;
}

function renderMailErrorState(message) {
  const detail = message || "IMAP 拉取未完成";
  const insight = failureInsight(detail);
  setMailBusyState(false);
  renderMailSummary([], { kind: "error", label: insight.title, description: `${insight.summary} ${insight.nextStep}` });
  syncMailListSemantics(false);
  el.mailList.classList.add("empty");
  el.mailList.innerHTML = `
    <div class="mail-error-state mail-error-compact" role="status" aria-label="邮件拉取失败">
      <div class="mail-error-compact-card">
        <span class="mail-empty-icon is-error"><svg class="icon" aria-hidden="true"><use href="#icon-clear"></use></svg></span>
        <div>
          <strong>${escapeHtml(insight.title)}</strong>
          <span>查看详情面板或运行记录，调整后可重新拉取。</span>
        </div>
      </div>
      ${mailErrorDetailMarkup(detail)}
      ${mailErrorActionsMarkup()}
    </div>
  `;
  el.mailDetail.innerHTML = `
    <div class="mail-detail-placeholder mail-error-panel" aria-label="拉取失败详情">
      <span class="mail-empty-icon is-error"><svg class="icon" aria-hidden="true"><use href="#icon-clear"></use></svg></span>
      <strong>${escapeHtml(insight.title)}</strong>
      <span>${escapeHtml(insight.summary)}</span>
      ${mailErrorDiagnosticsMarkup(detail)}
      ${mailErrorDetailMarkup(detail)}
      ${mailErrorActionsMarkup()}
    </div>
  `;
  for (const button of [
    ...el.mailList.querySelectorAll(".mail-error-retry"),
    ...el.mailDetail.querySelectorAll(".mail-error-retry"),
  ]) {
    wireMailErrorRetryButton(button);
  }
  for (const button of [
    ...el.mailList.querySelectorAll(".mail-error-copy"),
    ...el.mailDetail.querySelectorAll(".mail-error-copy"),
  ]) {
    button.addEventListener("click", copyFailureSummary);
  }
  for (const button of [
    ...el.mailList.querySelectorAll(".mail-error-log-link"),
    ...el.mailDetail.querySelectorAll(".mail-error-log-link"),
  ]) {
    button.addEventListener("click", focusRunLog);
  }
}

function wireMailErrorRetryButton(button) {
  if (state.failedRows.length) {
    button.addEventListener("click", retryFailedAccounts);
  } else {
    button.addEventListener("click", fetchMail);
  }
}

function resetSessionResults() {
  state.failedRows = [];
  state.messagesByAccount.clear();
  state.selectedMessageKey = null;
  state.activeAccountEmail = "";
  renderResults([]);
  renderMailDetailPlaceholder();
}

function statusStageLabel(stage) {
  const labels = {
    request: "请求",
    oauth: "OAuth",
    fetch: "拉取",
    auth: "认证",
    select: "选目录",
    parse: "解析",
    connect: "连接",
  };
  return labels[stage] || "处理";
}

function statusPill(account) {
  const status = state.accountStatus.get(account.email);
  if (!status) {
    return `<span class="pill">待拉取</span>`;
  }
  if (status.kind === "busy") {
    return `<span class="pill">拉取中</span>`;
  }
  if (status.kind === "fetch") {
    return `<span class="pill ok" title="${escapeHtml(accountStatusLabel(status))}">已拉取 · ${escapeHtml(status.fetched)} 封 · ${escapeHtml(formatElapsedTime(status.elapsed_ms))}</span>`;
  }
  return `<span class="pill fail" title="${escapeHtml(accountStatusLabel(status))}">失败 · ${escapeHtml(statusStageLabel(status.stage))} · ${escapeHtml(formatElapsedTime(status.elapsed_ms))}</span>`;
}

function accountStatusLabel(status) {
  if (!status) {
    return "待拉取";
  }
  if (status.kind === "busy") {
    return "拉取中";
  }
  if (status.kind === "fetch") {
    return `已拉取，${status.fetched} 封，耗时 ${formatElapsedTime(status.elapsed_ms)}`;
  }
  const insight = failureInsight(status.error, status.stage);
  return `失败，${statusStageLabel(status.stage)}，耗时 ${formatElapsedTime(status.elapsed_ms)}，${insight.title}：${insight.summary}`;
}

function accountFailureCount() {
  return Array.from(state.accountStatus.values()).filter((status) => status?.kind === "fail").length;
}

function resultAccountCount(results) {
  return new Set(results.map((mail) => mail.account_email).filter(Boolean)).size;
}

function syncInitialEmptyLayout(accounts) {
  const hasInput = hasAccountInput();
  const hasSessionMessages = allSessionMessages().length > 0;
  const hasSessionState = Boolean(state.accountStatus.size || hasSessionMessages || state.failedRows.length);
  const isInitialEmpty = !accounts.length && !hasInput;
  const isPreflight = hasInput && !accounts.length && !hasSessionState;
  const shouldKeepAccountCompact = hasSessionState || !hasSessionMessages;
  const isAccountCompact = hasInput && accounts.length > 0 && shouldKeepAccountCompact;
  el.controlColumn?.classList.toggle("is-initial-empty", isInitialEmpty);
  el.controlColumn?.classList.toggle("is-preflight", isPreflight);
  el.controlColumn?.classList.toggle("is-account-compact", isAccountCompact);
  el.accountInputPanel?.classList.toggle("is-initial-empty", isInitialEmpty);
  el.accountInputPanel?.classList.toggle("is-preflight", isPreflight);
  el.accountInputPanel?.classList.toggle("is-account-compact", isAccountCompact);
  el.accountList?.classList.toggle("is-empty", !accounts.length);
}

function renderAccounts(accounts) {
  state.accounts = accounts;
  ensureSelectedAccount(accounts);
  ensureActiveAccount(accounts);
  el.accountCount.textContent = `${accounts.length} 个账号`;
  el.accountList.innerHTML = "";
  syncInitialEmptyLayout(accounts);
  syncFetchScopeControls();

  if (!accounts.length) {
    const report = inspectAccountText(el.accountTextInput?.value || "");
    if (report.totalLines) {
      const pendingHint = report.invalidLines
        ? `${report.invalidLines} 行格式需要检查`
        : "格式完整，准备读取账号状态。";
      el.accountList.innerHTML = `
        <div class="account-empty-panel account-pending-panel" aria-label="账号等待解析">
          <strong>${escapeHtml(report.totalLines)} 行等待解析</strong>
          <span>${escapeHtml(pendingHint)}</span>
          <div class="account-empty-guide" aria-hidden="true">
            <span class="account-empty-chip">待读取</span>
            <span class="account-empty-chip">格式检查</span>
            <span class="account-empty-chip">只显示邮箱</span>
          </div>
        </div>
      `;
      return;
    }
    el.accountList.innerHTML = `
      <div class="account-empty-panel" aria-label="账号状态待命">
        <strong>等待账号</strong>
        <span>粘贴后自动读取账号状态。</span>
        <div class="account-empty-guide" aria-hidden="true">
          <span class="account-empty-chip">自动读取</span>
          <span class="account-empty-chip">隐私保护</span>
        </div>
      </div>
    `;
    return;
  }

  for (const account of accounts) {
    const status = state.accountStatus.get(account.email);
    const isSelected = account.email === state.activeAccountEmail;
    const row = document.createElement("div");
    row.dataset.accountEmail = account.email;
    row.className = `account-row ${isSelected ? "is-selected" : ""}`.trim();
    const statusLabel = accountStatusLabel(status);
    row.title = status ? `${account.email}：${statusLabel}` : account.email;
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "copy-account-button account-copy-zone";
    copyButton.innerHTML = `
      <span class="copy-account-icon" aria-hidden="true"><svg class="icon"><use href="#icon-copy"></use></svg></span>
    `;
    copyButton.title = `复制邮箱账号 ${account.email}`;
    copyButton.setAttribute("aria-label", `复制邮箱账号 ${account.email}`);
    copyButton.addEventListener("click", (event) => {
      event.stopPropagation();
      copyAccountEmail(account.email);
    });
    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "account-select-button account-status-button";
    selectButton.title = `选择账号 ${account.email}`;
    selectButton.setAttribute("aria-label", `${account.email}，${isSelected ? "当前选中，" : ""}${failureAccessibilityLabel(status)}`);
    selectButton.setAttribute("aria-pressed", String(isSelected));
    selectButton.innerHTML = `
      <strong class="account-email-label">${escapeHtml(account.email)}</strong>
      ${statusPill(account)}
    `;
    selectButton.addEventListener("click", () => selectAccount(account.email));
    row.append(copyButton, selectButton);
    el.accountList.append(row);
  }
}

function mergeFetchedMessagesByAccount(rows = [], fetchedMessages = []) {
  const messagesByAccount = new Map();
  for (const mail of fetchedMessages || []) {
    const email = mail.account_email || "";
    if (!email) {
      continue;
    }
    const messages = messagesByAccount.get(email) || [];
    messages.push(mail);
    messagesByAccount.set(email, messages);
  }

  for (const row of rows || []) {
    const email = row.email;
    if (!email) {
      continue;
    }
    state.messagesByAccount.set(email, messagesByAccount.get(email) || []);
  }

  for (const [accountEmail, messages] of messagesByAccount) {
    state.messagesByAccount.set(accountEmail, messages);
  }
}

function renderFetchResult(data) {
  const failedByEmail = new Map(state.failedRows.map((row) => [row.email, row]));
  for (const row of data.rows) {
    if (row.ok) {
      failedByEmail.delete(row.email);
      state.accountStatus.set(row.email, {
        kind: "fetch",
        fetched: row.fetched,
        elapsed_ms: row.elapsed_ms,
        raw_bytes: row.raw_bytes,
        downloaded_bytes: row.downloaded_bytes,
        message_count: row.message_count,
        timings: row.timings || {},
      });
      addLog(`${row.email}: 已拉取 ${row.fetched} 封邮件，耗时 ${formatElapsedTime(row.elapsed_ms)}，下载 ${formatBytes(row.raw_bytes)}，阶段 ${formatTimingBreakdown(row.timings)}`, "ok");
    } else {
      failedByEmail.set(row.email, row);
      state.accountStatus.set(row.email, {
        kind: "fail",
        stage: row.stage || "fetch",
        elapsed_ms: row.elapsed_ms,
        raw_bytes: row.raw_bytes,
        downloaded_bytes: row.downloaded_bytes,
        message_count: row.message_count,
        timings: row.timings || {},
        error: row.error,
      });
      addLog(`${failureLogMessage(row.email, row.error, row.stage)}，耗时 ${formatElapsedTime(row.elapsed_ms)}，下载 ${formatBytes(row.raw_bytes)}，阶段 ${formatTimingBreakdown(row.timings)}`, "fail");
    }
  }
  state.failedRows = Array.from(failedByEmail.values());
  mergeFetchedMessagesByAccount(data.rows, data.messages || []);
  ensureActiveAccount();
  renderAccounts(state.accounts);
  const results = visibleMessages();
  if (!results.length && state.failedRows.length) {
    renderMailErrorState(latestFailureMessage());
  } else {
    renderResults(results);
    selectInitialMessage(results);
  }
}

function renderMailSummary(results, options = {}) {
  const hasResults = Boolean(results.length);
  const summaryState = options.kind || (hasResults ? "ready" : "empty");
  const isLoading = summaryState === "loading";
  const isError = summaryState === "error";
  const failedCount = accountFailureCount();
  const visibleAccountCount = resultAccountCount(results);
  const title = isLoading ? (options.label || "正在拉取邮件") : isError ? (options.label || "拉取失败") : hasResults ? `本次 ${escapeHtml(results.length)} 封` : "等待拉取";
  const description = isLoading ? "正在连接账号并整理本次会话结果。" : isError ? (options.description || "当前会话未能完成拉取，请查看运行记录后重试。") : hasResults ? "选择左侧邮件查看正文和关键头信息。" : "收件箱列表和阅读区会在同一视图内更新。";
  const summaryLabel = isLoading ? "同步状态" : isError ? "错误状态" : hasResults ? "本次拉取摘要" : "待处理摘要";
  const emptyMetrics = `
      <div class="mail-summary-metrics" aria-label="待处理摘要">
        <span class="summary-metric is-muted"><span>状态</span><strong>待命</strong></span>
        <span class="summary-metric is-muted"><span>邮件</span><strong>0</strong></span>
        <span class="summary-metric is-muted"><span>账号</span><strong>${escapeHtml(state.accounts.length)}</strong></span>
      </div>
    `;
  const errorMetrics = `
      <div class="mail-summary-metrics" aria-label="错误状态">
        <span class="summary-metric is-error"><span>状态</span><strong>失败</strong></span>
        <span class="summary-metric is-muted"><span>邮件</span><strong>${escapeHtml(results.length)}</strong></span>
        <span class="summary-metric is-muted"><span>账号</span><strong>${escapeHtml(visibleAccountCount)}</strong></span>
      </div>
    `;
  el.mailSummary.dataset.state = summaryState;
  el.mailSummary.setAttribute("aria-label", summaryLabel);
  el.mailSummary.innerHTML = `
    <div class="mail-summary-copy">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(description)}</span>
    </div>
    ${isLoading ? `
      <div class="mail-summary-metrics" aria-label="同步状态">
        <span class="summary-metric is-loading"><span>状态</span><strong><i class="summary-loading-dot" aria-hidden="true"></i>同步中</strong></span>
      </div>
    ` : isError ? errorMetrics : hasResults ? `
      <div class="mail-summary-metrics" aria-label="本次拉取摘要">
        <span class="summary-metric"><span>邮件</span><strong>${escapeHtml(results.length)}</strong></span>
        <span class="summary-metric"><span>账号</span><strong>${escapeHtml(visibleAccountCount)}</strong></span>
        <span class="summary-metric ${failedCount ? "is-danger" : ""}"><span>受限</span><strong>${escapeHtml(failedCount)}</strong></span>
      </div>
    ` : emptyMetrics}
  `;
}

function renderResults(results) {
  setMailBusyState(false);
  el.mailList.innerHTML = "";
  syncMailListSemantics(Boolean(results.length));
  el.mailList.classList.toggle("empty", !results.length);
  renderMailSummary(results);
  if (!results.length) {
    renderMailDetailPlaceholder();
    el.mailList.innerHTML = mailListEmptyMarkup();
    syncSessionActions();
    return;
  }

  for (const [index, mail] of results.entries()) {
    const key = messageKey(mail);
    const preview = readableMailPreview(mail);
    const displayDate = formatMailDate(mail.sent_at);
    const senderName = senderDisplayName(mail.sender);
    const senderAddressText = senderAddress(mail.sender);
    const senderInitialValue = senderInitial(mail.sender);
    const button = document.createElement("button");
    const isSelected = key === state.selectedMessageKey;
    button.type = "button";
    button.dataset.mailId = String(mail.id);
    button.dataset.messageKey = key;
    button.id = `mail-row-${index}`;
    button.className = `mail-row ${isSelected ? "active" : ""}`.trim();
    button.tabIndex = isSelected || (!state.selectedMessageKey && mail === results[0]) ? 0 : -1;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(isSelected));
    button.setAttribute("aria-label", `${mail.subject || "(无主题)"}，${senderName}，${mail.account_email || "未知账号"}，${displayDate}`);
    button.innerHTML = `
      <div class="mail-row-main">
        <span class="mail-row-avatar" aria-hidden="true">${escapeHtml(senderInitialValue)}</span>
        <span class="mail-row-title-group">
          <span class="mail-row-title-line">
            <span class="mail-row-status-dot" aria-hidden="true"></span>
            <strong class="subject">${escapeHtml(mail.subject || "(无主题)")}</strong>
          </span>
          <span class="mail-row-meta-line">
            <span class="mail-row-sender" title="${escapeHtml(senderAddressText)}">${escapeHtml(senderName)}</span>
            <span class="mail-row-account" title="${escapeHtml(mail.account_email || "-")}">${escapeHtml(mail.account_email || "-")}</span>
          </span>
          <span class="mail-row-preview">${escapeHtml(preview)}</span>
        </span>
        <span class="mail-time">${escapeHtml(displayDate)}</span>
      </div>
    `;
    button.addEventListener("click", () => showEmail(key));
    el.mailList.append(button);
  }
  syncSessionActions();
}

function selectInitialMessage(results = visibleMessages()) {
  if (!results.length) {
    return;
  }
  const selectedStillExists = results.some((mail) => messageKey(mail) === state.selectedMessageKey);
  const key = selectedStillExists ? state.selectedMessageKey : messageKey(results[0]);
  showEmail(key, results);
}

function focusSelectedMail() {
  for (const row of el.mailList.querySelectorAll(".mail-row")) {
    if (row.dataset.messageKey === state.selectedMessageKey) {
      row.focus({ preventScroll: true });
      row.scrollIntoView({ block: "nearest" });
      return;
    }
  }
}

function handleMailListKeydown(event) {
  const navigationKeys = ["ArrowDown", "ArrowUp", "Home", "End"];
  const results = visibleMessages();
  if (!navigationKeys.includes(event.key) || !results.length) {
    return;
  }

  event.preventDefault();
  const focusedMessageKey = event.target?.dataset?.messageKey;
  const activeKey = state.selectedMessageKey ?? focusedMessageKey ?? messageKey(results[0]);
  const currentIndex = Math.max(0, results.findIndex((mail) => messageKey(mail) === activeKey));
  let nextIndex = currentIndex;

  if (event.key === "ArrowDown") {
    nextIndex = Math.min(results.length - 1, currentIndex + 1);
  } else if (event.key === "ArrowUp") {
    nextIndex = Math.max(0, currentIndex - 1);
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = results.length - 1;
  }

  showEmail(messageKey(results[nextIndex]), results);
  focusSelectedMail();
}

function confidenceLabel(confidence) {
  if (confidence === "high") {
    return "高置信";
  }
  if (confidence === "medium") {
    return "中置信";
  }
  return "未识别";
}

function verificationCodeCardMarkup(mail) {
  const verification = extractVerificationCode(mail);
  const hasCode = Boolean(verification.code);
  const displayCode = hasCode ? verification.code : "未识别验证码";
  const providerPrefix = verification.providerLabel ? `${verification.providerLabel} · ` : "";
  return `
    <section class="verification-card" aria-label="验证码摘要">
      <div class="verification-card-copy">
        <span class="verification-eyebrow">验证码摘要</span>
        <strong class="verification-code-value" title="${hasCode ? escapeHtml(verification.code) : "未识别验证码"}">${escapeHtml(displayCode)}</strong>
        <span class="verification-source">${escapeHtml(providerPrefix)}${escapeHtml(verification.source)} · ${escapeHtml(confidenceLabel(verification.confidence))}</span>
      </div>
      <button type="button" class="button secondary copy-current-code-inline" data-code-action="copy-current" ${hasCode ? "" : "disabled aria-disabled=\"true\""}>
        复制验证码
      </button>
    </section>
  `;
}

function renderDetail(mail) {
  setMailBusyState(false);
  state.selectedMessageKey = messageKey(mail);
  const readableBody = readableMailText(mail) || "没有可读正文预览。";
  const bodyLength = readableBody.length;
  const displayDate = formatMailDate(mail.sent_at);
  const senderName = senderDisplayName(mail.sender);
  const senderAddressText = senderAddress(mail.sender);
  const senderInitialValue = senderInitial(mail.sender);
  el.mailDetail.innerHTML = `
    <div class="detail-header">
      <div>
        <h2>${escapeHtml(mail.subject || "(无主题)")}</h2>
        <div class="meta detail-meta-line">
          <span>${escapeHtml(senderName)}</span>
          <span>${escapeHtml(displayDate)}</span>
        </div>
      </div>
      <div class="detail-actions">
        <span class="pill">${escapeHtml(mail.mailbox)}</span>
      </div>
    </div>
    ${verificationCodeCardMarkup(mail)}
    <div class="detail-summary-bar" aria-label="邮件摘要">
      <div class="detail-summary-item">
        <span>账号</span>
        <strong title="${escapeHtml(mail.account_email || "-")}">${escapeHtml(mail.account_email || "-")}</strong>
      </div>
      <div class="detail-summary-item">
        <span>目录</span>
        <strong title="${escapeHtml(mail.mailbox || "-")}">${escapeHtml(mail.mailbox || "-")}</strong>
      </div>
      <div class="detail-summary-item">
        <span>时间</span>
        <strong title="${escapeHtml(displayDate)}">${escapeHtml(displayDate)}</strong>
      </div>
    </div>
    <div class="reader-toolbar" aria-label="阅读上下文">
      <span class="reader-stat is-primary">可读正文 · ${escapeHtml(bodyLength)} 字</span>
      <span class="reader-stat-separator" aria-hidden="true">·</span>
      <span class="reader-stat is-safe">正文已净化</span>
      <span class="reader-stat-separator" aria-hidden="true">·</span>
      <span class="reader-stat is-session">当前会话预览</span>
    </div>
    <div class="detail-meta-card sender-identity-card" aria-label="发件人身份信息">
      <div class="sender-avatar" aria-hidden="true">${escapeHtml(senderInitialValue)}</div>
      <div class="sender-copy">
        <div class="sender-copy-head">
          <strong>${escapeHtml(senderName)}</strong>
          <span>${escapeHtml(displayDate)}</span>
        </div>
        <div class="sender-address">${escapeHtml(senderAddressText)}</div>
        <div class="detail-grid sender-route">
          <span>收件人</span><strong title="${escapeHtml(mail.recipients || "-")}">${escapeHtml(mail.recipients || "-")}</strong>
          <span>账号</span><strong title="${escapeHtml(mail.account_email || "-")}">${escapeHtml(mail.account_email || "-")}</strong>
        </div>
      </div>
    </div>
    <section class="body-card">
      <div class="body-card-title">正文预览</div>
      <pre class="body-preview">${escapeHtml(readableBody)}</pre>
    </section>
  `;
  el.mailDetail.querySelector("[data-code-action=\"copy-current\"]")?.addEventListener("click", copyCurrentVerificationCode);
  syncSessionActions();
}

async function loadConfig() {
  const config = await api("/api/config");
  state.config = config;
  if (config.version && el.appVersionBadge) {
    el.appVersionBadge.textContent = `v${config.version}`;
    el.appVersionBadge.title = `当前版本 v${config.version}`;
    el.appVersionBadge.hidden = false;
  }
  el.mailboxInput.value = config.defaults.mailbox;
  el.limitInput.value = normalizeLimit(config.defaults.limit);
  renderAccounts([]);
  renderResults([]);
  renderInputQuality();
  syncActionAvailability();
}

function rejectInvalidAccountInput(report = inspectAccountText(el.accountTextInput.value)) {
  clearScheduledAccountParse();
  sessionRequests.reset();
  state.accountStatus.clear();
  state.selectedAccountEmail = "";
  state.parsedText = "";
  resetSessionResults();
  renderAccounts([]);
  setBusy(false);
  setStatus(report.totalLines ? "账号格式需要检查" : "请先粘贴账号信息", report.totalLines ? "warning" : "ready");
  return false;
}

async function parseInput(options = {}) {
  const source = options.source || "manual";
  const accountText = el.accountTextInput.value.trim();
  const report = inspectAccountText(accountText);
  if (!report.totalLines || report.invalidLines) {
    return rejectInvalidAccountInput(report);
  }
  if (state.accounts.length && state.parsedText === accountText) {
    return true;
  }
  const request = sessionRequests.startRequest();
  setBusy(true, source === "auto" ? "正在自动解析账号" : "正在读取账号");
  try {
    const data = await api("/api/accounts", {
      method: "POST",
      body: JSON.stringify(payloadBase()),
      signal: request.controller.signal,
    });
    if (!sessionRequests.isCurrent(request.revision) || accountText !== el.accountTextInput.value.trim()) {
      return false;
    }
    state.accountStatus.clear();
    state.parsedText = accountText;
    resetSessionResults();
    renderAccounts(data.accounts);
    addLog(source === "auto" ? `账号自动解析完成：${data.count} 个` : `账号读取完成：${data.count} 个`, "ok");
    setStatus(`已读取 ${data.count} 个账号`, "success");
    return true;
  } catch (error) {
    if (requestIsStale(request.revision, error)) {
      return false;
    }
    addLog(error.message, "fail");
    setStatus("账号读取失败", "error");
    return false;
  } finally {
    sessionRequests.finishRequest(request.controller);
    if (sessionRequests.isCurrent(request.revision)) {
      setBusy(false);
    }
  }
}

function accountsToFetch() {
  if (state.fetchScope === "all") {
    return state.accounts;
  }
  const selectedEmail = ensureSelectedAccount();
  return state.accounts.filter((account) => account.email === selectedEmail);
}

async function fetchOneAccount(account) {
  const request = sessionRequests.startRequest();
  try {
    return await api("/api/fetch", {
      method: "POST",
      body: JSON.stringify(actionPayload(account.email)),
      signal: request.controller.signal,
    });
  } finally {
    sessionRequests.finishRequest(request.controller);
  }
}

async function fetchMail() {
  const operationToken = mailOperationGate.tryStart();
  if (operationToken === null) {
    return;
  }
  const operationRevision = sessionRequests.currentRevision();
  let pendingEmail = "";
  try {
    const parsed = await ensureParsed();
    if (!parsed || !sessionRequests.isCurrent(operationRevision)) {
      return;
    }
    setBusy(true, "正在拉取邮件");
    renderMailLoadingState("正在拉取邮件");
    const summary = { fetched: 0, failed: 0 };
    for (const account of accountsToFetch()) {
      state.accountStatus.set(account.email, { kind: "busy" });
      renderAccounts(state.accounts);
      setStatus(`正在拉取 ${account.email}`, "busy");
      pendingEmail = account.email;
      const accountData = await fetchOneAccount(account);
      if (!sessionRequests.isCurrent(operationRevision)) {
        return;
      }
      pendingEmail = "";
      renderFetchResult(accountData);
      summary.fetched += accountData.fetched;
      summary.failed += accountData.failed;
    }
    setStatus(`拉取完成：邮件 ${summary.fetched}，失败 ${summary.failed}`, summary.failed ? "warning" : "success");
  } catch (error) {
    if (requestIsStale(operationRevision, error)) {
      return;
    }
    if (pendingEmail) {
      recordRequestFailure(pendingEmail, error);
    }
    addLog(error.message, "fail");
    const results = visibleMessages();
    if (allSessionMessages().length) {
      renderResults(results);
      selectInitialMessage(results);
      renderMailSummary(results, { kind: "error", label: "拉取失败", description: "已保留当前会话结果，请查看运行记录后重试。" });
    } else {
      renderMailErrorState(error.message);
    }
    setStatus("拉取失败", "error");
  } finally {
    if (mailOperationGate.finish(operationToken) && sessionRequests.isCurrent(operationRevision)) {
      setBusy(false);
      syncSessionActions();
    }
  }
}

async function ensureParsed() {
  clearScheduledAccountParse();
  const report = inspectAccountText(el.accountTextInput.value);
  if (!report.totalLines || report.invalidLines) {
    return rejectInvalidAccountInput(report);
  }
  if (state.accounts.length && state.parsedText === el.accountTextInput.value.trim()) {
    return true;
  }
  const revision = sessionRequests.currentRevision();
  const ok = await parseInput();
  if (!ok && sessionRequests.isCurrent(revision)) {
    throw new Error("账号读取失败");
  }
  return ok;
}

function showEmail(key, results = visibleMessages()) {
  const mail = findMessageByKey(results, key);
  if (!mail) {
    addLog(`邮件不存在：${key}`, "fail");
    return;
  }
  renderDetail(mail);
  for (const row of el.mailList.querySelectorAll(".mail-row")) {
    const isSelected = row.dataset.messageKey === key;
    row.classList.toggle("active", isSelected);
    row.setAttribute("aria-selected", String(isSelected));
    row.tabIndex = isSelected ? 0 : -1;
    if (isSelected) {
      el.mailList.setAttribute("aria-activedescendant", row.id);
    }
  }
}

initTheme();

el.themeToggle.addEventListener("click", toggleTheme);
el.fetchBtn.addEventListener("click", fetchMail);
el.logDrawerToggle?.addEventListener("click", toggleLogDrawer);
el.mailList.addEventListener("keydown", handleMailListKeydown);
el.limitInput.addEventListener("change", () => {
  el.limitInput.value = normalizeLimit(el.limitInput.value);
  syncFetchScopeControls();
});
if (el.rawFetchToggle) {
  el.rawFetchToggle.addEventListener("change", syncFetchScopeControls);
}
el.selectedScopeBtn?.addEventListener("click", () => setFetchScope("selected"));
el.allScopeBtn?.addEventListener("click", () => setFetchScope("all"));
el.privacyToggle.addEventListener("click", () => {
  state.accountPrivacy = !state.accountPrivacy;
  syncAccountPrivacy();
});
el.accountTextInput.addEventListener("input", () => {
  sessionRequests.reset();
  mailOperationGate.reset();
  clearScheduledAccountParse();
  state.accounts = [];
  state.accountStatus.clear();
  state.selectedAccountEmail = "";
  state.activeAccountEmail = "";
  state.fetchScope = "selected";
  state.parsedText = "";
  resetSessionResults();
  renderAccounts([]);
  renderInputQuality();
  resetAccountPrivacyWhenEmpty();
  syncAccountPrivacy();
  setBusy(false);
  setStatus("准备就绪", "ready");
  scheduleAccountParse();
});
el.clearLogBtn.addEventListener("click", () => {
  el.runLog.innerHTML = "";
  syncLogActions();
});

syncActionAvailability();
syncLogActions();
syncAccountPrivacy();
syncSessionActions();
renderInputQuality();
setStatus("准备就绪", "ready");

loadConfig()
  .catch((error) => {
    addLog(error.message, "fail");
    setStatus("初始化失败", "error");
  });
