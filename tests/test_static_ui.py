from pathlib import Path
import re
import unittest


STATIC_HTML = Path(__file__).resolve().parents[1] / "mail_receiver" / "static" / "index.html"
STATIC_JS = Path(__file__).resolve().parents[1] / "mail_receiver" / "static" / "app.js"
STATIC_CSS = Path(__file__).resolve().parents[1] / "mail_receiver" / "static" / "app.css"


def section_html(html: str, title: str) -> str:
    for match in re.finditer(r"<section[^>]*>.*?</section>", html, flags=re.DOTALL):
        fragment = match.group(0)
        if f"<h2>{title}</h2>" in fragment:
            return fragment
    raise AssertionError(f"section not found: {title}")


def column_html(html: str, class_name: str) -> str:
    start_match = re.search(rf'<div class="[^"]*\b{re.escape(class_name)}\b[^"]*">', html)
    if start_match is None:
        raise AssertionError(f"column not found: {class_name}")
    start = start_match.start()
    if class_name == "control-column":
        review_match = re.search(r'<div class="[^"]*\breview-column\b[^"]*">', html)
        if review_match is None:
            raise AssertionError("review column not found")
        end = review_match.start()
        return html[start:end]
    return html[start:]


def css_rule(css: str, selector: str) -> str:
    pattern = rf"^{re.escape(selector)} \{{\n(?P<body>.*?)\n\}}"
    match = re.search(pattern, css, re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError(f"css rule not found: {selector}")
    return match.group("body")


def nested_css_rule(css: str, selector: str) -> str:
    pattern = rf"^\s*{re.escape(selector)} \{{\n(?P<body>.*?)\n\s*\}}"
    match = re.search(pattern, css, re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError(f"css rule not found: {selector}")
    return match.group("body")


class StaticUiTests(unittest.TestCase):
    def test_frontend_branding_uses_short_product_name(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")

        self.assertIn("<title>Outlook 邮件</title>", html)
        self.assertIn("<h1>Outlook 邮件</h1>", html)
        self.assertIn('<header class="app-header">', html)
        self.assertIn('<div class="brand-lockup">', html)
        self.assertLess(
            html.index('<header class="app-header">'),
            html.index('<main class="workspace dashboard-grid">'),
        )
        self.assertNotIn("Outlook 邮件调试台", html)

    def test_frontend_branding_shows_runtime_version_badge(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="appVersionBadge"', html)
        self.assertIn('class="version-badge"', html)
        self.assertIn("appVersionBadge: document.getElementById(\"appVersionBadge\")", js)
        self.assertIn("el.appVersionBadge.textContent = `v${config.version}`", js)
        self.assertIn("el.appVersionBadge.hidden = false", js)
        version_badge = css_rule(css[: css.index("@media")], ".version-badge")
        self.assertIn("border-radius: 999px", version_badge)
        self.assertIn("font-size: 12px", version_badge)

    def test_dashboard_layout_has_modern_productivity_structure(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")

        self.assertIn('class="workspace dashboard-grid"', html)
        self.assertIn('class="control-column command-center"', html)
        self.assertIn('class="review-column mail-review-stage"', html)
        self.assertIn("activity-log", html)
        self.assertNotIn("terminal-log", html)
        self.assertIn('class="mail-workbench"', html)
        self.assertIn('class="icon"', html)
        self.assertIn('id="themeToggle"', html)

        self.assertNotIn("诊断报告", html)
        self.assertNotIn("UI 蓝图", html)
        self.assertNotIn("insight-strip", html)
        self.assertNotIn("1. 输入账号信息", html)
        self.assertNotIn("2. 解析账号信息", html)
        self.assertNotIn("3. 操作", html)
        self.assertNotIn("4. 运行记录", html)
        self.assertNotIn("5. 邮件结果", html)

    def test_c2_mail_review_workbench_promotes_command_center_and_log_drawer(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        self.assertIn('class="control-column command-center"', html)
        self.assertIn('class="review-column mail-review-stage"', html)
        self.assertNotIn('id="messageFilterBar"', html)
        self.assertIn('id="logDrawerToggle"', html)
        self.assertIn('class="button ghost log-drawer-tab"', html)
        self.assertIn('class="panel run-log-panel log-drawer is-collapsed"', html)
        self.assertNotIn('id="runLogPanel"', column_html(html, "control-column"))
        self.assertLess(html.index("</main>"), html.index('id="runLogPanel"'))

        dashboard = css_rule(base_css, ".dashboard-grid")
        command = css_rule(base_css, ".control-column.command-center")
        command_empty = css_rule(base_css, ".control-column.command-center.is-initial-empty")
        review = css_rule(base_css, ".review-column.mail-review-stage")
        review_panel = css_rule(base_css, ".review-column.mail-review-stage > .result-panel")
        drawer = css_rule(base_css, ".run-log-panel.log-drawer")

        self.assertIn("grid-template-columns: minmax(360px, 420px) minmax(0, 1fr)", dashboard)
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto", dashboard)
        self.assertIn("height: calc(100vh - 142px)", dashboard)
        self.assertIn("align-items: stretch", dashboard)
        self.assertIn("gap: 12px", dashboard)
        self.assertIn("display: contents", command)
        self.assertNotIn("grid-template-columns: minmax(360px, 0.92fr) minmax(420px, 1.08fr)", command)
        self.assertIn("grid-template-rows: auto", command_empty)
        self.assertNotIn("minmax(174px", command_empty)
        self.assertIn("grid-column: 2", review)
        self.assertIn("grid-row: 1 / 3", review)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", review)
        self.assertIn("height: 100%", review)
        self.assertIn("grid-column: 1", review_panel)
        self.assertIn("height: 100%", review_panel)
        self.assertIn("position: fixed", drawer)
        self.assertIn("right: 14px", drawer)
        self.assertIn("width: min(420px, calc(100vw - 32px))", drawer)
        self.assertIn("transform: translateX(calc(100% + 16px))", drawer)
        self.assertIn(".log-drawer-tab", css)
        self.assertIn(".run-log-panel.log-drawer.is-open", css)

    def test_desktop_workspace_uses_left_account_rail_and_right_work_area(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        dashboard = css_rule(base_css, ".dashboard-grid")
        command = css_rule(base_css, ".control-column.command-center")
        account = css_rule(base_css, ".account-input-panel")
        operation = css_rule(base_css, ".operation-panel")
        review = css_rule(base_css, ".review-column.mail-review-stage")
        result = css_rule(base_css, ".review-column.mail-review-stage > .result-panel")
        account_list = css_rule(base_css, ".account-list")

        self.assertIn("grid-template-columns: minmax(360px, 420px) minmax(0, 1fr)", dashboard)
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto", dashboard)
        self.assertIn("height: calc(100vh - 142px)", dashboard)
        self.assertIn("display: contents", command)
        self.assertIn("grid-column: 1", account)
        self.assertIn("grid-row: 1", account)
        self.assertIn("height: 100%", account)
        self.assertIn("overflow: hidden", account)
        self.assertIn("grid-column: 1", operation)
        self.assertIn("grid-row: 2", operation)
        self.assertIn("align-self: end", operation)
        self.assertNotIn("align-self: stretch", operation)
        self.assertIn("grid-column: 2", review)
        self.assertIn("grid-row: 1 / 3", review)
        self.assertIn("min-height: 0", result)
        self.assertIn("height: 100%", result)
        self.assertIn("max-height: none", account_list)
        self.assertIn("overflow: auto", account_list)

    def test_verification_code_card_and_session_actions_are_frontend_only(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="currentCodeSummary"', html)
        self.assertIn('currentCodeSummary: document.getElementById("currentCodeSummary")', js)
        self.assertNotIn('id="copyCurrentCodeBtn"', html)
        self.assertNotIn('copyCurrentCodeBtn: document.getElementById("copyCurrentCodeBtn")', js)
        for removed_control_id in [
            "copyAllCodesBtn",
            "exportResultsBtn",
            "retryFailedBtn",
            "codePrivacyToggle",
        ]:
            self.assertNotIn(f'id="{removed_control_id}"', html)
            self.assertNotIn(f'{removed_control_id}: document.getElementById("{removed_control_id}")', js)

        self.assertIn("function extractVerificationCode(mail)", js)
        self.assertIn("const VERIFICATION_KEYWORD_PATTERN", js)
        self.assertIn("function verificationCodeCardMarkup(mail)", js)
        self.assertIn("function copyCurrentVerificationCode", js)
        self.assertIn("function retryFailedAccounts", js)
        self.assertNotIn("function copyAllVerificationCodes", js)
        self.assertNotIn("function exportSessionResultsCsv", js)
        self.assertNotIn("function sessionExportRows", js)
        self.assertNotIn("account_email,sender,subject,received_at,code,source,confidence", js)
        self.assertNotIn("codePrivacy", js)
        self.assertNotIn("data-privacy", js)
        self.assertNotIn('api("/api/verification"', js)

        self.assertIn('class="verification-card"', js)
        self.assertIn('class="verification-code-value"', js)
        self.assertIn("未识别验证码", js)
        self.assertIn(".verification-card", css)
        self.assertIn(".verification-code-value", css)
        verification_card = css_rule(css[: css.index("@media")], ".verification-card")
        verification_button = css_rule(css[: css.index("@media")], ".verification-card .button")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", verification_card)
        self.assertNotIn("grid-template-columns: minmax(0, 1fr) auto", verification_card)
        self.assertIn("justify-self: start", verification_button)
        self.assertNotIn(".verification-card[data-privacy=\"hidden\"]", css)

    def test_verification_parser_uses_provider_registry_for_xai_codes(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("const VERIFICATION_PROVIDERS", js)
        self.assertIn('id: "xai"', js)
        self.assertIn('label: "xAI"', js)
        self.assertIn("/x\\.ai/i", js)
        self.assertIn("/grok/i", js)
        self.assertIn("/confirmation code/i", js)
        self.assertIn("[A-Z0-9]{3}[-\\s][A-Z0-9]{3}", js)
        self.assertIn("normalizeVerificationCode", js)
        self.assertIn("preserveSeparator", js)
        self.assertIn('provider: provider.id', js)
        self.assertIn('providerLabel: provider.label', js)

    def test_provider_specific_verification_parsing_requires_provider_identity(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("identityPatterns", js)
        self.assertIn("function providerMatchesText(provider, text)", js)
        self.assertIn("provider.identityPatterns?.length && !providerMatchesText(provider, text)", js)
        self.assertIn('identityPatterns: [/x\\.ai/i, /xai/i, /grok/i]', js)

    def test_fetch_and_retry_share_an_owner_gate_for_busy_cleanup(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn(
            "const { createOperationGate, createRequestFailureState, createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;",
            js,
        )
        self.assertEqual(js.count("const mailOperationGate = createOperationGate();"), 1)

        fetch_match = re.search(r"async function fetchMail\(\) \{(?P<body>.*?)\n\}", js, re.DOTALL)
        retry_match = re.search(r"async function retryFailedAccounts\(\) \{(?P<body>.*?)\n\}", js, re.DOTALL)
        self.assertIsNotNone(fetch_match)
        self.assertIsNotNone(retry_match)
        gate_start = (
            "const operationToken = mailOperationGate.tryStart();\n"
            "  if (operationToken === null) {\n"
            "    return;\n"
            "  }"
        )
        self.assertTrue(fetch_match.group("body").strip().startswith(gate_start))
        retry_body = retry_match.group("body")
        self.assertLess(retry_body.index("if (!failedEmails.length)"), retry_body.index(gate_start))

        for function_name in ["fetchMail", "retryFailedAccounts"]:
            with self.subTest(function_name=function_name):
                function_match = re.search(
                    rf"async function {function_name}\(\) \{{(?P<body>.*?)\n\}}",
                    js,
                    re.DOTALL,
                )
                self.assertIsNotNone(function_match)
                function_body = function_match.group("body")
                self.assertEqual(function_body.count("mailOperationGate.tryStart()"), 1)
                self.assertEqual(function_body.count("mailOperationGate.finish(operationToken)"), 1)
                self.assertIn("const operationToken = mailOperationGate.tryStart();", function_body)
                self.assertIn(
                    "if (operationToken === null) {\n"
                    "    return;\n"
                    "  }",
                    function_body,
                )
                self.assertLess(
                    function_body.index("mailOperationGate.tryStart()"),
                    function_body.index("const parsed = await ensureParsed();"),
                )
                finally_block = re.search(r"finally \{\n(?P<body>.*?)\n  \}", function_match.group("body"), re.DOTALL)
                self.assertIsNotNone(finally_block)
                body = finally_block.group("body")
                self.assertIn(
                    "mailOperationGate.finish(operationToken) && sessionRequests.isCurrent(operationRevision)",
                    body,
                )
                self.assertIn("setBusy(false);", body)
                self.assertIn("syncSessionActions();", body)
                self.assertLess(
                    body.index("mailOperationGate.finish(operationToken)"),
                    body.index("sessionRequests.isCurrent(operationRevision)"),
                )
                self.assertLess(body.index("setBusy(false);"), body.index("syncSessionActions();"))

    def test_fetch_transport_failures_replace_busy_status_and_preserve_retry_rows(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn(
            "const { createOperationGate, createRequestFailureState, createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;",
            js,
        )
        self.assertIn('request: "请求"', js)

        helper_match = re.search(
            r"function recordRequestFailure\(email, error\) \{(?P<body>.*?)\n\}",
            js,
            re.DOTALL,
        )
        self.assertIsNotNone(helper_match)
        helper_body = helper_match.group("body")
        helper_contract = [
            "const failure = createRequestFailureState(email, error);",
            "state.accountStatus.set(email, failure.status);",
            "const failedByEmail = new Map(state.failedRows.map((row) => [row.email, row]));",
            "failedByEmail.set(email, failure.row);",
            "state.failedRows = Array.from(failedByEmail.values());",
            "renderAccounts(state.accounts);",
        ]
        for contract in helper_contract:
            with self.subTest(helper_contract=contract):
                self.assertIn(contract, helper_body)
        for earlier, later in zip(helper_contract, helper_contract[1:]):
            self.assertLess(helper_body.index(earlier), helper_body.index(later))

        for function_name in ["fetchMail", "retryFailedAccounts"]:
            with self.subTest(function_name=function_name):
                function_match = re.search(
                    rf"async function {function_name}\(\) \{{(?P<body>.*?)\n\}}",
                    js,
                    re.DOTALL,
                )
                self.assertIsNotNone(function_match)
                body = function_match.group("body")
                self.assertEqual(body.count('let pendingEmail = "";'), 1)
                self.assertRegex(
                    body,
                    r"pendingEmail = account\.email;\s+"
                    r"const accountData = await fetchOneAccount\(account\);\s+"
                    r"if \(!sessionRequests\.isCurrent\(operationRevision\)\) \{\s+"
                    r"return;\s+"
                    r"\}\s+"
                    r"pendingEmail = \"\";\s+"
                    r"renderFetchResult\(accountData\);",
                )
                stale_check = "if (requestIsStale(operationRevision, error))"
                failure_record = (
                    "if (pendingEmail) {\n"
                    "      recordRequestFailure(pendingEmail, error);\n"
                    "    }"
                )
                self.assertIn(failure_record, body)
                self.assertLess(body.index(stale_check), body.index(failure_record))
                self.assertEqual(body.count("recordRequestFailure(pendingEmail, error);"), 1)

    def test_account_edits_cancel_and_isolate_stale_requests(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        def async_function_body(function_name: str) -> str:
            function_match = re.search(
                rf"async function {function_name}\([^)]*\) \{{(?P<body>.*?)\n\}}",
                js,
                re.DOTALL,
            )
            self.assertIsNotNone(function_match, f"function not found: {function_name}")
            return function_match.group("body")

        self.assertIn(
            "const { createOperationGate, createRequestFailureState, createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;",
            js,
        )
        self.assertIn("const sessionRequests = createSessionCoordinator();", js)
        self.assertIn("const mailOperationGate = createOperationGate();", js)

        stale_match = re.search(
            r"function requestIsStale\(revision, error\) \{(?P<body>.*?)\n\}",
            js,
            re.DOTALL,
        )
        self.assertIsNotNone(stale_match)
        self.assertIn(
            'return !sessionRequests.isCurrent(revision) || error?.name === "AbortError";',
            stale_match.group("body"),
        )

        input_match = re.search(
            r'el\.accountTextInput\.addEventListener\("input", \(\) => \{(?P<body>.*?)\n\}\);',
            js,
            re.DOTALL,
        )
        self.assertIsNotNone(input_match)
        input_body = input_match.group("body")
        self.assertTrue(input_body.strip().startswith("sessionRequests.reset();\n  mailOperationGate.reset();"))
        self.assertIn("mailOperationGate.reset();", input_body)
        self.assertLess(input_body.index("sessionRequests.reset();"), input_body.index("mailOperationGate.reset();"))
        self.assertLess(input_body.index("mailOperationGate.reset();"), input_body.index("resetSessionResults();"))
        self.assertLess(input_body.index("mailOperationGate.reset();"), input_body.index("setBusy(false);"))
        self.assertLess(input_body.index("sessionRequests.reset();"), input_body.index("resetSessionResults();"))
        self.assertIn("setBusy(false);", input_body)

        parse_body = async_function_body("parseInput")
        for contract in [
            "sessionRequests.startRequest()",
            "request.controller.signal",
            "sessionRequests.isCurrent(request.revision)",
            "requestIsStale(request.revision, error)",
            "sessionRequests.finishRequest(request.controller);",
        ]:
            with self.subTest(function_name="parseInput", contract=contract):
                self.assertIn(contract, parse_body)
        self.assertIn(
            "catch (error) {\n"
            "    if (requestIsStale(request.revision, error)) {\n"
            "      return false;\n"
            "    }",
            parse_body,
        )
        self.assertIn(
            "finally {\n"
            "    sessionRequests.finishRequest(request.controller);\n"
            "    if (sessionRequests.isCurrent(request.revision)) {\n"
            "      setBusy(false);\n"
            "    }\n"
            "  }",
            parse_body,
        )

        fetch_one_body = async_function_body("fetchOneAccount")
        for contract in [
            "sessionRequests.startRequest()",
            "request.controller.signal",
            "sessionRequests.finishRequest(request.controller);",
        ]:
            with self.subTest(function_name="fetchOneAccount", contract=contract):
                self.assertIn(contract, fetch_one_body)
        self.assertIn(
            "finally {\n"
            "    sessionRequests.finishRequest(request.controller);\n"
            "  }",
            fetch_one_body,
        )

        ensure_body = async_function_body("ensureParsed")
        self.assertIn("sessionRequests.currentRevision()", ensure_body)
        self.assertIn("!ok && sessionRequests.isCurrent(revision)", ensure_body)
        self.assertIn("return ok;", ensure_body)

        for function_name in ["fetchMail", "retryFailedAccounts"]:
            with self.subTest(function_name=function_name):
                body = async_function_body(function_name)
                self.assertIn(
                    "const operationToken = mailOperationGate.tryStart();\n"
                    "  if (operationToken === null) {\n"
                    "    return;\n"
                    "  }",
                    body,
                )
                self.assertIn("const operationRevision = sessionRequests.currentRevision();", body)
                self.assertLess(
                    body.index("const operationToken = mailOperationGate.tryStart();"),
                    body.index("const operationRevision = sessionRequests.currentRevision();"),
                )
                self.assertIn("const parsed = await ensureParsed();", body)
                self.assertIn("!parsed || !sessionRequests.isCurrent(operationRevision)", body)
                self.assertRegex(
                    body,
                    r"await fetchOneAccount\(account\);\s+if \(!sessionRequests\.isCurrent\(operationRevision\)\)",
                )
                self.assertIn("requestIsStale(operationRevision, error)", body)
                self.assertIn(
                    "catch (error) {\n"
                    "    if (requestIsStale(operationRevision, error)) {\n"
                    "      return;\n"
                    "    }",
                    body,
                )
                self.assertIn(
                    "finally {\n"
                    "    if (mailOperationGate.finish(operationToken) && sessionRequests.isCurrent(operationRevision)) {\n"
                    "      setBusy(false);\n"
                    "      syncSessionActions();\n"
                    "    }\n"
                    "  }",
                    body,
                )

    def test_c2_mail_stage_defaults_to_selected_account_without_filter_chips(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        mobile_start = css.index("@media (max-width: 720px)")
        mobile_end = css.index("@media (max-width: 560px)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        self.assertNotIn('data-filter="all"', html)
        self.assertNotIn('data-filter="failed"', html)
        self.assertNotIn('id="messageFilterBar"', html)
        self.assertNotIn("messageFilter:", js)
        self.assertNotIn("function setMessageFilter(filter)", js)
        self.assertNotIn("function filteredVisibleMessages", js)
        self.assertNotIn("el.messageFilterBar?.querySelectorAll", js)
        self.assertNotIn("filter-chip", css)
        self.assertIn("function visibleMessages()", js)
        self.assertIn("return state.activeAccountEmail ? messagesForAccount(state.activeAccountEmail) : allSessionMessages();", js)
        self.assertIn(".mail-review-stage", css)
        self.assertIn(".control-column.command-center", mobile_block)
        self.assertIn("grid-template-columns: 1fr", mobile_block)
        self.assertIn(".run-log-panel.log-drawer", mobile_block)

    def test_p1_empty_states_are_quiet_and_non_repetitive(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        active_copy = f"{html}\n{js}"

        for noisy_copy in [
            "粘贴账号 → 拉取邮件 → 查看验证码",
            "等待本次拉取",
            "选择邮件查看详情",
        ]:
            self.assertNotIn(noisy_copy, active_copy)

        html_empty_mail = html[html.index('class="mail-list empty"'):html.index('class="mail-reader-shell"')]
        js_empty_mail = js[js.index("function mailListEmptyMarkup"):js.index("function mailReaderPlaceholderMarkup")]
        for noisy_mail_step in ["账号解析", "IMAP 拉取", "自动选中"]:
            self.assertNotIn(noisy_mail_step, html_empty_mail)
            self.assertNotIn(noisy_mail_step, js_empty_mail)

        self.assertIn("等待账号", js)
        self.assertIn("粘贴后自动读取账号状态", js)
        self.assertIn("拉取后显示邮件与验证码", html)
        self.assertIn("邮件详情", html)
        self.assertNotIn("mail-empty-guide", html)

    def test_p1_log_drawer_entry_is_quiet_until_session_events_exist(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        self.assertIn('id="logDrawerToggle"', html)
        self.assertIn('aria-label="查看运行日志"', html)
        self.assertIn(">日志</button>", html)
        self.assertNotIn(">展开日志</button>", html)
        self.assertIn('el.logDrawerToggle.classList.toggle("has-log-events", hasLogs);', js)
        self.assertIn('el.logDrawerToggle.textContent = nextOpen ? "收起" : "日志";', js)

        tab = css_rule(base_css, "button.log-drawer-tab")
        has_events_tab = css_rule(base_css, 'button.log-drawer-tab.has-log-events:not([aria-expanded="true"])')
        self.assertIn("top: auto", tab)
        self.assertIn("bottom: 18px", tab)
        self.assertIn("width: auto", tab)
        self.assertIn("min-height: 34px", tab)
        self.assertIn("writing-mode: horizontal-tb", tab)
        self.assertIn("opacity: 0.58", tab)
        self.assertNotIn("min-height: 112px", tab)
        self.assertNotIn("writing-mode: vertical-rl", tab)
        self.assertIn("opacity: 0.88", has_events_tab)

    def test_p1_operation_console_groups_context_and_actions(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        operation = section_html(html, "控制台")

        self.assertIn('class="section-title operation-panel-title"', operation)
        self.assertIn('class="operation-command-row"', html)
        self.assertIn('class="operation-command-actions"', html)
        self.assertNotIn('class="operation-command-copy"', operation)
        self.assertLess(operation.index('class="section-title operation-panel-title"'), operation.index('id="operationNote"'))
        self.assertLess(operation.index('id="operationNote"'), operation.index('class="operation-command-row"'))
        self.assertLess(operation.index('class="operation-command-actions"'), operation.index('id="fetchBtn"'))
        self.assertLess(operation.index('id="fetchBtn"'), operation.index('id="currentCodeSummary"'))
        self.assertIn("验证码摘要", operation)
        self.assertNotIn("复制当前验证码", operation)

        title = css_rule(base_css, ".section-title.operation-panel-title")
        title_note = css_rule(base_css, ".operation-panel-title .operation-note")
        row = css_rule(base_css, ".operation-command-row")
        actions = css_rule(base_css, ".operation-command-actions")
        actions_stack = css_rule(base_css, ".operation-command-actions .action-stack")
        code_summary = css_rule(base_css, ".operation-code-summary")
        self.assertIn("display: grid", title)
        self.assertIn("grid-template-columns: auto minmax(260px, 1fr)", title)
        self.assertIn("justify-self: end", title_note)
        self.assertIn("border-top: 0", title_note)
        self.assertIn("grid-template-columns: 1fr", row)
        self.assertIn("align-items: end", row)
        self.assertIn("min-height: 58px", row)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", actions)
        self.assertIn("max-width: none", actions)
        self.assertIn("justify-self: start", actions)
        self.assertIn("grid-template-columns: 1fr", actions_stack)
        self.assertIn("min-height: 48px", code_summary)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", code_summary)

    def test_p1_console_code_summary_tracks_selected_mail_with_inline_copy_button(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="currentCodeSummary"', html)
        self.assertIn("验证码摘要", html)
        self.assertIn("function renderOperationCodeSummary(currentMail)", js)
        self.assertIn("const hasCode = Boolean(currentCode);", js)
        self.assertIn('el.currentCodeSummary.className = "operation-code-summary operation-verification-card verification-card";', js)
        self.assertIn('el.currentCodeSummary.classList.toggle("has-code", hasCode);', js)
        self.assertIn('el.currentCodeSummary.classList.toggle("is-empty", !currentMail);', js)
        self.assertIn("extractVerificationCode(currentMail)", js)
        self.assertIn("copy-current-code-inline", js)
        self.assertIn("copyCurrentVerificationCode", js)
        self.assertIn(".operation-code-summary", css)
        self.assertIn(".operation-code-summary.has-code", css)
        self.assertIn(".operation-verification-card", css)
        self.assertIn("复制验证码", html)

    def test_console_code_summary_uses_full_verification_card_with_copy_button(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        operation = section_html(html, "控制台")

        self.assertIn('id="currentCodeSummary"', operation)
        self.assertIn("function renderOperationCodeSummary(currentMail)", js)
        self.assertIn("operation-verification-card", js)
        self.assertIn("verification-card-copy", js)
        self.assertIn("verification-eyebrow", js)
        self.assertIn("verification-code-value", js)
        self.assertIn("verification-source", js)
        self.assertIn("copy-current-code-inline", js)
        self.assertIn('data-code-action="copy-current"', js)
        self.assertIn("copyCurrentVerificationCode", js)
        self.assertIn('el.currentCodeSummary.querySelector("[data-code-action=\\"copy-current\\"]")?.addEventListener("click", copyCurrentVerificationCode);', js)

        card = css_rule(base_css, ".operation-verification-card")
        code = css_rule(base_css, ".operation-verification-card .verification-code-value")
        self.assertIn("min-height: 156px", card)
        self.assertIn("padding: 16px 18px", card)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--accent) 16%, var(--line-soft))", card)
        self.assertIn("border-radius: var(--radius-lg)", card)
        self.assertIn("justify-self: stretch", card)
        self.assertIn("font-size: 32px", code)
        self.assertIn("letter-spacing: 0.10em", code)

    def test_console_verification_card_stays_inside_mobile_console(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        narrow_start = css.index("@media (max-width: 720px)")
        narrow_end = css.index("@media (min-width: 561px) and (max-width: 720px)", narrow_start)
        phone_start = css.index("@media (max-width: 560px)")
        phone_end = css.index("@media (max-width: 360px)", phone_start)
        narrow_css = css[narrow_start:narrow_end]
        phone_css = css[phone_start:phone_end]

        actions = nested_css_rule(narrow_css, ".operation-command-actions")
        card = nested_css_rule(phone_css, ".operation-verification-card")
        code = nested_css_rule(phone_css, ".operation-verification-card .verification-code-value")
        button = nested_css_rule(phone_css, ".operation-verification-card .copy-current-code-inline")

        self.assertIn("grid-template-columns: minmax(0, 1fr)", actions)
        self.assertNotIn("minmax(360px", actions)
        self.assertIn("width: 100%", card)
        self.assertIn("min-height: 156px", card)
        self.assertIn("padding: 16px 18px", card)
        self.assertIn("font-size: 32px", code)
        self.assertIn("width: auto", button)
        self.assertIn("justify-self: start", button)

    def test_account_management_sits_above_console_in_control_column(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        phone_start = css.index("@media (max-width: 560px)")
        phone_end = css.index("@media (max-width: 360px)", phone_start)
        phone_css = css[phone_start:phone_end]
        control_column = column_html(html, "control-column")

        operation = css_rule(base_css, ".operation-panel")
        account = css_rule(base_css, ".account-input-panel")
        review = css_rule(base_css, ".review-column.mail-review-stage")
        mobile_operation = nested_css_rule(phone_css, ".operation-panel")
        mobile_account = nested_css_rule(phone_css, ".account-input-panel")

        self.assertLess(control_column.index("<h2>账号管理</h2>"), control_column.index("<h2>控制台</h2>"))
        self.assertIn("grid-column: 1", operation)
        self.assertIn("grid-row: 2", operation)
        self.assertIn("align-self: end", operation)
        self.assertNotIn("align-self: stretch", operation)
        self.assertIn("grid-column: 1", account)
        self.assertIn("grid-row: 1", account)
        self.assertIn("grid-column: 2", review)
        self.assertIn("grid-row: 1 / 3", review)
        self.assertIn("order: 2", mobile_operation)
        self.assertIn("order: 1", mobile_account)

    def test_scrollable_regions_use_quiet_edge_scrollbars(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        scrollable = re.search(
            r"\.account-list,\n\.mail-list,\n\.mail-detail,\n\.run-log \{\n(?P<body>.*?)\n\}",
            base_css,
            re.DOTALL,
        )
        scrollbar = re.search(
            r"\.account-list::-webkit-scrollbar,\n"
            r"\.mail-list::-webkit-scrollbar,\n"
            r"\.mail-detail::-webkit-scrollbar,\n"
            r"\.run-log::-webkit-scrollbar \{\n(?P<body>.*?)\n\}",
            base_css,
            re.DOTALL,
        )
        thumb = re.search(
            r"\.account-list::-webkit-scrollbar-thumb,\n"
            r"\.mail-list::-webkit-scrollbar-thumb,\n"
            r"\.mail-detail::-webkit-scrollbar-thumb,\n"
            r"\.run-log::-webkit-scrollbar-thumb \{\n(?P<body>.*?)\n\}",
            base_css,
            re.DOTALL,
        )

        self.assertIsNotNone(scrollable)
        self.assertIsNotNone(scrollbar)
        self.assertIsNotNone(thumb)
        self.assertIn("scrollbar-width: thin", scrollable.group("body"))
        self.assertIn(
            "scrollbar-color: color-mix(in srgb, var(--line-strong) 42%, transparent) transparent",
            scrollable.group("body"),
        )
        self.assertNotIn("scrollbar-color: var(--line-strong) transparent", scrollable.group("body"))
        self.assertIn("width: 8px", scrollbar.group("body"))
        self.assertIn("height: 8px", scrollbar.group("body"))
        self.assertIn("border: 3px solid transparent", thumb.group("body"))
        self.assertIn("background: color-mix(in srgb, var(--line-strong) 46%, transparent)", thumb.group("body"))
        self.assertNotIn("background: var(--line-strong)", thumb.group("body"))
        self.assertIn("::-webkit-scrollbar-thumb:hover", base_css)
        self.assertIn("background: color-mix(in srgb, var(--line-strong) 64%, transparent)", base_css)

        self.assertIn(".mail-list::-webkit-scrollbar", mobile_block)
        self.assertIn("width: 6px", mobile_block)
        self.assertIn("height: 6px", mobile_block)
        self.assertIn(".mail-list::-webkit-scrollbar-thumb", mobile_block)
        self.assertIn("border: 2px solid transparent", mobile_block)

    def test_workflow_removes_unneeded_controls_and_positions_actions(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertNotIn("拖拽配置文本或点击导入", html)
        self.assertNotIn("解析输入", html)
        self.assertNotIn('id="parseBtn"', html)
        self.assertNotIn('id="clearInputBtn"', html)
        self.assertNotIn("Validation", html)
        self.assertNotIn("筛选本次邮件", html)
        self.assertNotIn("复制失败", html)
        self.assertNotIn('id="queryInput"', html)
        self.assertNotIn('id="searchBtn"', html)
        self.assertNotIn('id="searchLimitInput"', html)
        self.assertNotIn('id="copyFailedBtn"', html)
        self.assertNotIn("accountFileInput", html)
        self.assertNotIn("accountFileUpload", html)
        self.assertNotIn("dropZone", html)
        self.assertNotIn("loadFileBtn", html)
        self.assertNotIn("账号文件", html)
        self.assertNotIn("summary-strip", html)
        self.assertNotIn("accountSelect", html)
        self.assertNotIn("账号过滤", html)

        accounts = section_html(html, "账号管理")
        operation = section_html(html, "控制台")
        control_column = column_html(html, "control-column")
        review_column = column_html(html, "review-column")
        review_in_main = review_column[:review_column.index("</main>")]

        self.assertIn('id="accountTextInput"', accounts)
        self.assertIn('id="accountList"', accounts)
        self.assertIn("账号状态", accounts)
        self.assertNotIn('id="accountList"', operation)
        self.assertNotIn("运行记录", operation)
        self.assertNotIn("runLog", operation)

        self.assertNotIn('id="runLog"', control_column)
        self.assertNotIn('id="clearLogBtn"', control_column)
        self.assertNotIn('id="runLog"', review_in_main)
        self.assertLess(html.index("</main>"), html.index("运行日志"))

        self.assertIn("<h2>账号管理</h2>", html)
        self.assertIn("<h2>控制台</h2>", html)
        self.assertIn("<h2>运行日志</h2>", html)
        self.assertIn("<h2>邮件结果</h2>", html)
        self.assertNotIn('class="section-kicker"', html)
        self.assertNotIn("<h2>账号输入</h2>", html)
        self.assertNotIn("<h2>操作控制</h2>", html)

        self.assertNotIn("dropZone", js)
        self.assertNotIn("clearInputBtn", js)
        self.assertNotIn("queryInput", js)
        self.assertNotIn("searchBtn", js)
        self.assertNotIn("copyFailedBtn", js)
        self.assertNotIn("copyFailed", js)

    def test_account_input_auto_parses_without_manual_detection_control(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertNotIn('id="checkBtn"', html)
        self.assertNotIn("检测有效性", html)
        self.assertNotIn("checkBtn:", js)
        self.assertNotIn("function checkAccounts", js)
        self.assertNotIn('api("/api/check"', js)
        self.assertNotIn('el.checkBtn.addEventListener("click"', js)

        self.assertIn("const AUTO_PARSE_DELAY_MS = 300", js)
        self.assertIn("let autoParseTimer = null", js)
        self.assertIn("function clearScheduledAccountParse", js)
        self.assertIn("function shouldAutoParseAccountText", js)
        self.assertIn("function scheduleAccountParse", js)
        self.assertIn("autoParseTimer = window.setTimeout", js)
        self.assertIn('parseInput({ source: "auto" })', js)
        self.assertLess(
            js.index("renderInputQuality();", js.index('el.accountTextInput.addEventListener("input"')),
            js.index("scheduleAccountParse();", js.index('el.accountTextInput.addEventListener("input"')),
        )
        action_stack_rules = re.findall(r"^\.action-stack \{\n(?P<body>.*?)\n\}", css, re.DOTALL | re.MULTILINE)
        self.assertTrue(any("grid-template-columns: 1fr" in rule for rule in action_stack_rules))

    def test_theme_toggle_is_available_and_persistent(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="themeToggle"', html)
        self.assertIn("浅色", html)
        self.assertIn("深色", html)
        self.assertIn("localStorage", js)
        self.assertIn("mailReceiverTheme", js)
        self.assertIn('document.documentElement.dataset.theme', js)
        self.assertIn('[data-theme="light"]', css)
        self.assertIn('[data-theme="dark"]', css)

    def test_activity_stream_follows_theme_tokens(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("--activity-bg: #ffffff;", css)
        self.assertIn("--activity-bar: #f4f8fc;", css)
        self.assertIn("--activity-text: #172033;", css)
        self.assertIn("--activity-line: #d9e2ee;", css)
        self.assertIn("--activity-bg: rgba(2, 6, 23, 0.42);", css)
        self.assertIn("background: var(--activity-bg)", css)
        self.assertIn("color: var(--activity-text)", css)
        self.assertNotIn('content: "$ 等待操作输出..."', css)

    def test_activity_empty_state_is_quiet_session_hint_not_nested_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        empty_log = css_rule(css, ".activity-log:empty")
        empty_before = css_rule(css, ".activity-log:empty::before")
        empty_after = css_rule(css, ".activity-log:empty::after")

        self.assertIn("justify-items: start", empty_log)
        self.assertIn("padding: 10px", empty_log)
        self.assertIn('content: "静候会话事件"', empty_before)
        self.assertIn("border-left: 2px solid var(--subtle)", empty_before)
        self.assertIn("color: var(--activity-muted)", empty_before)
        self.assertIn("box-shadow: none", empty_before)
        self.assertNotIn("border: 1px solid", empty_before)
        self.assertNotIn("background:", empty_before)
        self.assertIn('content: "解析账号或拉取邮件后显示最新记录"', empty_after)
        self.assertIn("font-size: 10.75px", empty_after)
        self.assertNotIn("display: none", empty_after)

    def test_inbox_preview_uses_modern_empty_and_reader_layout(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("mail-result-summary", html)
        self.assertIn("mail-list-shell", html)
        self.assertIn("mail-reader-shell", html)
        self.assertIn("mail-empty-panel", html)
        self.assertIn("mail-empty-hero", html)
        self.assertIn("mail-empty-icon", html)
        self.assertIn("mail-list-empty-state", html)
        self.assertIn("mail-detail-placeholder", html)
        self.assertIn("mail-empty-panel", js)
        self.assertIn("mail-list-empty-state", js)
        self.assertIn("mail-detail-placeholder", js)
        self.assertIn(".mail-empty-panel", css)
        self.assertIn(".mail-list-empty-state", css)
        self.assertIn(".mail-detail-placeholder", css)
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr)", css)
        self.assertIn('class="mail-list empty"', html)
        self.assertIn('el.mailList.classList.toggle("empty"', js)
        self.assertIn(".mail-list.empty", css)
        self.assertIn(".mail-list.empty .mail-empty-panel", css)
        self.assertNotIn("源码", html)
        self.assertNotIn("源码", js)

    def test_mail_result_summary_surfaces_session_metrics_without_extra_panels(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function accountFailureCount", js)
        self.assertIn("function resultAccountCount", js)
        self.assertIn("function renderMailSummary", js)
        self.assertIn("renderMailSummary(results);", js)
        self.assertIn("mail-summary-copy", js)
        self.assertIn("mail-summary-metrics", js)
        self.assertIn("summary-metric", js)
        self.assertIn("受限", js)
        self.assertIn("accountFailureCount()", js)
        self.assertIn("resultAccountCount(results)", js)
        self.assertIn("Array.from(state.accountStatus.values())", js)

        for selector in [
            ".mail-summary-copy",
            ".mail-summary-metrics",
            ".summary-metric",
            ".summary-metric.is-danger",
        ]:
            self.assertIn(selector, css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", css)
        self.assertIn("font-variant-numeric: tabular-nums", css)

    def test_mail_summary_is_live_and_loading_state_reuses_summary_system(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="mailSummary"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('aria-label="邮件结果摘要"', html)
        self.assertIn("function renderMailSummary(results, options = {})", js)
        self.assertIn('const summaryState = options.kind || (hasResults ? "ready" : "empty")', js)
        self.assertIn('const isLoading = summaryState === "loading"', js)
        self.assertIn("renderMailSummary([], { kind: \"loading\", label });", js)
        self.assertIn("summary-metric is-loading", js)
        self.assertNotIn('el.mailSummary.innerHTML = `\n    <strong>${escapeHtml(label)}</strong>', js)
        self.assertIn("正在连接账号并整理本次会话结果。", js)
        self.assertNotIn("正在连接账号并同步本次页面内结果。", js)
        self.assertIn(".summary-metric.is-loading", css)
        self.assertIn("border-color: transparent", css)

    def test_empty_mail_summary_has_zero_state_metrics_and_stateful_styling(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('class="mail-result-summary"', html)
        self.assertIn('data-state="empty"', html)
        self.assertIn('aria-label="待处理摘要"', html)
        self.assertIn("el.mailSummary.dataset.state = summaryState", js)
        self.assertIn('const isError = summaryState === "error"', js)
        self.assertIn('const summaryLabel = isLoading ? "同步状态" : isError ? "错误状态" : hasResults ? "本次拉取摘要" : "待处理摘要"', js)
        self.assertIn('const emptyMetrics = `', js)
        self.assertIn('summary-metric is-muted', js)
        self.assertIn("<span>状态</span><strong>待命</strong>", js)
        self.assertIn("<span>邮件</span><strong>0</strong>", js)
        self.assertIn("<span>账号</span><strong>${escapeHtml(state.accounts.length)}</strong>", js)
        self.assertIn(".mail-result-summary[data-state=\"empty\"]", css)
        self.assertIn(".summary-metric.is-muted", css)

    def test_mail_result_summary_reads_as_quiet_status_bar_not_feature_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        summary = css_rule(base_css, ".mail-result-summary")
        empty_summary = css_rule(base_css, '.mail-result-summary[data-state="empty"]')

        self.assertIn("min-height: 40px", summary)
        self.assertIn("gap: 10px", summary)
        self.assertIn("padding: 10px 12px", summary)
        self.assertIn("color-mix(in srgb, var(--line-soft) 78%, transparent)", summary)
        self.assertIn("color-mix(in srgb, var(--surface-soft) 46%, transparent)", summary)
        self.assertIn("color-mix(in srgb, var(--surface-raised) 28%, transparent)", summary)
        self.assertIn("box-shadow: none", summary)

        self.assertIn("color-mix(in srgb, var(--surface-soft) 54%, transparent)", empty_summary)
        self.assertIn("color-mix(in srgb, var(--surface-raised) 34%, transparent)", empty_summary)
        self.assertNotIn("radial-gradient(circle at 94% 16%", empty_summary)

        self.assertIn(".mail-result-summary", mobile_block)
        self.assertIn("gap: 4px", mobile_block)
        self.assertIn("padding: 8px 10px", mobile_block)
        self.assertIn(".mail-summary-metrics", mobile_block)
        self.assertIn("gap: 8px", mobile_block)

    def test_mobile_ready_mail_summary_uses_inline_ledger_to_preserve_first_viewport(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        ready_summary = re.search(
            r"\.mail-result-summary\[data-state=\"ready\"\] \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )
        ready_copy_span = re.search(
            r"\.mail-result-summary\[data-state=\"ready\"\] \.mail-summary-copy span \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )
        ready_metrics = re.search(
            r"\.mail-result-summary\[data-state=\"ready\"\] \.mail-summary-metrics \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )
        ready_divider = re.search(
            r"\.mail-result-summary\[data-state=\"ready\"\] \.summary-metric \+ \.summary-metric::before \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )

        self.assertIsNotNone(ready_summary)
        self.assertIsNotNone(ready_copy_span)
        self.assertIsNotNone(ready_metrics)
        self.assertIsNotNone(ready_divider)

        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", ready_summary.group("body"))
        self.assertIn("align-items: start", ready_summary.group("body"))
        self.assertIn("gap: 4px 8px", ready_summary.group("body"))
        self.assertIn("padding: 9px 10px", ready_summary.group("body"))
        self.assertNotIn("flex-direction: column", ready_summary.group("body"))

        self.assertIn("font-size: 11.25px", ready_copy_span.group("body"))
        self.assertIn("line-height: 1.2", ready_copy_span.group("body"))
        self.assertIn("white-space: nowrap", ready_copy_span.group("body"))
        self.assertIn("overflow: hidden", ready_copy_span.group("body"))
        self.assertIn("text-overflow: ellipsis", ready_copy_span.group("body"))

        self.assertIn("align-self: start", ready_metrics.group("body"))
        self.assertIn("justify-content: flex-end", ready_metrics.group("body"))
        self.assertIn("padding-top: 1px", ready_metrics.group("body"))
        self.assertIn("margin: 0 6px", ready_divider.group("body"))

    def test_empty_mail_workbench_connects_summary_to_reader_surface(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        bridge = css_rule(base_css, ".mail-result-summary + .mail-workbench")
        list_empty = css_rule(base_css, ".mail-list.empty")
        mobile_bridge = re.search(
            r"\.mail-result-summary \+ \.mail-workbench \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )

        self.assertIn("margin-top: -4px", bridge)
        self.assertIn("border-top-color: color-mix(in srgb, var(--line-soft) 52%, transparent)", bridge)
        self.assertIn("color-mix(in srgb, var(--surface-raised) 88%, var(--surface-soft))", bridge)
        self.assertNotIn("box-shadow", bridge)

        self.assertIn("padding: 12px", list_empty)
        self.assertIn("color-mix(in srgb, var(--surface-soft) 42%, transparent)", list_empty)

        self.assertIsNotNone(mobile_bridge)
        self.assertIn("margin-top: -2px", mobile_bridge.group("body"))

    def test_populated_mail_list_receives_summary_with_quiet_ingress(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        mail_list = css_rule(base_css, ".mail-list")
        dark_mail_list = css_rule(base_css, '[data-theme="dark"] .mail-list')
        mobile_mail_list = re.search(r"\.mail-list \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        mobile_dark_mail_list = re.search(
            r"\[data-theme=\"dark\"\] \.mail-list \{\n(?P<body>.*?)\n  \}",
            mobile_block,
            re.DOTALL,
        )

        self.assertIn("padding: 10px 10px 12px", mail_list)
        self.assertIn("scroll-padding-top: 10px", mail_list)
        self.assertIn("color-mix(in srgb, var(--surface-soft) 34%, transparent)", mail_list)
        self.assertIn("transparent 92px", mail_list)
        self.assertNotIn("box-shadow", mail_list)

        self.assertIn("color-mix(in srgb, var(--surface-soft) 24%, transparent)", dark_mail_list)
        self.assertIn("transparent 88px", dark_mail_list)

        self.assertIsNotNone(mobile_mail_list)
        self.assertIn("padding: 8px", mobile_mail_list.group("body"))
        self.assertIn("scroll-padding-top: 8px", mobile_mail_list.group("body"))
        self.assertIn("background: transparent", mobile_mail_list.group("body"))
        self.assertIsNotNone(mobile_dark_mail_list)
        self.assertIn("background: transparent", mobile_dark_mail_list.group("body"))

    def test_mail_result_summary_metrics_read_as_quiet_ledger_strip(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        copy_title = css_rule(base_css, ".mail-summary-copy strong")
        copy_description = css_rule(base_css, ".mail-summary-copy span")
        metrics = css_rule(base_css, ".mail-summary-metrics")
        metric = css_rule(base_css, ".summary-metric")
        metric_label = css_rule(base_css, ".summary-metric span")
        metric_value = css_rule(base_css, ".summary-metric strong")
        metric_divider = css_rule(base_css, ".summary-metric + .summary-metric::before")

        self.assertIn("font-size: 12.75px", copy_title)
        self.assertIn("line-height: 1.2", copy_title)
        self.assertIn("line-height: 1.32", copy_description)
        self.assertIn("gap: 2px 0", metrics)
        self.assertIn("gap: 3px", metric)
        self.assertIn("font-size: 10.75px", metric)
        self.assertIn("font-weight: 650", metric)
        self.assertIn("letter-spacing: -0.004em", metric)
        self.assertIn("color: color-mix(in srgb, var(--muted) 84%, transparent)", metric_label)
        self.assertIn("font-size: 10.5px", metric_label)
        self.assertIn("min-width: 1ch", metric_value)
        self.assertIn('content: ""', metric_divider)
        self.assertIn("width: 1px", metric_divider)
        self.assertIn("height: 10px", metric_divider)
        self.assertIn("margin: 0 8px", metric_divider)
        self.assertIn("background: color-mix(in srgb, var(--line-strong) 44%, transparent)", metric_divider)

        self.assertIn(".mail-summary-metrics", mobile_block)
        self.assertIn("gap: 3px 0", mobile_block)
        self.assertIn(".summary-metric + .summary-metric::before", mobile_block)
        self.assertIn("margin: 0 7px", mobile_block)

    def test_fetch_scope_defaults_to_selected_account_with_explicit_all_mode(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="selectedScopeBtn"', html)
        self.assertIn('id="allScopeBtn"', html)
        self.assertIn("选中账号", html)
        self.assertIn("全部账号", html)
        self.assertIn('fetchScope: "selected"', js)
        self.assertIn("selectedAccountEmail", js)
        self.assertIn("function selectedFetchAccountEmail", js)
        self.assertIn("payload.account = selectedAccountEmail;", js)
        self.assertIn("selectAccount(account.email)", js)
        self.assertIn("row.dataset.accountEmail = account.email", js)
        self.assertIn('row.className = `account-row ${isSelected ? "is-selected" : ""}`.trim();', js)
        self.assertIn(".scope-toggle-group", css)
        self.assertIn(".scope-toggle.is-active", css)
        self.assertIn(".account-row.is-selected", css)

    def test_low_frequency_fetch_options_live_in_collapsed_advanced_settings(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        operation = section_html(html, "控制台")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        details = re.search(r'<details class="advanced-settings">\s*(?P<body>.*?)\s*</details>', operation, re.DOTALL)
        self.assertIsNotNone(details)
        advanced_body = details.group("body")
        primary_path = operation[:details.start()]

        self.assertIn("<summary>", advanced_body)
        self.assertIn("<span>高级设置</span>", advanced_body)
        self.assertIn("<small>范围 · 邮箱目录 · 数量 · 原文</small>", advanced_body)
        self.assertNotIn('<details class="advanced-settings" open', operation)

        self.assertNotIn('class="scope-toggle-group"', primary_path)
        self.assertNotIn('id="selectedScopeBtn"', primary_path)
        self.assertNotIn('id="allScopeBtn"', primary_path)
        self.assertIn('class="scope-toggle-group"', advanced_body)
        self.assertIn('id="selectedScopeBtn"', advanced_body)
        self.assertIn('id="allScopeBtn"', advanced_body)
        self.assertIn('id="fetchBtn"', primary_path)
        self.assertIn('id="currentCodeSummary"', primary_path)
        self.assertIn("验证码摘要", primary_path)
        self.assertNotIn("复制当前验证码", primary_path)
        for low_frequency_id in ["mailboxInput", "limitInput", "rawFetchToggle", "selectedScopeBtn", "allScopeBtn"]:
            self.assertNotIn(f'id="{low_frequency_id}"', primary_path)
            self.assertIn(f'id="{low_frequency_id}"', advanced_body)

        self.assertIn(".advanced-settings", base_css)
        self.assertIn(".advanced-settings > summary", base_css)
        self.assertIn(".advanced-settings .operation-grid", base_css)
        self.assertIn(".advanced-settings .raw-fetch-toggle", base_css)
        self.assertIn(".advanced-settings", mobile_block)
        self.assertIn("min-height: 28px", mobile_block)

    def test_selected_account_row_reads_as_quiet_focus_not_alert_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]
        ultra_start = css.index("@media (max-width: 360px)")
        ultra_end = css.index("@media (prefers-reduced-motion: reduce)", ultra_start)
        ultra_block = css[ultra_start:ultra_end]

        selected = css_rule(base_css, ".account-row.is-selected")
        selected_pill = css_rule(base_css, ".account-row.is-selected .pill")

        self.assertIn("border-color: color-mix(in srgb, var(--accent) 18%, var(--line-soft))", selected)
        self.assertIn("background: linear-gradient(180deg, color-mix(in srgb, var(--accent-softer) 28%, var(--row-bg)), color-mix(in srgb, var(--row-bg) 92%, transparent))", selected)
        self.assertIn("box-shadow: inset 2px 0 0 color-mix(in srgb, var(--accent) 38%, transparent)", selected)
        self.assertNotIn("rgba(8, 120, 216, 0.45)", selected)
        self.assertNotIn("background: var(--accent-soft)", selected)
        self.assertNotIn("inset 3px 0 0 var(--accent)", selected)

        self.assertIn("border-color: color-mix(in srgb, var(--accent) 16%, var(--line-soft))", selected_pill)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 72%, transparent)", selected_pill)
        self.assertIn("color: color-mix(in srgb, var(--text) 78%, var(--muted))", selected_pill)
        self.assertNotIn("box-shadow", selected_pill)

        self.assertIn(".account-row.is-selected", mobile_block)
        self.assertIn("box-shadow: inset 2px 0 0 color-mix(in srgb, var(--accent) 34%, transparent)", mobile_block)
        self.assertIn(".account-row.is-selected", ultra_block)
        self.assertIn("box-shadow: inset 2px 0 0 color-mix(in srgb, var(--accent) 30%, transparent)", ultra_block)

    def test_account_click_filters_right_results_without_discarding_other_accounts(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("messagesByAccount: new Map()", js)
        self.assertIn("activeAccountEmail", js)
        self.assertIn("function messagesForAccount", js)
        self.assertIn("function visibleMessages", js)
        self.assertIn("function mergeFetchedMessagesByAccount", js)
        self.assertIn("state.messagesByAccount.set(email, messagesByAccount.get(email) || [])", js)
        self.assertIn("state.messagesByAccount.set(accountEmail, messages)", js)
        self.assertIn("renderResults(visibleMessages())", js)
        self.assertIn("selectInitialMessage(visibleMessages())", js)
        self.assertIn("state.activeAccountEmail = email", js)
        self.assertNotIn('state.fetchScope = "selected";\n  renderAccounts(state.accounts);', js)

    def test_all_account_fetch_updates_each_account_incrementally(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function accountsToFetch", js)
        self.assertIn("async function fetchOneAccount", js)
        self.assertIn("for (const account of accountsToFetch())", js)
        self.assertIn("renderFetchResult(accountData);", js)
        self.assertIn("setStatus(`正在拉取 ${account.email}`", js)

    def test_account_status_surfaces_fetch_elapsed_time(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function formatElapsedTime", js)
        self.assertIn("elapsed_ms: row.elapsed_ms", js)
        self.assertIn("${escapeHtml(formatElapsedTime(status.elapsed_ms))}", js)
        self.assertIn("耗时 ${formatElapsedTime(row.elapsed_ms)}", js)

    def test_account_status_keeps_fetch_diagnostics_out_of_rows(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function formatBytes", js)
        self.assertIn("function timingEntries", js)
        self.assertIn("function formatTimingBreakdown", js)
        self.assertIn("raw_bytes: row.raw_bytes", js)
        self.assertIn("timings: row.timings || {}", js)
        self.assertIn("下载 ${formatBytes(row.raw_bytes)}", js)
        self.assertIn("阶段 ${formatTimingBreakdown(row.timings)}", js)
        self.assertNotIn("慢点", js)
        self.assertNotIn("function slowestTimingLabel", js)
        self.assertNotIn("function accountDiagnosticText", js)
        self.assertNotIn("function accountDiagnosticMarkup", js)
        self.assertNotIn("account-row-diagnostic", js)
        self.assertNotIn(".account-row-diagnostic", css)

        status_pill = js[js.index("function statusPill"):js.index("function accountStatusLabel")]
        self.assertIn('title="${escapeHtml(accountStatusLabel(status))}"', status_pill)
        self.assertNotIn("diagnostic ? ` ·", status_pill)

    def test_mail_rows_surface_account_context_to_avoid_mixed_results(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("mail-row-meta-line", js)
        self.assertIn("mail-row-account", js)
        self.assertIn("${escapeHtml(mail.account_email || \"-\")}", js)
        self.assertIn(".mail-row-meta-line", css)
        self.assertIn(".mail-row-account", css)
        self.assertIn("text-overflow: ellipsis", css[css.index(".mail-row-account"):])

    def test_visual_noise_reduction_uses_restrained_chrome_and_metadata(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        section_kicker = re.search(r"\.section-kicker \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        detail_summary_item = re.search(r"\.detail-summary-item \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        reader_stat = re.search(r"\.reader-stat \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        summary_metric = re.search(r"\.summary-metric \{\n(?P<body>.*?)\n\}", css, re.DOTALL)

        self.assertIsNotNone(section_kicker)
        self.assertIsNotNone(detail_summary_item)
        self.assertIsNotNone(reader_stat)
        self.assertIsNotNone(summary_metric)

        self.assertIn("grid-template-columns: clamp(390px, 42%, 520px) minmax(0, 1fr)", css)

        self.assertIn("display: none", section_kicker.group("body"))
        self.assertNotIn("var(--accent-strong)", section_kicker.group("body"))

        self.assertIn("border-block: 0", css)
        self.assertIn("border: 0", detail_summary_item.group("body"))
        self.assertIn("background: transparent", detail_summary_item.group("body"))
        self.assertNotIn("border-radius: var(--radius-md)", detail_summary_item.group("body"))

        self.assertIn("reader-stat-separator", js)
        self.assertIn('<span class="reader-stat-separator" aria-hidden="true">·</span>', js)
        self.assertIn("border: 0", reader_stat.group("body"))
        self.assertIn("background: transparent", reader_stat.group("body"))
        self.assertNotIn("border-radius: 999px", reader_stat.group("body"))

        self.assertIn("border: 0", summary_metric.group("body"))
        self.assertIn("background: transparent", summary_metric.group("body"))

        body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        body_title = re.search(r"^\.body-card-title \{\n(?P<body>.*?)\n\}", css, re.DOTALL | re.MULTILINE)
        operation_note = re.search(r"\.operation-note \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        operation_note_badge = re.search(r"\.operation-note > span::before \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        mail_dot = re.search(r"\.mail-row-status-dot \{\n(?P<body>.*?)\n\}", css, re.DOTALL)
        active_mail_dot = re.search(
            r"\.mail-row\.active \.mail-row-status-dot,\n"
            r"\.mail-row\[aria-selected=\"true\"\] \.mail-row-status-dot \{\n(?P<body>.*?)\n\}",
            css,
            re.DOTALL,
        )

        self.assertIsNotNone(body_card)
        self.assertIsNotNone(body_title)
        self.assertIsNotNone(operation_note)
        self.assertIsNotNone(operation_note_badge)
        self.assertIsNotNone(mail_dot)
        self.assertIsNotNone(active_mail_dot)

        self.assertIn("border: 0", body_card.group("body"))
        self.assertIn("background: transparent", body_card.group("body"))
        self.assertNotIn("border-radius: var(--radius-lg)", body_card.group("body"))
        self.assertIn("border-bottom: 0", body_title.group("body"))
        self.assertIn("background: transparent", operation_note.group("body"))
        self.assertNotIn("var(--accent-softer)", operation_note.group("body"))
        self.assertIn("background: var(--subtle)", operation_note_badge.group("body"))
        self.assertIn("background: var(--subtle)", mail_dot.group("body"))
        self.assertIn("background: var(--accent)", active_mail_dot.group("body"))

    def test_dark_mail_workbench_uses_quiet_layering_instead_of_heavy_blocks(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        workbench = css_rule(css, '[data-theme="dark"] .mail-workbench')
        list_shell = css_rule(css, '[data-theme="dark"] .mail-list-shell')
        reader_shell = css_rule(css, '[data-theme="dark"] .mail-reader-shell')

        self.assertIn("border-color: rgba(148, 163, 184, 0.14)", workbench)
        self.assertIn("background: rgba(15, 23, 42, 0.52)", workbench)
        self.assertIn("0 12px 30px rgba(0, 0, 0, 0.18)", workbench)
        self.assertIn("border-right-color: rgba(148, 163, 184, 0.12)", list_shell)
        self.assertIn("rgba(15, 23, 42, 0.50)", list_shell)
        self.assertIn("rgba(15, 23, 42, 0.38)", list_shell)
        self.assertIn("rgba(148, 163, 184, 0.045)", reader_shell)
        self.assertNotIn("rgba(148, 163, 184, 0.075)", reader_shell)

    def test_desktop_mail_reader_seam_guides_focus_without_heavy_divider(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        tablet_start = css.index("@media (max-width: 980px)")
        tablet_end = css.index("@media (max-width: 720px)", tablet_start)
        tablet_block = css[tablet_start:tablet_end]

        reader_shell_rules = re.findall(r"^\.mail-reader-shell \{\n(?P<body>.*?)\n\}", base_css, re.DOTALL | re.MULTILINE)
        reader_seam = css_rule(base_css, ".mail-reader-shell::after")
        dark_reader_seam = css_rule(css, '[data-theme="dark"] .mail-reader-shell::after')
        tablet_reader_seam = re.search(r"\.mail-reader-shell::after \{\n(?P<body>.*?)\n  \}", tablet_block, re.DOTALL)

        self.assertTrue(reader_shell_rules)
        reader_shell = reader_shell_rules[-1]
        self.assertIn("isolation: isolate", reader_shell)
        self.assertIn('content: ""', reader_seam)
        self.assertIn("position: absolute", reader_seam)
        self.assertIn("inset: 0 auto 0 0", reader_seam)
        self.assertIn("width: 1px", reader_seam)
        self.assertIn("pointer-events: none", reader_seam)
        self.assertIn("opacity: 0.72", reader_seam)
        self.assertIn("linear-gradient(180deg, transparent 0", reader_seam)
        self.assertIn("color-mix(in srgb, var(--accent) 16%, transparent)", reader_seam)
        self.assertIn("color-mix(in srgb, var(--line-soft) 72%, transparent)", reader_seam)
        self.assertNotIn("box-shadow", reader_seam)

        self.assertIn("opacity: 0.58", dark_reader_seam)
        self.assertIn("color-mix(in srgb, var(--accent-strong) 16%, transparent)", dark_reader_seam)

        self.assertIsNotNone(tablet_reader_seam)
        self.assertIn("display: none", tablet_reader_seam.group("body"))

    def test_empty_mail_placeholders_feel_guided_instead_of_blank(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        for active_class_name in [
            "placeholder-reader-frame",
            "placeholder-meta-grid",
            "placeholder-line",
            "placeholder-line short",
            "is-preview-selected",
        ]:
            self.assertIn(active_class_name, html)
            self.assertIn(active_class_name, js)

        for inactive_class_name in ["mail-empty-guide", "mail-empty-step"]:
            self.assertNotIn(inactive_class_name, html)
            self.assertNotIn(inactive_class_name, js)

        self.assertIn("等待邮件", html)
        self.assertIn("邮件详情", html)
        self.assertNotIn("等待本次拉取", html)
        self.assertNotIn("选择邮件查看详情", html)
        self.assertIn('aria-label="空邮件列表引导"', html)
        self.assertIn('aria-label="阅读区占位预览"', html)
        self.assertIn("当前会话预览", js)
        self.assertIn("关键头信息", js)

        for selector in [
            ".placeholder-reader-frame",
            ".placeholder-meta-grid",
            ".placeholder-line",
            ".placeholder-line.short",
            ".mail-empty-row.is-preview-selected",
            ".mail-empty-row.is-preview-selected .mail-row-status-dot",
        ]:
            self.assertIn(selector, css)

        preview_row = css_rule(css, ".mail-empty-row.is-preview-selected")
        preview_dot = css_rule(css, ".mail-empty-row.is-preview-selected .mail-row-status-dot")
        self.assertIn("border-color: color-mix(in srgb, var(--accent) 16%, var(--line-soft))", preview_row)
        self.assertIn("inset 2px 0 0", preview_row)
        self.assertIn("background: var(--accent)", preview_dot)

    def test_mail_empty_preview_rows_are_subtle_but_visible(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        rows = css_rule(css, ".mail-empty-rows")
        row = css_rule(css, ".mail-empty-row")
        selected = css_rule(css, ".mail-empty-row.is-preview-selected")
        muted = css_rule(css, ".mail-empty-row.is-muted")
        dark_row = css_rule(css, '[data-theme="dark"] .mail-empty-row')
        line_rule = re.search(
            r"\.mail-empty-row-subject,\n\.mail-empty-row-meta,\n\.mail-empty-row-time \{\n(?P<body>.*?)\n\}",
            css,
            re.DOTALL,
        )

        self.assertIsNotNone(line_rule)
        line_body = line_rule.group("body")

        self.assertIn("gap: 7px", rows)
        self.assertIn("width: min(100%, 318px)", rows)
        self.assertIn("grid-template-columns: 7px minmax(0, 1fr) 40px", row)
        self.assertIn("min-height: 46px", row)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-soft) 82%, transparent)", row)
        self.assertIn("box-shadow: none", row)
        self.assertIn("color-mix(in srgb, var(--accent) 16%, var(--line-soft))", selected)
        self.assertIn("color-mix(in srgb, var(--accent) 45%, transparent)", selected)
        self.assertNotIn("0 6px 14px", selected)
        self.assertIn("opacity: 0.66", muted)
        self.assertIn("height: 6px", line_body)
        self.assertIn("color-mix(in srgb, var(--line-soft) 68%, transparent)", line_body)
        self.assertIn("color-mix(in srgb, var(--accent-softer) 48%, var(--line-soft))", line_body)
        self.assertIn("rgba(15, 23, 42, 0.34)", dark_row)
        self.assertIn("rgba(15, 23, 42, 0.24)", dark_row)
        self.assertIn('[data-theme="dark"] .mail-empty-row-subject', css)
        self.assertIn("color-mix(in srgb, var(--line-strong) 28%, transparent)", css)

    def test_mail_empty_guide_uses_quiet_status_rail_not_fake_controls(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        guide = css_rule(css, ".mail-empty-guide")
        step = css_rule(css, ".mail-empty-step")
        list_step = css_rule(css, ".mail-empty-panel.mail-list-empty-state .mail-empty-step")
        step_dot = css_rule(css, ".mail-empty-step i")
        first_step = css_rule(css, ".mail-empty-step:first-child")
        list_first_step = css_rule(css, ".mail-empty-panel.mail-list-empty-state .mail-empty-step:first-child")
        first_dot = css_rule(css, ".mail-empty-step:first-child i")

        self.assertIn("gap: 6px 10px", guide)
        self.assertIn("color: var(--subtle)", guide)
        self.assertIn("min-height: 16px", step)
        self.assertIn("padding: 0", step)
        self.assertIn("border: 0", step)
        self.assertIn("border-radius: 0", step)
        self.assertIn("background: transparent", step)
        self.assertIn("box-shadow: none", step)
        self.assertIn("font-size: 10.75px", step)
        self.assertIn("font-size: 10.75px", list_step)
        self.assertIn("line-height: 1.2", list_step)
        self.assertIn("max-width: none", list_step)
        self.assertIn("background: var(--subtle)", step_dot)
        self.assertIn("box-shadow: none", step_dot)
        self.assertIn("color: var(--muted)", first_step)
        self.assertIn("color: var(--muted)", list_first_step)
        self.assertIn("background: var(--accent)", first_dot)
        self.assertNotIn("border: 1px solid var(--line-soft)", step)
        self.assertNotIn("var(--surface-glass)", step)

    def test_reader_empty_state_is_quiet_reading_hint_not_heavy_placeholder(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        hero = css_rule(base_css, ".mail-empty-hero")
        detail_start = base_css.index(".mail-detail-placeholder {\n  min-height: clamp")
        detail_end = base_css.index(".mail-detail-placeholder .mail-empty-icon", detail_start)
        detail_placeholder = base_css[detail_start:detail_end]
        detail_icon = css_rule(base_css, ".mail-detail-placeholder .mail-empty-icon")
        reader_frame = css_rule(base_css, ".placeholder-reader-frame")
        meta_line = css_rule(base_css, ".placeholder-meta-grid span")
        placeholder_line = css_rule(base_css, ".placeholder-line")

        self.assertIn("color-mix(in srgb, var(--accent-softer) 38%, transparent)", hero)
        self.assertIn("transparent 9.5rem", hero)
        self.assertNotIn("linear-gradient(180deg, rgba(8, 120, 216, 0.024)", hero)

        self.assertIn("min-height: clamp(196px, 24vh, 232px)", detail_placeholder)
        self.assertIn("gap: 5px", detail_placeholder)
        self.assertIn("padding: 14px", detail_placeholder)
        self.assertIn("opacity: 0.78", detail_placeholder)
        self.assertIn("width: 34px", detail_icon)
        self.assertIn("height: 34px", detail_icon)
        self.assertIn("color: var(--subtle)", detail_icon)
        self.assertIn("box-shadow: none", detail_icon)

        self.assertIn("width: min(310px, 88%)", reader_frame)
        self.assertIn("gap: 8px", reader_frame)
        self.assertIn("padding: 10px", reader_frame)
        self.assertIn("color-mix(in srgb, var(--line-soft) 76%, transparent)", reader_frame)
        self.assertIn("opacity: 0.64", reader_frame)
        self.assertIn("height: 7px", meta_line)
        self.assertIn("height: 6px", placeholder_line)
        self.assertIn("opacity: 0.52", placeholder_line)

        self.assertIn(".mail-reader-shell", mobile_block)
        self.assertIn("min-height: 286px", mobile_block)
        self.assertIn(".mail-detail-placeholder", mobile_block)
        self.assertIn("min-height: 196px", mobile_block)
        self.assertNotIn("min-height: 324px", mobile_block)
        self.assertNotIn("min-height: 246px", mobile_block)

    def test_mobile_reader_empty_hint_stays_compact_and_airier(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        reader_shell = re.search(r"\.mail-reader-shell \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        detail_placeholder = re.search(r"\.mail-detail-placeholder \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        detail_icon = re.search(r"\.mail-detail-placeholder \.mail-empty-icon \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        reader_frame = re.search(r"\.placeholder-reader-frame \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)

        self.assertIsNotNone(reader_shell)
        self.assertIsNotNone(detail_placeholder)
        self.assertIsNotNone(detail_icon)
        self.assertIsNotNone(reader_frame)

        self.assertIn("min-height: 286px", reader_shell.group("body"))
        self.assertIn("transparent 72px", reader_shell.group("body"))
        self.assertIn("min-height: 196px", detail_placeholder.group("body"))
        self.assertIn("gap: 4px", detail_placeholder.group("body"))
        self.assertIn("padding: 12px 10px 16px", detail_placeholder.group("body"))
        self.assertIn("width: 30px", detail_icon.group("body"))
        self.assertIn("height: 30px", detail_icon.group("body"))
        self.assertIn("width: min(280px, 86%)", reader_frame.group("body"))
        self.assertIn("gap: 6px", reader_frame.group("body"))
        self.assertIn("padding: 8px", reader_frame.group("body"))
        self.assertIn("color-mix(in srgb, var(--line-soft) 66%, transparent)", reader_frame.group("body"))
        self.assertNotIn("min-height: 306px", reader_shell.group("body"))
        self.assertNotIn("min-height: 224px", detail_placeholder.group("body"))

    def test_account_status_rows_do_not_expose_credentials(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("account-email-label", js)
        self.assertIn("copy-account-icon", js)
        self.assertNotIn("password ${escapeHtml(account.password)}", js)
        self.assertNotIn("client ${escapeHtml(account.client_id)}", js)
        self.assertNotIn("refresh ${escapeHtml(account.refresh_token)}", js)
        self.assertNotIn("line ${escapeHtml(account.line)}", js)
        self.assertNotIn("account.client_id", js)
        self.assertNotIn("account.refresh_token", js)

    def test_account_empty_state_is_guided_and_privacy_preserving(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        empty_start = js.index('aria-label="账号状态待命"')
        empty_end = js.index("return;", empty_start)
        account_empty_block = js[empty_start:empty_end]

        self.assertIn("account-empty-panel", js)
        self.assertIn("等待账号", account_empty_block)
        self.assertIn("粘贴后自动读取账号状态。", account_empty_block)
        self.assertIn("account-empty-guide", account_empty_block)
        self.assertIn("account-empty-chip", account_empty_block)
        self.assertIn("自动读取", account_empty_block)
        self.assertIn("隐私保护", account_empty_block)
        self.assertNotIn("三步开始", js)
        self.assertNotIn("粘贴账号 → 拉取邮件 → 查看验证码", js)
        self.assertNotIn("查看验证码", account_empty_block)
        self.assertNotIn("等待账号输入", js)
        self.assertNotIn("粘贴账号后会自动解析，并显示拉取状态。", js)
        self.assertIn(".account-empty-panel", css)
        self.assertIn(".account-empty-guide", css)
        self.assertIn(".account-empty-chip", css)
        self.assertNotIn("等待账号状态", js)

    def test_initial_empty_state_uses_compact_product_skeletons_not_stretched_hero_cards(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("controlColumn", js)
        self.assertIn("accountInputPanel", js)
        self.assertIn("isInitialEmpty", js)
        self.assertIn('classList.toggle("is-initial-empty"', js)
        self.assertIn('classList.toggle("is-empty"', js)

        self.assertIn(".control-column.is-initial-empty", css)
        self.assertIn("height: auto", css)
        self.assertIn("align-content: start", css)
        self.assertIn("grid-template-rows: auto auto minmax(174px, auto)", css)
        self.assertIn(".control-column.is-initial-empty {\n  gap: 10px;", css)
        self.assertIn(
            ".control-column.is-initial-empty .run-log-panel {\n"
            "  min-height: 168px;\n"
            "  gap: 8px;\n"
            "  padding: 10px;",
            css,
        )
        self.assertIn(
            ".control-column.is-initial-empty .activity-log:empty {\n"
            "  padding: 10px;",
            css,
        )
        self.assertIn(".account-input-panel.is-initial-empty", css)
        self.assertIn(
            ".account-input-panel.is-initial-empty {\n"
            "  grid-template-rows: auto minmax(76px, auto) auto auto auto;",
            css,
        )
        self.assertIn(
            ".account-input-panel.is-initial-empty textarea {\n"
            "  min-height: 72px;\n"
            "  max-height: 88px;",
            css,
        )
        self.assertIn(".account-list.is-empty", css)
        self.assertIn("align-self: start", css)
        self.assertIn("overflow: visible", css)

        self.assertIn("mail-empty-row", js)
        self.assertIn("mail-empty-row-subject", js)
        self.assertIn("mail-empty-row-meta", js)
        self.assertIn(".mail-empty-row", css)
        self.assertIn(".mail-list.empty .mail-empty-panel", css)
        self.assertIn("min-height: 0", css)
        self.assertNotIn("min-height: 100%;\n}", css[css.index(".mail-list.empty .mail-empty-panel"):css.index(".mail-list-empty-state")])

    def test_account_status_shows_pending_state_for_unparsed_input(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("isPreflight", js)
        self.assertIn('classList.toggle("is-preflight"', js)
        self.assertIn(".control-column.is-preflight", css)
        self.assertIn(".account-input-panel.is-preflight", css)
        self.assertIn(
            ".control-column.is-initial-empty,\n.control-column.is-preflight",
            css,
        )
        self.assertIn(
            ".account-input-panel.is-initial-empty,\n.account-input-panel.is-preflight",
            css,
        )
        self.assertIn("account-pending-panel", js)
        self.assertIn("账号等待解析", js)
        self.assertIn("${escapeHtml(report.totalLines)} 行等待解析", js)
        self.assertIn("格式完整后会自动读取账号", js)
        self.assertIn("待读取", js)
        self.assertIn("格式检查", js)
        self.assertIn("只显示邮箱", js)
        self.assertLess(js.index("const report = inspectAccountText"), js.index("account-pending-panel"))

        self.assertIn(".account-pending-panel", css)
        self.assertIn(".account-pending-panel .account-empty-chip", css)
        self.assertIn("border-style: solid", css)

    def test_operation_account_state_stays_compact_for_three_or_more_accounts(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("isAccountCompact", js)
        self.assertIn("accounts.length > 0", js)
        self.assertIn("hasSessionState", js)
        self.assertIn("const shouldKeepAccountCompact", js)
        self.assertIn("hasSessionState || !hasSessionMessages", js)
        self.assertNotIn("accounts.length <= 2", js)
        self.assertNotIn("accounts.length <= 2 && !hasSessionMessages", js)
        self.assertIn('classList.toggle("is-account-compact"', js)

        self.assertIn(".control-column.is-account-compact", css)
        self.assertIn(".account-input-panel.is-account-compact", css)
        self.assertIn(
            ".control-column.is-initial-empty,\n"
            ".control-column.is-preflight,\n"
            ".control-column.is-account-compact",
            css,
        )
        self.assertIn(
            ".account-input-panel.is-initial-empty,\n"
            ".account-input-panel.is-preflight,\n"
            ".account-input-panel.is-account-compact",
            css,
        )

    def test_account_status_empty_state_fits_control_panel_without_clipping(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("grid-template-rows: minmax(0, 1fr) auto 184px", css)
        self.assertIn("grid-template-rows: auto minmax(96px, auto) auto auto minmax(0, 1fr)", css)
        self.assertNotIn("grid-template-rows: auto minmax(96px, auto) auto auto auto minmax(0, 1fr)", css)
        self.assertIn(".account-empty-panel", css)
        self.assertIn("min-height: 58px", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", css)
        self.assertIn("text-align: left", css)
        self.assertIn(".account-empty-guide", css)
        self.assertIn("grid-column: 2", css)
        self.assertIn("grid-row: 1 / 3", css)

    def test_account_status_rows_keep_two_accounts_visible_on_short_desktop(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media", media_start + 1)
        short_desktop_css = css[media_start:media_end]

        self.assertIn(
            "grid-template-rows: auto minmax(56px, auto) auto auto minmax(68px, 1fr);",
            short_desktop_css,
        )
        self.assertIn(".account-input-panel {\n    min-height: 0;\n    overflow: hidden;\n    gap: 5px;", short_desktop_css)
        self.assertIn(".account-input-panel textarea {\n    min-height: 56px;\n    max-height: 60px;", short_desktop_css)
        self.assertIn(".account-list {\n    max-height: none;\n    min-height: 68px;", short_desktop_css)
        self.assertIn(".account-empty-panel {\n    min-height: 68px;\n    padding: 6px 8px;", short_desktop_css)
        self.assertIn(".account-empty-guide {\n    display: none;", short_desktop_css)
        self.assertIn(".input-quality {\n    grid-template-columns: minmax(0, 1fr) auto;", short_desktop_css)
        self.assertIn(".quality-copy {\n    display: contents;", short_desktop_css)
        self.assertIn(".quality-copy > span:not(.quality-chip) {\n    display: none;", short_desktop_css)

    def test_account_empty_state_stacks_on_extra_narrow_screens(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        narrow_css = css[media_start:media_end]

        self.assertIn(".account-empty-panel", narrow_css)
        self.assertIn("grid-template-columns: 1fr", narrow_css)
        self.assertIn(".account-empty-panel > span", narrow_css)
        self.assertIn("white-space: normal", narrow_css)
        self.assertIn("text-overflow: clip", narrow_css)
        self.assertIn(".account-empty-guide", narrow_css)
        self.assertIn("grid-column: 1", narrow_css)
        self.assertIn("justify-content: flex-start", narrow_css)

    def test_account_status_and_logs_use_product_copy_instead_of_raw_debug_terms(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function statusStageLabel", js)
        self.assertIn("function accountStatusLabel", js)
        self.assertIn('fetch: "拉取"', js)
        self.assertNotIn('check: "检测"', js)
        self.assertIn('oauth: "OAuth"', js)
        self.assertIn('auth: "认证"', js)
        self.assertIn('select: "选目录"', js)
        self.assertIn('connect: "连接"', js)
        self.assertIn('return labels[stage] || "处理"', js)
        self.assertIn('失败 · ${escapeHtml(statusStageLabel(status.stage))}', js)
        self.assertIn('stage: row.stage || "fetch"', js)
        self.assertIn("const statusLabel = accountStatusLabel(status)", js)
        self.assertIn("row.title = status ? `${account.email}：${statusLabel}` : account.email", js)
        self.assertIn("function failureAccessibilityLabel(status)", js)
        self.assertIn('selectButton.setAttribute("aria-label", `${account.email}，${isSelected ? "当前选中，" : ""}${failureAccessibilityLabel(status)}`)', js)
        self.assertIn("已拉取 ${row.fetched} 封邮件", js)
        self.assertNotIn('class="error-text"', js)
        self.assertNotIn('失败 · ${escapeHtml(status.stage || "unknown")}', js)
        self.assertNotIn("fetched=${row.fetched}", js)
        self.assertNotIn("unknown", js)

    def test_account_rows_copy_only_from_icon_and_select_from_main_area(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        self.assertIn('<symbol id="icon-copy"', html)
        self.assertIn('className = `account-row ${isSelected ? "is-selected" : ""}`.trim()', js)
        self.assertIn('className = "account-select-button account-status-button"', js)
        self.assertIn('className = "copy-account-button account-copy-zone"', js)
        self.assertIn('class="copy-account-icon"', js)
        self.assertIn('class="account-email-label"', js)
        self.assertNotIn('class="account-copy-email"', js)
        self.assertNotIn('copyButton.textContent = "复制"', js)
        self.assertIn('copyButton.setAttribute("aria-label", `复制邮箱账号 ${account.email}`)', js)
        self.assertIn('copyButton.addEventListener("click", (event) => {', js)
        self.assertIn("event.stopPropagation()", js)
        self.assertIn("copyAccountEmail(account.email)", js)
        self.assertIn('selectButton.addEventListener("click", () => selectAccount(account.email));', js)
        self.assertIn("navigator.clipboard.writeText(email)", js)
        self.assertIn('document.execCommand("copy")', js)
        self.assertIn('setStatus("已复制邮箱账号", "success")', js)
        self.assertIn('setStatus("已选择账号", "ready")', js)
        self.assertIn("appendLog(`已复制 ${email}`", js)
        self.assertIn("row.append(copyButton, selectButton)", js)
        self.assertLess(js.index("row.append(copyButton, selectButton)"), js.index("el.accountList.append(row)"))
        self.assertNotIn("shell.append(button, copyButton)", js)

        row = css_rule(base_css, ".account-row")
        select_button = css_rule(base_css, ".account-select-button")
        status_button = css_rule(base_css, ".account-status-button")
        copy_button = css_rule(base_css, ".copy-account-button")
        copy_icon_wrap = css_rule(base_css, ".copy-account-icon")
        copy_icon = css_rule(base_css, ".copy-account-button .icon")
        copy_hover = css_rule(base_css, ".copy-account-button:hover")
        copy_selected = css_rule(base_css, ".account-row.is-selected .copy-account-button")
        account_email = css_rule(base_css, ".account-email-label")
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", row)
        self.assertIn("gap: 6px", row)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", select_button)
        self.assertIn("justify-self: stretch", select_button)
        self.assertIn("text-align: left", select_button)
        self.assertIn("min-height: 44px", status_button)
        self.assertNotIn("border-left", status_button)
        self.assertIn("border: 0", copy_button)
        self.assertIn("background: transparent", copy_button)
        self.assertIn("border-radius: calc(var(--radius-sm) - 3px)", copy_button)
        self.assertNotIn("border-radius: 999px", copy_button)
        self.assertIn("width: 44px", copy_button)
        self.assertIn("min-width: 44px", copy_button)
        self.assertIn("cursor: copy", copy_button)
        self.assertIn("position: relative", copy_button)
        self.assertNotIn("grid-template-columns: 48px minmax(0, 1fr)", copy_button)
        self.assertIn("min-height: 44px", copy_button)
        self.assertNotIn(".copy-account-button::after", base_css)
        self.assertIn("width: 36px", copy_icon_wrap)
        self.assertNotIn("padding-right", copy_icon_wrap)
        self.assertNotIn("border-right", copy_icon_wrap)
        self.assertIn("width: 14px", copy_icon)
        self.assertIn("height: 14px", copy_icon)
        self.assertIn("text-overflow: ellipsis", account_email)
        self.assertIn("white-space: nowrap", account_email)
        self.assertIn("background: color-mix(in srgb, var(--accent-softer) 54%, transparent)", copy_hover)
        self.assertIn("color: var(--text-strong)", copy_hover)
        self.assertIn("color: color-mix(in srgb, var(--accent) 72%, var(--text))", copy_selected)
        self.assertNotIn("border-color", copy_selected)

    def test_activity_events_are_structured_product_timeline_not_log_lines(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('const level = kind === "fail" ? "错误" : kind === "ok" ? "成功" : "信息"', js)
        self.assertNotIn('const level = kind === "fail" ? "ERROR" : kind === "ok" ? "OK" : "INFO"', js)
        self.assertIn("activity-event", js)
        self.assertIn("activity-event-meta", js)
        self.assertIn("activity-event-kind", js)
        self.assertIn("activity-event-time", js)
        self.assertIn("activity-event-message", js)
        self.assertNotIn("log-level-chip", js)
        self.assertIn(".activity-event", css)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", css)
        self.assertIn(".activity-event::before", css)
        self.assertIn(".activity-event-body", css)
        self.assertIn(".activity-event-kind", css)
        self.assertIn(".activity-event-time", css)
        self.assertIn(".activity-event-message", css)
        self.assertIn("grid-template-columns: auto minmax(108px, 0.64fr) minmax(0, 1fr) auto", css)
        self.assertIn(".activity-event-account {\n  grid-column: 2;\n  grid-row: 1;", css)
        self.assertIn(".activity-event-message {\n  grid-column: 3;\n  grid-row: 1;", css)
        self.assertIn(".activity-event-time {\n  grid-column: 4;\n  grid-row: 1;", css)
        self.assertIn("text-overflow: ellipsis", css)
        self.assertIn(".activity-event.ok .activity-event-kind", css)
        self.assertIn(".activity-event.fail .activity-event-kind", css)
        self.assertNotIn(".log-level-chip", css)

    def test_populated_activity_events_separate_account_context_from_detail(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function splitLogMessage", js)
        self.assertIn("const logParts = splitLogMessage(message)", js)
        self.assertIn("activity-event-account", js)
        self.assertIn("logParts.context", js)
        self.assertIn("logParts.detail", js)
        self.assertIn(".activity-event-account", css)
        self.assertIn(".activity-event-account {\n  grid-column: 2;\n  grid-row: 1;", css)
        self.assertIn(".activity-event-message {\n  grid-column: 3;\n  grid-row: 1;", css)
        self.assertIn(".activity-event.fail .activity-event-message", css)
        self.assertIn("color: var(--activity-muted)", css)

    def test_activity_events_read_as_quiet_event_stream_with_metadata_hierarchy(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        event = css_rule(base_css, ".activity-event")
        event_dot = css_rule(base_css, ".activity-event::before")
        event_body = css_rule(base_css, ".activity-event-body")
        event_kind = css_rule(base_css, ".activity-event-kind")
        event_account = css_rule(base_css, ".activity-event-account")
        event_time = css_rule(base_css, ".activity-event-time")
        event_message = css_rule(base_css, ".activity-event-message")
        ok_event = css_rule(base_css, ".activity-event.ok")
        fail_event = css_rule(base_css, ".activity-event.fail")
        fail_account = css_rule(base_css, ".activity-event.fail .activity-event-account")

        self.assertIn("padding: 6px 8px", event)
        self.assertIn("color-mix(in srgb, var(--activity-line) 72%, transparent)", event)
        self.assertIn("color-mix(in srgb, var(--activity-bar) 46%, transparent)", event)
        self.assertIn("box-shadow: none", event)
        self.assertIn("width: 6px", event_dot)
        self.assertIn("height: 6px", event_dot)
        self.assertIn("0 0 0 2px var(--event-ring)", event_dot)
        self.assertIn("grid-template-columns: auto minmax(108px, 0.64fr) minmax(0, 1fr) auto", event_body)
        self.assertIn("gap: 2px 8px", event_body)
        self.assertIn("min-height: 15px", event_kind)
        self.assertIn("font-size: 9.25px", event_kind)
        self.assertIn("font-weight: 720", event_kind)
        self.assertIn("font-size: 11.25px", event_account)
        self.assertIn("font-weight: 700", event_account)
        self.assertIn("color: color-mix(in srgb, var(--activity-muted) 78%, transparent)", event_time)
        self.assertIn("font-size: 9.75px", event_time)
        self.assertIn("font-weight: 620", event_time)
        self.assertIn("color: color-mix(in srgb, var(--activity-muted) 82%, transparent)", event_message)
        self.assertIn("font-size: 10.75px", event_message)
        self.assertIn("opacity: 0.88", event_message)
        self.assertIn("color-mix(in srgb, var(--ok) 14%, var(--activity-line))", ok_event)
        self.assertIn("color-mix(in srgb, var(--danger) 16%, var(--activity-line))", fail_event)
        self.assertIn("color: color-mix(in srgb, var(--danger) 78%, var(--activity-text))", fail_account)

    def test_account_header_actions_read_as_quiet_status_capsule(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        self.assertIn('id="privacyToggle"', html)
        self.assertIn('id="accountCount" class="count-chip"', html)

        actions = css_rule(base_css, ".account-input-panel .section-actions")
        privacy = css_rule(base_css, ".account-input-panel .section-actions .privacy-toggle")
        privacy_pressed = css_rule(base_css, ".account-input-panel .section-actions .privacy-toggle[aria-pressed=\"true\"]")
        count = css_rule(base_css, ".account-input-panel .section-actions .count-chip")
        count_divider = css_rule(base_css, ".account-input-panel .section-actions .count-chip::before")

        self.assertIn("gap: 2px", actions)
        self.assertIn("padding: 2px", actions)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-soft) 82%, transparent)", actions)
        self.assertIn("background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 68%, transparent), color-mix(in srgb, var(--surface-raised) 34%, transparent))", actions)
        self.assertIn("box-shadow: none", actions)

        self.assertIn("min-height: 24px", privacy)
        self.assertIn("border: 0", privacy)
        self.assertIn("background: transparent", privacy)
        self.assertIn("box-shadow: none", privacy)
        self.assertIn("color: var(--muted)", privacy)
        self.assertIn("color: var(--text-strong)", privacy_pressed)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 68%, transparent)", privacy_pressed)

        self.assertIn("position: relative", count)
        self.assertIn("border: 0", count)
        self.assertIn("background: transparent", count)
        self.assertIn("padding-left: 10px", count)
        self.assertIn('content: ""', count_divider)
        self.assertIn("width: 1px", count_divider)
        self.assertIn("height: 12px", count_divider)
        self.assertIn("background: color-mix(in srgb, var(--line-soft) 88%, transparent)", count_divider)

        self.assertIn(".account-input-panel .section-actions", mobile_block)
        self.assertIn("gap: 2px", mobile_block)
        self.assertIn("padding: 2px", mobile_block)
        self.assertIn(".account-input-panel .section-actions .privacy-toggle", mobile_block)
        self.assertIn("min-height: 23px", mobile_block)
        self.assertIn(".account-input-panel .section-actions .count-chip", mobile_block)
        self.assertIn("min-height: 23px", mobile_block)

    def test_account_input_supports_demo_privacy_mask_without_changing_value(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="privacyToggle"', html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn("隐私保护", html)
        self.assertIn("输入后自动遮蔽敏感字段", html)
        self.assertIn('autocomplete="off"', html)
        self.assertIn('autocapitalize="none"', html)
        self.assertIn('data-private="false"', html)
        self.assertIn("accountPrivacy: true", js)
        self.assertIn('privacyToggle: document.getElementById("privacyToggle")', js)
        self.assertIn("function syncAccountPrivacy", js)
        self.assertIn("el.accountTextInput.dataset.private = String(state.accountPrivacy && hasAccountInput())", js)
        self.assertIn('el.privacyToggle.textContent = !hasInput ? "隐私保护" : state.accountPrivacy ? "显示原文" : "隐藏敏感字段"', js)
        self.assertIn('el.privacyToggle.addEventListener("click"', js)
        self.assertIn("syncAccountPrivacy();", js)
        self.assertIn(".section-actions", css)
        self.assertIn(".privacy-toggle", css)
        self.assertIn('#accountTextInput[data-private="true"]', css)
        self.assertIn("-webkit-text-security: disc", css)

    def test_account_textarea_keeps_each_account_on_one_visual_line(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        textarea = re.search(r"<textarea\s+[^>]*id=\"accountTextInput\"[^>]*>", html, re.DOTALL)
        account_textarea = re.search(r"#accountTextInput \{\n(?P<body>.*?)\n\}", css, re.DOTALL)

        self.assertIsNotNone(textarea)
        self.assertIsNotNone(account_textarea)
        self.assertIn('wrap="off"', textarea.group(0))
        self.assertIn("white-space: pre", account_textarea.group("body"))
        self.assertIn("overflow-x: auto", account_textarea.group("body"))
        self.assertIn("overflow-y: auto", account_textarea.group("body"))
        self.assertIn("overflow-wrap: normal", account_textarea.group("body"))
        self.assertIn("word-break: normal", account_textarea.group("body"))
        self.assertIn("#accountTextInput:placeholder-shown", css)
        self.assertIn("overflow-x: hidden", css_rule(css, "#accountTextInput:placeholder-shown"))
        self.assertIn("#accountTextInput:not(:placeholder-shown)", css)
        self.assertIn("overflow-x: auto", css_rule(css, "#accountTextInput:not(:placeholder-shown)"))

    def test_account_textarea_horizontal_scrollbar_is_quiet_and_precise(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        textarea = css_rule(base_css, "#accountTextInput")
        scrollbar = css_rule(base_css, "#accountTextInput::-webkit-scrollbar")
        track = css_rule(base_css, "#accountTextInput::-webkit-scrollbar-track")
        thumb = css_rule(base_css, "#accountTextInput::-webkit-scrollbar-thumb")
        thumb_hover = css_rule(base_css, "#accountTextInput::-webkit-scrollbar-thumb:hover")
        corner = css_rule(base_css, "#accountTextInput::-webkit-scrollbar-corner")

        self.assertIn("scrollbar-width: thin", textarea)
        self.assertIn("scrollbar-gutter: stable", textarea)
        self.assertIn("scrollbar-color: color-mix(in srgb, var(--line-strong) 34%, transparent) transparent", textarea)
        self.assertIn("width: 7px", scrollbar)
        self.assertIn("height: 7px", scrollbar)
        self.assertIn("background: color-mix(in srgb, var(--surface-soft) 44%, transparent)", track)
        self.assertIn("border-radius: 999px", track)
        self.assertIn("border: 2px solid transparent", thumb)
        self.assertIn("background: color-mix(in srgb, var(--line-strong) 42%, transparent)", thumb)
        self.assertIn("background-clip: padding-box", thumb)
        self.assertIn("background: color-mix(in srgb, var(--line-strong) 58%, transparent)", thumb_hover)
        self.assertIn("background: transparent", corner)

        self.assertIn("#accountTextInput::-webkit-scrollbar", mobile_block)
        self.assertIn("width: 6px", mobile_block)
        self.assertIn("height: 6px", mobile_block)
        self.assertIn("#accountTextInput::-webkit-scrollbar-thumb", mobile_block)
        self.assertIn("border: 2px solid transparent", mobile_block)

    def test_privacy_toggle_is_contextual_and_disabled_until_input_exists(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn('id="privacyToggle"', html)
        self.assertIn("disabled", html)
        self.assertIn("隐私保护", html)
        self.assertIn("const hasInput = hasAccountInput();", js)
        self.assertIn("el.privacyToggle.disabled = !hasInput", js)
        self.assertIn('el.privacyToggle.textContent = !hasInput ? "隐私保护" : state.accountPrivacy ? "显示原文" : "隐藏敏感字段"', js)
        self.assertIn('el.privacyToggle.title = !hasInput ? "输入后自动遮蔽敏感字段" : state.accountPrivacy ? "临时显示粘贴的账号原文" : "遮蔽密码、客户端 ID 与刷新令牌"', js)
        self.assertNotIn("client 和 refresh", js)

    def test_account_privacy_resets_after_input_is_cleared(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function resetAccountPrivacyWhenEmpty", js)
        self.assertIn("if (!hasAccountInput())", js)
        self.assertIn("state.accountPrivacy = true", js)
        self.assertIn("resetAccountPrivacyWhenEmpty();", js)
        self.assertLess(js.index("resetAccountPrivacyWhenEmpty();"), js.index("syncAccountPrivacy();", js.index("resetAccountPrivacyWhenEmpty();")))

    def test_interface_copy_is_refined_and_chinese_first(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")

        for noisy_copy in [
            "Accounts",
            "Status",
            "Control",
            "Terminal",
            "Inbox Preview",
            "ACCOUNTS",
            "STATUS",
            "CONTROL",
            "TERMINAL",
            "INBOX PREVIEW",
            "mail-receiver / session",
        ]:
            self.assertNotIn(noisy_copy, html)

        for refined_copy in ["账号", "状态", "控制", "日志", "收件箱", "会话事件"]:
            self.assertIn(refined_copy, html)
        js = STATIC_JS.read_text(encoding="utf-8")
        self.assertIn("收件箱列表和阅读区会在同一视图内更新。", js)
        self.assertNotIn("邮件列表和阅读区会在同一视图内更新。", js)
        self.assertIn("账号校验、IMAP 拉取与本次结果审阅", html)
        self.assertNotIn("面向账号校验、IMAP 拉取和本次结果审阅的内部生产力面板", html)

    def test_mail_review_prioritizes_readable_body_and_client_proportions(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function readableMailText", js)
        self.assertIn("readableBody", js)
        self.assertIn("body-card", js)
        self.assertNotIn("minmax(260px, 36%)", css)
        self.assertIn("clamp(390px, 42%, 520px)", css)
        self.assertNotIn("raw_message", js)

    def test_mail_reader_uses_full_body_candidates_before_preview(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function firstReadableValue", js)
        self.assertIn("function readableMailPreview", js)
        self.assertIn("function readableMailText", js)
        self.assertIn("mail.body_text", js)
        self.assertIn("mail.text_body", js)
        self.assertIn("mail.plain_text", js)
        self.assertIn("mail.body_html", js)
        self.assertIn("mail.html_body", js)
        self.assertIn("mail.html", js)
        self.assertIn(
            "const source = firstReadableValue(\n"
            "    mail.body_text,\n"
            "    mail.text_body,\n"
            "    mail.plain_text,\n"
            "    mail.body_preview,",
            js,
        )
        self.assertIn("const preview = readableMailPreview(mail);", js)
        self.assertNotIn("const preview = readableMailText(mail) || mail.body_preview || \"\";", js)

    def test_html_mail_body_sanitizing_preserves_block_spacing(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function addReadableBlockBreaks", js)
        self.assertIn('querySelectorAll("br")', js)
        self.assertIn('document.createTextNode("\\n")', js)
        self.assertIn(
            "querySelectorAll(\"p, div, section, article, header, footer, main, aside, blockquote, li, tr, h1, h2, h3, h4, h5, h6\")",
            js,
        )
        self.assertIn("addReadableBlockBreaks(documentFragment);", js)

    def test_raw_source_view_is_removed_from_frontend(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        for forbidden in [
            "查看源码",
            "隐藏源码",
            "邮件源码",
            "复制源码",
            "raw-card",
            "raw-card-header",
            "rawCloseBtn",
            "rawCopyBtn",
            "rawBtn",
            "rawPreview",
            "showRaw",
            "copyRaw",
            "raw_message",
        ]:
            self.assertNotIn(forbidden, html)
            self.assertNotIn(forbidden, js)
            self.assertNotIn(forbidden, css)

        self.assertNotIn("查看原文", js)
        self.assertNotIn("邮件原文", js)
        self.assertNotIn("复制原文", js)
        self.assertNotIn("隐藏原文", js)

    def test_status_feedback_has_busy_success_and_error_states(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="statusModule"', html)
        self.assertIn('data-status="ready"', html)
        self.assertIn("function setStatus", js)
        self.assertIn("statusModule", js)
        self.assertIn("aria-busy", js)
        self.assertIn("setStatus(text, \"busy\")", js)
        self.assertIn("setStatus(\"准备就绪\", \"ready\")", js)
        self.assertIn('setStatus("账号读取失败", "error")', js)
        self.assertIn('setStatus(`已读取 ${data.count} 个账号`, "success")', js)
        self.assertIn(".status-module.is-busy", css)
        self.assertIn(".status-module.is-success", css)
        self.assertIn(".status-module.is-error", css)
        self.assertIn("@keyframes statusPulse", css)

    def test_ultra_narrow_status_uses_compact_label_without_losing_context(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn('id="statusLine" data-full-status="准备就绪" data-compact-status="准备就绪"', html)
        self.assertIn("function compactStatusText", js)
        self.assertIn("el.statusLine.dataset.fullStatus = text", js)
        self.assertIn("el.statusLine.dataset.compactStatus", js)
        self.assertIn("el.statusLine.title = text", js)
        self.assertIn('renderInputQuality();\nsetStatus("准备就绪", "ready");', js)
        self.assertIn('el.statusModule.setAttribute("aria-label"', js)
        self.assertIn('"拉取完成"', js)
        self.assertIn('"完成 ·"', js)
        self.assertNotIn('"检测 ·"', js)
        self.assertIn('"读取 ·"', js)
        self.assertIn('"失败 ·"', js)

        self.assertIn("#statusLine", media_block)
        self.assertIn("#statusLine::after", media_block)
        self.assertIn("content: attr(data-compact-status)", media_block)
        self.assertIn("color: transparent", media_block)
        self.assertIn("text-overflow: ellipsis", media_block)

    def test_mail_fetch_auto_selects_first_message_for_reader_context(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function selectInitialMessage", js)
        self.assertIn("selectInitialMessage(visibleMessages());", js)
        self.assertIn("messageKey(results[0])", js)
        self.assertIn("mail-row-status-dot", js)
        self.assertIn(".mail-row.active::before", css)
        self.assertIn(".mail-row-status-dot", css)
        self.assertIn(".detail-meta-card", css)

    def test_design_system_uses_refined_tokens_and_responsive_density(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        for token in [
            "--radius-xs:",
            "--radius-sm:",
            "--radius-md:",
            "--radius-lg:",
            "--radius-xl:",
            "--shadow-soft:",
            "--shadow-floating:",
            "--ease-standard:",
            "--focus-ring:",
        ]:
            self.assertIn(token, css)

        self.assertIn(".panel::before", css)
        self.assertIn(".app-shell::before", css)
        self.assertIn("@media (max-width: 960px)", css)
        self.assertIn("@media (max-width: 560px)", css)

    def test_primary_actions_are_disabled_until_account_text_is_fully_valid(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        sync_action_block = js[js.index("function syncActionAvailability"):js.index("function setBusy")]

        self.assertIn("function hasAccountInput", js)
        self.assertIn("function hasValidAccountInput", js)
        self.assertIn("function syncActionAvailability", js)
        self.assertIn("state.busy", js)
        self.assertIn("const hasValidInput = hasValidAccountInput();", sync_action_block)
        self.assertIn("button.disabled = state.busy || !hasValidInput", js)
        self.assertIn('button.setAttribute("aria-busy", String(state.busy));', sync_action_block)
        self.assertIn('button.classList.toggle("is-busy", state.busy);', sync_action_block)
        self.assertIn("syncActionAvailability();", js)
        self.assertIn('setStatus("准备就绪", "ready")', js)
        self.assertIn(".button:disabled", css)
        self.assertIn(".button:disabled .icon", css)

    def test_fetch_flow_has_polished_mail_loading_state(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function renderMailLoadingState", js)
        self.assertIn("mail-loading-state", js)
        self.assertIn("mail-skeleton-row", js)
        self.assertIn("mail-skeleton-meta", js)
        self.assertIn("mail-detail-loading", js)
        self.assertIn("detail-skeleton-summary", js)
        self.assertIn("body-skeleton-card", js)
        self.assertIn('renderMailLoadingState("正在拉取邮件")', js)
        self.assertIn(".mail-loading-state", css)
        for selector in [
            ".mail-skeleton-row",
            ".mail-skeleton-meta",
            ".mail-detail-loading",
            ".detail-skeleton-summary",
            ".detail-skeleton-block",
            ".body-skeleton-card",
            ".skeleton-text-line",
        ]:
            self.assertIn(selector, css)
        self.assertNotIn('class="skeleton-row"', js)
        self.assertNotIn(".skeleton-row", css)
        self.assertIn("@keyframes skeletonShimmer", css)

    def test_fetch_loading_state_has_stage_rail_and_busy_semantics(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function setMailBusyState(isBusy)", js)
        self.assertIn('el.mailList.setAttribute("aria-busy", "true")', js)
        self.assertIn('el.mailDetail.setAttribute("aria-busy", "true")', js)
        self.assertIn('el.mailList.removeAttribute("aria-busy")', js)
        self.assertIn('el.mailDetail.removeAttribute("aria-busy")', js)
        self.assertIn("setMailBusyState(true);", js)
        self.assertIn("setMailBusyState(false);", js)
        self.assertIn('aria-busy="true"', js)
        self.assertIn("mail-loading-header", js)
        self.assertIn("mail-loading-orb", js)
        self.assertIn("mail-loading-rail", js)
        self.assertIn("mail-loading-step is-active", js)
        self.assertIn("连接账号", js)
        self.assertIn("同步邮件", js)
        self.assertIn("准备阅读区", js)
        self.assertIn("detail-loading-status", js)
        self.assertIn("summary-loading-dot", js)

        for selector in [
            ".mail-loading-header",
            ".mail-loading-orb",
            ".mail-loading-rail",
            ".mail-loading-step",
            ".mail-loading-step.is-active",
            ".detail-loading-status",
            ".summary-loading-dot",
        ]:
            self.assertIn(selector, css)
        self.assertIn("@keyframes loadingPulse", css)

    def test_fetch_failure_renders_product_error_state_in_mail_workspace(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function renderMailErrorState", js)
        self.assertIn('renderMailSummary([], { kind: "error", label: insight.title', js)
        self.assertIn("mail-error-state", js)
        self.assertIn("mail-error-panel", js)
        self.assertIn("mail-error-detail", js)
        self.assertIn("mail-error-actions", js)
        self.assertIn("mail-error-retry", js)
        self.assertIn("重新拉取", js)
        self.assertIn("button.addEventListener(\"click\", fetchMail)", js)
        self.assertIn("OAuth 授权失败", js)
        self.assertIn("查看技术详情", js)
        self.assertIn("renderMailErrorState(error.message);", js)
        self.assertIn(".mail-result-summary[data-state=\"error\"]", css)
        self.assertIn(".summary-metric.is-error", css)
        self.assertIn(".mail-error-state", css)
        self.assertIn(".mail-error-panel", css)
        self.assertIn(".mail-error-detail", css)
        self.assertIn(".mail-error-actions", css)
        self.assertIn(".mail-error-retry", css)

    def test_fetch_failure_prioritizes_recovery_summary_over_raw_oauth_detail(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function failureInsight", js)
        self.assertIn("function failureLogMessage", js)
        self.assertIn("function latestFailureMessage", js)
        self.assertIn("OAuth 授权失败", js)
        self.assertIn("刷新令牌不可用于当前租户", js)
        self.assertIn("检查 client ID、租户与 refresh token 是否来自同一账号或租户", js)
        self.assertIn("查看技术详情", js)
        self.assertIn("mail-error-technical", js)
        self.assertIn("mail-error-next-step", js)
        self.assertIn("mail-error-copy", js)
        self.assertIn("button.addEventListener(\"click\", retryFailedAccounts)", js)
        self.assertIn("button.addEventListener(\"click\", copyFailureSummary)", js)
        self.assertIn("renderMailErrorState(latestFailureMessage());", js)
        self.assertNotIn("`${row.email}: ${row.error}", js)

    def test_failure_accessibility_uses_short_labels_and_controls_log_drawer(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('aria-controls="runLogPanel"', html)
        self.assertIn('id="runLogPanel"', html)
        self.assertIn("failureAccessibilityLabel(status)", js)
        self.assertIn('selectButton.setAttribute("aria-label", `${account.email}，${isSelected ? "当前选中，" : ""}${failureAccessibilityLabel(status)}`);', js)
        self.assertNotIn('status.error ? `，${status.error}` : ""', js)
        self.assertIn(".copy-account-button", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("cursor: copy", css)

    def test_fetch_failure_uses_compact_list_error_and_detailed_reader_error(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("mail-error-compact", js)
        self.assertIn("mail-error-compact-card", js)
        self.assertIn("查看详情面板或运行记录", js)
        self.assertIn("mail-error-panel", js)
        self.assertLess(js.index("mail-error-compact"), js.index("mail-error-panel"))

        for selector in [
            ".mail-error-state.mail-error-compact",
            ".mail-error-compact-card",
            ".mail-error-compact-card .mail-empty-icon",
            ".mail-error-compact .mail-error-detail",
            ".mail-error-compact .mail-error-actions",
        ]:
            self.assertIn(selector, css)

        self.assertIn("align-content: start", css)
        self.assertIn("text-align: left", css)
        self.assertIn("grid-template-columns: 32px minmax(0, 1fr)", css)

    def test_fetch_failure_has_recoverable_diagnostics_and_log_focus_action(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function focusRunLog()", js)
        self.assertIn("mail-error-diagnostics", js)
        self.assertIn("mail-error-diagnostic-item", js)
        self.assertIn("mail-error-code", js)
        self.assertIn("mail-error-log-link", js)
        self.assertIn("恢复建议", js)
        self.assertIn("保留运行记录", js)
        self.assertIn("重新授权或调整账号后重试", js)
        self.assertIn("查看运行记录", js)
        self.assertIn('button.addEventListener("click", focusRunLog)', js)

        for selector in [
            ".mail-error-diagnostics",
            ".mail-error-diagnostic-item",
            ".mail-error-code",
            ".mail-error-log-link",
            ".mail-error-retry:focus-visible",
            ".mail-error-log-link:focus-visible",
        ]:
            self.assertIn(selector, css)
        self.assertIn('font-family: "Cascadia Mono"', css)

    def test_fetch_failure_diagnostics_read_as_quiet_recovery_panel_not_alarm_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn(
            'border-color: color-mix(in srgb, var(--danger) 16%, var(--line-soft));',
            css,
        )
        self.assertIn(
            'background: linear-gradient(180deg, color-mix(in srgb, var(--danger-soft) 8%, var(--surface-soft)), var(--surface-raised));',
            css,
        )
        self.assertIn(
            'background: linear-gradient(180deg, color-mix(in srgb, var(--danger-soft) 10%, var(--surface-soft)), transparent 58%);',
            css,
        )
        self.assertIn(
            'background: color-mix(in srgb, var(--danger-soft) 14%, var(--surface-raised));',
            css,
        )
        self.assertIn(
            'background: color-mix(in srgb, var(--danger-soft) 16%, var(--surface-raised));',
            css,
        )
        self.assertIn(
            'background: color-mix(in srgb, var(--danger-soft) 12%, var(--surface-raised));',
            css,
        )
        self.assertIn(
            'color: color-mix(in srgb, var(--danger) 72%, var(--text-strong));',
            css,
        )
        self.assertIn(
            'background: color-mix(in srgb, var(--danger-soft) 34%, var(--surface-raised));',
            css,
        )
        self.assertNotIn("radial-gradient(circle at 94% 14%, var(--danger-soft)", css)
        self.assertNotIn("radial-gradient(circle at 50% 0%, var(--danger-soft)", css)
        self.assertNotIn("radial-gradient(circle at 50% 36%, var(--danger-soft)", css)

    def test_fetch_failure_error_code_reads_like_quiet_log_excerpt(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (max-width: 360px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-error-detail .mail-error-code", css)
        self.assertIn(
            "color: color-mix(in srgb, var(--danger) 54%, var(--muted)) !important;",
            css,
        )
        self.assertIn(
            "border-left: 2px solid color-mix(in srgb, var(--danger) 34%, transparent);",
            css,
        )
        self.assertIn(
            "color: color-mix(in srgb, var(--danger) 58%, var(--text-strong)) !important;",
            css,
        )
        self.assertIn("font-size: 11.5px !important", css)
        self.assertIn("font-weight: 650", css)
        self.assertIn("line-height: 1.46", css)
        self.assertIn("letter-spacing: -0.025em", css)
        self.assertIn(".mail-error-detail .mail-error-code", media_block)
        self.assertIn("font-size: 11px !important", media_block)
        self.assertIn("line-height: 1.42", media_block)
        self.assertNotIn("box-shadow: 0 14px 32px rgba(251, 113, 133", css)

    def test_fetch_failure_actions_use_quiet_tool_buttons_not_alert_buttons(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn(".mail-error-retry::before", css)
        self.assertIn(
            "border-color: color-mix(in srgb, var(--danger) 16%, var(--line-soft));",
            css,
        )
        self.assertIn(
            "background: linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 96%, transparent), color-mix(in srgb, var(--surface-soft) 88%, transparent));",
            css,
        )
        self.assertIn(
            "box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 24%, transparent);",
            css,
        )
        self.assertIn(
            "background: color-mix(in srgb, var(--danger) 42%, transparent);",
            css,
        )
        self.assertIn(
            "border-color: color-mix(in srgb, var(--line-strong) 64%, var(--danger-soft));",
            css,
        )
        self.assertIn(
            "box-shadow: 0 8px 18px rgba(15, 23, 42, 0.055);",
            css,
        )
        self.assertIn(
            "border-color: color-mix(in srgb, var(--line-strong) 72%, var(--surface-soft));",
            css,
        )
        self.assertNotIn("linear-gradient(180deg, var(--surface-raised), color-mix(in srgb, var(--danger-soft) 36%", css)
        self.assertNotIn("box-shadow: 0 10px 24px rgba(251, 113, 133", css)
        self.assertNotIn("border-color: rgba(251, 113, 133, 0.42)", css)

    def test_fetch_failure_copy_is_direction_agnostic_for_responsive_layouts(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("查看详情面板或运行记录", js)
        self.assertIn("失败上下文已写入事件流", js)
        self.assertIn("查看运行记录", js)
        self.assertNotIn("查看右侧详情或运行记录", js)
        self.assertNotIn("左侧事件流", js)
        self.assertNotIn("定位运行记录", js)

    def test_disabled_and_busy_buttons_have_distinct_visual_states(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('.button:disabled:not([aria-busy="true"])', css)
        self.assertIn('.button.primary:disabled:not([aria-busy="true"])', css)
        self.assertIn('.button[aria-busy="true"]', css)

    def test_primary_fetch_button_reads_as_quiet_command_surface(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        primary = css_rule(base_css, ".button.primary")
        primary_after = css_rule(base_css, ".button.primary::after")
        primary_hover = css_rule(base_css, ".button.primary:hover:not(:disabled)")
        primary_active = css_rule(base_css, ".button.primary:active:not(:disabled)")
        primary_disabled = css_rule(base_css, '.button.primary:disabled:not([aria-busy="true"])')
        primary_busy = css_rule(base_css, ".button.primary.is-busy")
        busy_spinner = css_rule(base_css, ".button.primary.is-busy .button-spinner")
        operation_primary = css_rule(base_css, ".operation-panel .button.primary")

        self.assertIn('id="fetchBtn" type="button" class="button primary"', html)
        self.assertIn('class="button-spinner" aria-hidden="true"', html)
        self.assertIn('button.classList.toggle("is-busy", busy);', js)

        self.assertIn("overflow: hidden", primary)
        self.assertIn("isolation: isolate", primary)
        self.assertIn("border-color: color-mix(in srgb, var(--accent) 52%, var(--accent-strong))", primary)
        self.assertIn("background: var(--accent-gradient)", primary)
        self.assertIn("box-shadow: 0 12px 28px rgba(8, 120, 216, 0.24)", primary)
        self.assertNotIn("0 10px 20px rgba(15, 23, 42, 0.18)", primary)

        self.assertIn('content: ""', primary_after)
        self.assertIn("inset: 1px", primary_after)
        self.assertIn("border-radius: inherit", primary_after)
        self.assertIn("pointer-events: none", primary_after)
        self.assertIn("background: linear-gradient(180deg, rgba(255, 255, 255, 0.11), transparent 48%)", primary_after)

        self.assertIn("transform: translateY(-1px)", primary_hover)
        self.assertIn("box-shadow: 0 14px 30px rgba(8, 120, 216, 0.28)", primary_hover)
        self.assertNotIn("0 12px 24px rgba(15, 23, 42, 0.22)", primary_hover)
        self.assertIn("transform: translateY(0)", primary_active)
        self.assertIn("box-shadow: 0 7px 16px rgba(8, 120, 216, 0.20)", primary_active)

        self.assertIn("filter: saturate(0.86)", primary_disabled)
        self.assertIn("color: color-mix(in srgb, var(--muted) 82%, transparent)", primary_disabled)
        self.assertIn("box-shadow: none", primary_disabled)

        self.assertIn("cursor: progress", primary_busy)
        self.assertIn("transform: none", primary_busy)
        self.assertIn("box-shadow: 0 8px 18px rgba(8, 120, 216, 0.18)", primary_busy)
        self.assertIn("background: var(--accent-gradient)", primary_busy)
        self.assertIn("opacity: 0.88", busy_spinner)
        self.assertIn("border-color: color-mix(in srgb, currentColor 62%, transparent)", busy_spinner)
        self.assertIn("border-right-color: transparent", busy_spinner)

        self.assertIn("min-height: 48px", operation_primary)
        self.assertIn("font-size: 14.5px", operation_primary)
        self.assertIn("box-shadow: 0 16px 32px rgba(8, 120, 216, 0.28)", operation_primary)

    def test_account_input_has_live_quality_feedback_without_exposing_secrets(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="inputQuality"', html)
        self.assertIn("input-quality", html)
        self.assertIn('aria-describedby="inputQuality"', html)
        self.assertIn('title="每行一个账号：邮箱----密码----客户端 ID----刷新令牌；粘贴后自动遮蔽敏感字段"', html)
        self.assertIn('placeholder="邮箱----密码----客户端 ID----刷新令牌"', html)
        self.assertNotIn(
            'placeholder="每行一个账号：邮箱----密码----客户端 ID----刷新令牌；粘贴后自动遮蔽敏感字段"',
            html,
        )
        self.assertIn("邮箱----密码----客户端 ID----刷新令牌", html)
        self.assertNotIn("account-format-guide", html)
        self.assertNotIn('aria-label="账号格式"', html)
        self.assertNotIn("format-label", html)
        self.assertNotIn("format-step", html)
        self.assertNotIn("format-token", html)
        self.assertNotIn("format-separator", html)
        self.assertNotIn('placeholder="邮箱----密码----client_id----refresh_token"', html)
        self.assertIn("function inspectAccountText", js)
        self.assertIn("function renderInputQuality", js)
        self.assertIn("validLines", js)
        self.assertIn("invalidLines", js)
        self.assertIn("inputQuality", js)
        self.assertNotIn("password", html.lower())
        self.assertNotIn(".account-format-guide", css)
        self.assertNotIn(".format-label", css)
        self.assertNotIn(".format-step", css)
        self.assertNotIn(".format-token", css)
        self.assertNotIn(".format-separator", css)
        self.assertNotIn("break-inside: avoid", css)
        self.assertIn(".input-quality", css)
        self.assertIn(".quality-meter", css)
        self.assertIn(".quality-chip.is-good", css)
        self.assertIn(".quality-chip.is-warn", css)

    def test_account_count_reflects_unparsed_input_lines_before_parse(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn("function renderInputQuality", js)
        self.assertIn("if (!state.accounts.length && el.accountCount)", js)
        self.assertIn('report.totalLines ? `${report.totalLines} 行待解析` : "0 个账号"', js)
        self.assertIn("el.accountCount.textContent = `${accounts.length} 个账号`", js)
        self.assertLess(
            js.index("renderInputQuality();", js.index('el.accountTextInput.addEventListener("input"')),
            js.index("syncActionAvailability();", js.index('el.accountTextInput.addEventListener("input"')),
        )

    def test_mobile_account_format_lives_inside_textarea_placeholder(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn("邮箱----密码----客户端 ID----刷新令牌", html)
        self.assertNotIn("account-format-guide", html)
        self.assertNotIn(".account-format-guide", media_block)
        self.assertNotIn(".format-label", media_block)
        self.assertNotIn(".format-separator", media_block)
        self.assertNotIn(".format-step", media_block)
        self.assertIn(".input-quality", media_block)
        self.assertIn("padding: 5px 8px", media_block)

    def test_run_log_and_mail_detail_have_more_professional_information_hierarchy(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("activity-event-meta", js)
        self.assertIn("activity-event-message", js)
        self.assertIn("detail-summary-bar", js)
        self.assertIn("detail-summary-item", js)
        self.assertIn("formatMailDate", js)
        self.assertIn(".activity-event-meta", css)
        self.assertIn(".activity-event-message", css)
        self.assertIn(".detail-summary-bar", css)
        self.assertIn(".detail-summary-item", css)

    def test_mail_detail_uses_sender_identity_card_instead_of_plain_metadata_stack(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function senderDisplayName", js)
        self.assertIn("function senderInitial", js)
        self.assertIn("const senderName = senderDisplayName(mail.sender)", js)
        self.assertIn("const senderInitialValue = senderInitial(mail.sender)", js)
        for class_name in [
            "sender-identity-card",
            "sender-avatar",
            "sender-copy",
            "sender-copy-head",
            "sender-address",
            "sender-route",
        ]:
            self.assertIn(class_name, js)
            self.assertIn(f".{class_name}", css)

        self.assertIn('aria-label="发件人身份信息"', js)
        self.assertIn("grid-template-columns: 34px minmax(0, 1fr)", css)
        sender_avatar = css_rule(css[: css.index("@media")], ".sender-avatar")
        self.assertIn("width: 34px", sender_avatar)
        self.assertIn("height: 34px", sender_avatar)
        self.assertIn("border-radius: 999px", sender_avatar)
        self.assertIn("background: color-mix(in srgb, var(--surface-soft) 62%, transparent)", sender_avatar)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 78%, transparent)", css)

    def test_mail_detail_reader_uses_quiet_identity_strip_and_measured_body_text(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        detail_card = css_rule(base_css, ".detail-meta-card")
        sender_card = css_rule(base_css, ".sender-identity-card")
        sender_avatar = css_rule(base_css, ".sender-avatar")
        sender_copy = css_rule(base_css, ".sender-copy")
        sender_head_strong = css_rule(base_css, ".sender-copy-head strong")
        sender_route = css_rule(base_css, ".sender-route.detail-grid")
        body_card = css_rule(base_css, ".body-card")
        body_title = css_rule(base_css, ".body-card-title")
        body_preview = css_rule(base_css, ".body-preview")

        self.assertIn("margin-top: 15px", detail_card)
        self.assertIn("color-mix(in srgb, var(--surface-soft) 54%, transparent)", detail_card)
        self.assertIn("color-mix(in srgb, var(--surface-raised) 52%, transparent)", detail_card)
        self.assertIn("box-shadow: none", detail_card)

        self.assertIn("grid-template-columns: 34px minmax(0, 1fr)", sender_card)
        self.assertIn("gap: 11px", sender_card)
        self.assertIn("padding: 12px 13px", sender_card)
        self.assertIn("box-shadow: none", sender_card)
        self.assertIn("width: 34px", sender_avatar)
        self.assertIn("height: 34px", sender_avatar)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-soft) 72%, transparent)", sender_avatar)
        self.assertIn("font-size: 12.5px", sender_avatar)
        self.assertIn("font-weight: 760", sender_avatar)
        self.assertIn("gap: 5px", sender_copy)
        self.assertIn("font-size: 12.75px", sender_head_strong)
        self.assertIn("font-weight: 730", sender_head_strong)
        self.assertIn("padding: 8px 0 0", sender_route)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 78%, transparent)", sender_route)

        self.assertIn("margin-top: 16px", body_card)
        self.assertIn("padding-top: 16px", body_card)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 72%, transparent)", body_card)
        self.assertIn("background: transparent", body_card)
        self.assertIn("display: inline-flex", body_title)
        self.assertIn("padding: 0 0 8px", body_title)
        self.assertIn("font-size: 11px", body_title)
        self.assertIn("letter-spacing: 0.018em", body_title)
        self.assertIn("max-width: 66ch", body_preview)
        self.assertIn("line-height: 1.76", body_preview)

    def test_mail_detail_body_reader_uses_soft_editorial_cadence(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        body_card = css_rule(base_css, ".body-card")
        body_title = css_rule(base_css, ".body-card-title")
        body_title_marker = css_rule(base_css, ".body-card-title::before")
        body_preview = css_rule(base_css, ".body-preview")

        self.assertIn("margin-top: 16px", body_card)
        self.assertIn("padding-top: 16px", body_card)
        self.assertIn("color-mix(in srgb, var(--line-soft) 72%, transparent)", body_card)
        self.assertIn("display: inline-flex", body_title)
        self.assertIn("gap: 7px", body_title)
        self.assertIn("padding: 0 0 8px", body_title)
        self.assertIn("color: var(--subtle)", body_title)
        self.assertIn("font-size: 11px", body_title)
        self.assertIn("letter-spacing: 0.018em", body_title)
        self.assertIn("width: 18px", body_title_marker)
        self.assertIn("background: color-mix(in srgb, var(--accent) 38%, var(--line-soft))", body_title_marker)
        self.assertIn("color: color-mix(in srgb, var(--text) 92%, var(--muted))", body_preview)
        self.assertIn("font-size: 13.75px", body_preview)
        self.assertIn("line-height: 1.76", body_preview)
        self.assertIn("letter-spacing: -0.002em", body_preview)

    def test_mail_detail_body_reader_has_comfortable_scroll_tail(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        detail = css_rule(base_css, ".mail-detail")
        body_card = css_rule(base_css, ".body-card")
        body_tail = css_rule(base_css, ".body-preview::after")
        mobile_detail = re.search(r"\.mail-detail \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        mobile_body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        mobile_body_tail = re.search(r"\.body-preview::after \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)

        self.assertIn("scroll-padding-bottom: clamp(28px, 4vw, 44px)", detail)
        self.assertIn("padding-bottom: clamp(22px, 2.4vw, 32px)", body_card)
        self.assertIn('content: ""', body_tail)
        self.assertIn("display: block", body_tail)
        self.assertIn("width: 30px", body_tail)
        self.assertIn("height: 1px", body_tail)
        self.assertIn("margin-top: 22px", body_tail)
        self.assertIn("opacity: 0.66", body_tail)
        self.assertIn(
            "linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 28%, var(--line-soft)), transparent)",
            body_tail,
        )

        self.assertIsNotNone(mobile_detail)
        self.assertIsNotNone(mobile_body_card)
        self.assertIsNotNone(mobile_body_tail)
        self.assertIn("padding-bottom: 32px", mobile_detail.group("body"))
        self.assertIn("scroll-padding-bottom: 38px", mobile_detail.group("body"))
        self.assertIn("padding-bottom: 28px", mobile_body_card.group("body"))
        self.assertIn("margin-top: 20px", mobile_body_tail.group("body"))
        self.assertIn("width: 18px", mobile_body_tail.group("body"))
        self.assertIn("opacity: 0.52", mobile_body_tail.group("body"))

    def test_mobile_body_preview_ends_with_quiet_end_mark_not_decorative_rule(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)
        body_tail = re.search(r"\.body-preview::after \{\n(?P<body>.*?)\n  \}", mobile_block, re.DOTALL)

        self.assertIsNotNone(body_card)
        self.assertIsNotNone(body_tail)
        self.assertIn("padding-bottom: 28px", body_card.group("body"))
        self.assertIn("width: 18px", body_tail.group("body"))
        self.assertIn("margin-top: 20px", body_tail.group("body"))
        self.assertIn("opacity: 0.52", body_tail.group("body"))
        self.assertIn(
            "background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--line-soft) 72%, var(--accent)), transparent)",
            body_tail.group("body"),
        )
        self.assertNotIn("width: 22px", body_tail.group("body"))
        self.assertNotIn("background: color-mix(in srgb, var(--accent) 28%, var(--line-soft))", body_tail.group("body"))

    def test_sender_display_name_is_primary_in_rows_and_detail_header(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function senderAddress", js)
        self.assertIn("const senderName = senderDisplayName(mail.sender);", js)
        self.assertIn("const senderAddressText = senderAddress(mail.sender);", js)
        self.assertIn('button.setAttribute("aria-label", `${mail.subject || "(无主题)"}，${senderName}，${mail.account_email || "未知账号"}，${displayDate}`)', js)
        self.assertIn('title="${escapeHtml(senderAddressText)}">${escapeHtml(senderName)}</span>', js)
        self.assertIn('class="meta detail-meta-line"', js)
        self.assertIn("<span>${escapeHtml(senderName)}</span>", js)
        self.assertIn("<span>${escapeHtml(displayDate)}</span>", js)
        self.assertNotIn('<div class="meta">${escapeHtml(mail.sender || "-")} · ${escapeHtml(displayDate)}</div>', js)
        self.assertIn(".detail-meta-line", css)
        self.assertIn(".detail-meta-line span + span::before", css)

    def test_mobile_mail_workbench_keeps_reader_comfortable_and_bounded(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn(".mail-reader-shell", css)
        self.assertIn("max-height: 340px", css)
        self.assertIn("scroll-margin-top", css)

    def test_mobile_operation_controls_stay_compact_without_breaking_mail_stack(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 720px)")
        media_end = css.index("@media (max-width: 560px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".operation-grid", media_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(106px, 0.36fr)", media_block)
        self.assertIn(".action-stack", media_block)
        action_start = media_block.index(".action-stack")
        action_end = media_block.index(".mail-workbench", action_start)
        self.assertIn("grid-template-columns: 1fr", media_block[action_start:action_end])
        self.assertIn(".mail-workbench", media_block)
        self.assertIn("grid-template-columns: 1fr", media_block)
        self.assertNotIn(".operation-grid,\n  .action-stack,\n  .mail-workbench", media_block)

    def test_mobile_limit_input_stays_legible_without_native_spinner_clipping(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        handheld_start = css.index("@media (max-width: 720px)")
        handheld_end = css.index("@media (max-width: 560px)", handheld_start)
        handheld_block = css[handheld_start:handheld_end]
        narrow_start = css.index("@media (max-width: 360px)")
        narrow_end = css.index("@media (prefers-reduced-motion: reduce)", narrow_start)
        narrow_block = css[narrow_start:narrow_end]

        self.assertIn("#limitInput", css)
        self.assertIn("font-variant-numeric: tabular-nums", css)
        self.assertIn("text-align: center", css)
        self.assertIn("appearance: textfield", css)
        self.assertIn("#limitInput::-webkit-inner-spin-button", css)
        self.assertIn("#limitInput::-webkit-outer-spin-button", css)
        self.assertIn("appearance: none", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(106px, 0.36fr)", handheld_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 104px", narrow_block)

    def test_mail_list_supports_keyboard_navigation_and_accessible_selection(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("function handleMailListKeydown", js)
        self.assertIn("function focusSelectedMail", js)
        self.assertIn('el.mailList.setAttribute("role", "listbox")', js)
        self.assertIn('button.setAttribute("role", "option")', js)
        self.assertIn('button.setAttribute("aria-selected"', js)
        self.assertIn("ArrowDown", js)
        self.assertIn("ArrowUp", js)
        self.assertIn("Home", js)
        self.assertIn("End", js)
        self.assertIn(".mail-row:focus-visible", css)

    def test_message_selection_uses_stable_cross_account_keys(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")

        logic_script = '<script src="/static/app_logic.js"></script>'
        app_script = '<script src="/static/app.js"></script>'
        self.assertIn(logic_script, html)
        self.assertIn(app_script, html)
        self.assertLess(html.index(logic_script), html.index(app_script))
        self.assertIn(
            "const { createOperationGate, createRequestFailureState, createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;",
            js,
        )
        self.assertIn("selectedMessageKey: null", js)
        self.assertIn(
            "findMessageByKey(allSessionMessages(), state.selectedMessageKey)",
            js,
        )
        self.assertIn("button.dataset.messageKey = key", js)
        self.assertNotIn("selectedEmailId", js)

    def test_mail_rows_separate_sender_and_preview_hierarchy(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('class="mail-row-sender"', js)
        self.assertIn('class="mail-row-preview"', js)
        self.assertNotIn('<div class="meta">${escapeHtml(mail.sender || "-")}</div>\n      <div class="preview">', js)
        self.assertIn(".mail-row-sender", css)
        self.assertIn(".mail-row-preview", css)
        self.assertIn("font-size: 11.5px", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn("text-overflow: ellipsis", css)

    def test_mail_rows_gain_sender_avatar_for_mature_client_scanning(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("const senderInitialValue = senderInitial(mail.sender);", js)
        self.assertIn('class="mail-row-avatar"', js)
        self.assertIn('${escapeHtml(senderInitialValue)}', js)
        self.assertIn(".mail-row-avatar", css)
        self.assertIn("grid-template-columns: 28px minmax(0, 1fr) auto", css)
        self.assertIn(".mail-row.active .mail-row-avatar", css)
        self.assertIn('[data-theme="dark"] .mail-row-avatar', css)

        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]
        self.assertIn(".mail-row-avatar", mobile_block)
        self.assertIn("width: 24px", mobile_block)
        self.assertIn("height: 24px", mobile_block)

    def test_reader_surface_has_showcase_polish_without_heavy_card_stack(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("--reader-surface-wash:", css)
        self.assertIn("--reader-prose-glow:", css)
        self.assertIn(".mail-workbench::after", css)
        self.assertIn("mix-blend-mode: soft-light", css)
        self.assertIn(".mail-reader-shell::after", css)
        self.assertIn("width: 1px", css)
        self.assertIn(".body-card::before", css)
        self.assertIn("linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 26%, transparent), transparent)", css)

    def test_mail_rows_use_quiet_scanning_hierarchy_for_metadata(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        subject = css_rule(css, ".mail-row .subject")
        time = css_rule(css, ".mail-time")
        sender = css_rule(css, ".mail-row-sender")
        account = css_rule(css, ".mail-row-account")
        row_scan_start = css.index(".mail-row-main")
        row_scan_css = css[row_scan_start: css.index(".mail-detail", row_scan_start)]
        preview_rules = re.findall(r"^\.mail-row-preview \{\n(?P<body>.*?)\n\}", row_scan_css, re.DOTALL | re.MULTILINE)
        self.assertTrue(preview_rules)
        preview = preview_rules[-1]
        selected_sender = css_rule(
            css,
            '.mail-row.active .mail-row-sender,\n.mail-row[aria-selected="true"] .mail-row-sender',
        )
        selected_account = css_rule(
            css,
            '.mail-row.active .mail-row-account,\n.mail-row[aria-selected="true"] .mail-row-account',
        )
        selected_preview_and_time = css_rule(
            css,
            '.mail-row.active .mail-row-preview,\n.mail-row[aria-selected="true"] .mail-row-preview,\n.mail-row.active .mail-time,\n.mail-row[aria-selected="true"] .mail-time',
        )

        self.assertIn("color: var(--text-strong)", subject)
        self.assertIn("font-weight: 730", subject)
        self.assertIn("color: color-mix(in srgb, var(--text) 70%, var(--muted))", sender)
        self.assertIn("font-weight: 620", sender)
        self.assertIn("font-size: 10.75px", time)
        self.assertIn("color: color-mix(in srgb, var(--subtle) 82%, transparent)", time)
        self.assertIn("font-size: 10.75px", account)
        self.assertIn("color: color-mix(in srgb, var(--subtle) 78%, transparent)", account)
        self.assertIn("font-size: 11.75px", preview)
        self.assertIn("opacity: 0.82", preview)
        self.assertIn("color: color-mix(in srgb, var(--text) 88%, var(--mail-row-selected-text))", selected_sender)
        self.assertIn("color: color-mix(in srgb, var(--mail-row-selected-text) 78%, transparent)", selected_account)
        self.assertIn("opacity: 0.86", selected_preview_and_time)

    def test_mail_rows_have_theme_aware_interaction_states(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        for token in [
            "--mail-row-active:",
            "--mail-row-active-border:",
            "--mail-row-active-shadow:",
            "--mail-row-hover-shadow:",
            "--mail-row-selected-text:",
        ]:
            self.assertIn(token, css)

        self.assertIn('[data-theme="dark"]', css)
        self.assertIn("--mail-row-active: linear-gradient(180deg, color-mix(in srgb, var(--accent-softer) 30%, var(--row-bg)), color-mix(in srgb, var(--row-bg) 92%, transparent));", css)
        self.assertIn(".mail-row:hover:not(.active)", css)
        self.assertIn("transform: translateY(-1px)", css)
        self.assertIn(".mail-row:active", css)
        self.assertIn("transform: translateY(0)", css)
        self.assertIn(".mail-row.active,\n.mail-row[aria-selected=\"true\"]", css)
        self.assertIn("background: var(--mail-row-active)", css)
        self.assertIn("border-color: var(--mail-row-active-border)", css)
        self.assertIn("box-shadow: var(--mail-row-active-shadow)", css)
        self.assertIn(".mail-row.active .mail-row-preview", css)
        self.assertIn(".mail-row[aria-selected=\"true\"] .mail-row-preview", css)
        self.assertIn("color: var(--mail-row-selected-text)", css)
        self.assertIn(".mail-row.active:hover,\n.mail-row[aria-selected=\"true\"]:hover", css)

    def test_selected_mail_row_reads_as_quiet_selection_not_glowing_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        light_tokens = re.search(
            r":root,\n\[data-theme=\"light\"\] \{\n(?P<body>.*?)\n\}",
            css,
            re.DOTALL,
        )
        dark_tokens = css_rule(css, '[data-theme="dark"]')
        selected_dot = css_rule(css, '.mail-row.active .mail-row-status-dot,\n.mail-row[aria-selected="true"] .mail-row-status-dot')

        self.assertIsNotNone(light_tokens)
        light_body = light_tokens.group("body")

        self.assertIn("color-mix(in srgb, var(--accent-softer) 22%, var(--row-bg))", light_body)
        self.assertIn("--mail-row-active-border: color-mix(in srgb, var(--accent) 16%, var(--line-soft))", light_body)
        self.assertIn("--mail-row-active-shadow: none", light_body)
        self.assertIn("--mail-row-hover-shadow: 0 6px 14px rgba(22, 34, 51, 0.045)", light_body)
        self.assertNotIn("rgba(239, 247, 255, 0.74)", light_body)
        self.assertNotIn("inset 3px 0 0 var(--accent)", light_body)
        self.assertNotIn("0 8px 18px rgba(15, 23, 42, 0.055)", light_body)

        self.assertIn("color-mix(in srgb, var(--accent-softer) 30%, var(--row-bg))", dark_tokens)
        self.assertIn("--mail-row-active-border: rgba(96, 183, 255, 0.18)", dark_tokens)
        self.assertIn("--mail-row-active-shadow: none", dark_tokens)
        self.assertIn("--mail-row-selected-text: #b9c9dd", dark_tokens)
        self.assertNotIn("rgba(13, 54, 91, 0.38)", dark_tokens)
        self.assertNotIn("rgba(14, 74, 124, 0.48)", dark_tokens)
        self.assertNotIn("0 10px 28px rgba(0, 0, 0, 0.20)", dark_tokens)

        self.assertIn("background: var(--accent)", selected_dot)
        self.assertIn("box-shadow: none", selected_dot)
        self.assertNotIn("0 0 0 2px color-mix(in srgb, var(--accent-soft) 74%, transparent)", selected_dot)
        self.assertNotIn("0 0 0 3px var(--accent-soft)", selected_dot)
        self.assertNotIn("rgba(255, 255, 255, 0.28)", selected_dot)

    def test_selected_mail_row_reads_as_quiet_reading_marker_not_lifted_card(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        selected_row = css_rule(css, '.mail-row.active,\n.mail-row[aria-selected="true"]')
        selected_rail = css_rule(css, '.mail-row.active::before,\n.mail-row[aria-selected="true"]::before')
        selected_hover = css_rule(css, '.mail-row.active:hover,\n.mail-row[aria-selected="true"]:hover')
        selected_dot = css_rule(css, '.mail-row.active .mail-row-status-dot,\n.mail-row[aria-selected="true"] .mail-row-status-dot')

        self.assertIn("border-color: var(--mail-row-active-border)", selected_row)
        self.assertIn("background: var(--mail-row-active)", selected_row)
        self.assertIn("box-shadow: var(--mail-row-active-shadow)", selected_row)
        self.assertNotIn("0 6px 14px", selected_row)
        self.assertNotIn("0 8px 18px", selected_row)

        self.assertIn("left: 0", selected_rail)
        self.assertIn("width: 2px", selected_rail)
        self.assertIn("background: color-mix(in srgb, var(--accent) 58%, transparent)", selected_rail)
        self.assertIn("opacity: 0.88", selected_rail)
        self.assertIn("transform: none", selected_hover)
        self.assertIn("box-shadow: var(--mail-row-active-shadow)", selected_hover)
        self.assertIn("box-shadow: none", selected_dot)

    def test_mail_list_rows_use_card_stack_with_reference_style_selection_rail(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn(".mail-list {\n  display: grid;\n  align-content: start;\n  gap: 8px;", css)
        self.assertIn(".mail-row {\n  position: relative;", css)
        self.assertIn("min-height: 82px", css)
        self.assertIn("padding: 11px 12px 11px 14px", css)
        self.assertIn("border: 1px solid var(--line-soft)", css)
        self.assertIn("background: var(--row-bg)", css)
        self.assertIn("left: -1px", css)
        self.assertIn("width: 3px", css)
        self.assertIn("border-radius: 999px", css)
        self.assertIn(".mail-list-empty-state", css)
        self.assertIn(".mail-empty-rows", css)
        self.assertIn("width: min(100%, 318px)", css)
        self.assertIn(".mail-empty-row {\n  position: relative;", css)

    def test_operation_controls_explain_scope_and_clamp_limit(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="operationNote"', html)
        self.assertIn("operation-note", html)
        self.assertIn("不写入本地库", html)
        self.assertIn("function normalizeLimit", js)
        self.assertIn("normalizeLimit(el.limitInput.value)", js)
        self.assertIn("limitInput.addEventListener", js)
        self.assertIn(".operation-note", css)

    def test_operation_console_can_toggle_full_rfc822_downloads(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="rawFetchToggle"', html)
        self.assertIn('title="下载每封完整 RFC822 原文，可能明显变慢。"', html)
        self.assertIn('aria-label="下载每封完整 RFC822 原文，可能明显变慢。"', html)
        self.assertIn("完整原文", html)
        self.assertIn("RFC822 · 较慢", html)
        self.assertIn("完整 RFC822 原文", html)
        self.assertIn("rawFetchToggle: document.getElementById(\"rawFetchToggle\")", js)
        self.assertIn("if (el.rawFetchToggle?.checked)", js)
        self.assertIn("payload.include_raw = true", js)
        self.assertIn("rawFetchToggle.addEventListener", js)
        self.assertIn(".raw-fetch-toggle", css)
        self.assertIn(".raw-fetch-toggle input", css)

    def test_operation_console_uses_minimal_modern_visual_treatment(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        panel = css_rule(base_css, ".operation-panel")
        panel_before = css_rule(base_css, ".operation-panel::before")
        input_rule = css_rule(base_css, ".operation-panel input:not([type=\"checkbox\"])")
        segmented_group = css_rule(base_css, ".scope-toggle-group")
        segmented_active = css_rule(base_css, ".scope-toggle.is-active")
        raw_toggle = css_rule(base_css, ".raw-fetch-toggle")
        note = css_rule(base_css, ".operation-note")
        primary_button = css_rule(base_css, ".button.primary")

        self.assertIn("padding: 14px", panel)
        self.assertIn("gap: 12px", panel)
        self.assertIn("border: 1px solid rgba(226, 232, 240, 0.72)", panel)
        self.assertIn("background: #ffffff", panel)
        self.assertIn("box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03)", panel)
        self.assertNotIn("linear-gradient", panel)
        self.assertIn("display: none", panel_before)

        self.assertIn("min-height: 32px", input_rule)
        self.assertIn("border-radius: 8px", input_rule)
        self.assertIn("font-size: 12.25px", input_rule)
        self.assertIn("border-color: color-mix(in srgb, var(--line-soft) 68%, transparent)", input_rule)

        self.assertIn("border-radius: 999px", segmented_group)
        self.assertIn("padding: 2px", segmented_group)
        self.assertIn("gap: 2px", segmented_group)
        self.assertIn("background: color-mix(in srgb, var(--surface-soft) 72%, #ffffff)", segmented_group)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 92%, transparent)", segmented_active)
        self.assertIn("color: #111827", segmented_active)
        self.assertNotIn("var(--accent", segmented_active)

        self.assertIn("border: 0", raw_toggle)
        self.assertIn("min-height: 19px", raw_toggle)
        self.assertIn("padding: 0 1px", raw_toggle)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 64%, transparent)", note)
        self.assertIn("font-size: 10.25px", note)

        self.assertIn("border-color: color-mix(in srgb, var(--accent) 52%, var(--accent-strong))", primary_button)
        self.assertIn("background: var(--accent-gradient)", primary_button)
        self.assertIn("box-shadow: 0 12px 28px rgba(8, 120, 216, 0.24)", primary_button)

    def test_operation_console_reads_as_quiet_control_toolbar(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        grid = css_rule(base_css, ".operation-grid")
        segmented_group = css_rule(base_css, ".scope-toggle-group")
        segmented_toggle = css_rule(base_css, ".scope-toggle")
        segmented_active = css_rule(base_css, ".scope-toggle.is-active")
        raw_toggle = css_rule(base_css, ".raw-fetch-toggle")
        note = css_rule(base_css, ".operation-note")
        panel_button = css_rule(base_css, ".operation-panel .button")
        panel_primary = css_rule(base_css, ".operation-panel .button.primary")

        self.assertIn("gap: 7px", grid)
        self.assertIn("padding: 2px", segmented_group)
        self.assertIn("border: 1px solid rgba(226, 232, 240, 0.72)", segmented_group)
        self.assertIn("background: color-mix(in srgb, var(--surface-soft) 72%, #ffffff)", segmented_group)
        self.assertIn("box-shadow: none", segmented_group)
        self.assertIn("min-height: 30px", segmented_toggle)
        self.assertIn("font-weight: 620", segmented_toggle)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 92%, transparent)", segmented_active)
        self.assertIn("box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72)", segmented_active)
        self.assertIn("min-height: 19px", raw_toggle)
        self.assertIn("padding: 0 1px", raw_toggle)
        self.assertIn("padding: 6px 0 0", note)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 64%, transparent)", note)
        self.assertIn("font-size: 10.25px", note)
        self.assertIn("min-height: 38px", panel_button)
        self.assertIn("box-shadow: 0 16px 32px rgba(8, 120, 216, 0.28)", panel_primary)

    def test_operation_secondary_options_read_as_quiet_footer_rail(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        raw_toggle = css_rule(base_css, ".raw-fetch-toggle")
        checkbox = css_rule(base_css, ".raw-fetch-toggle input")
        checked = css_rule(base_css, '.raw-fetch-toggle input[type="checkbox"]:checked')
        focus = css_rule(base_css, ".raw-fetch-toggle input:focus-visible")
        raw_text = css_rule(base_css, ".raw-fetch-toggle span")
        raw_strong = css_rule(base_css, ".raw-fetch-toggle strong")
        raw_small = css_rule(base_css, ".raw-fetch-toggle small")
        note = css_rule(base_css, ".operation-note")
        note_label = css_rule(base_css, ".operation-note > span")
        note_marker = css_rule(base_css, ".operation-note > span::before")
        note_value = css_rule(base_css, ".operation-note strong")
        dark_checked = css_rule(base_css, '[data-theme="dark"] .raw-fetch-toggle input[type="checkbox"]:checked')

        self.assertIn("gap: 6px", raw_toggle)
        self.assertIn("min-height: 19px", raw_toggle)
        self.assertIn("padding: 0 1px", raw_toggle)
        self.assertIn("color: color-mix(in srgb, var(--muted) 82%, transparent)", raw_toggle)
        self.assertNotIn("min-height: 20px", raw_toggle)

        self.assertIn("width: 12px", checkbox)
        self.assertIn("height: 12px", checkbox)
        self.assertIn("min-height: 12px", checkbox)
        self.assertIn("border-radius: 3px", checkbox)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-strong) 58%, transparent)", checkbox)
        self.assertIn("background: transparent", checkbox)
        self.assertIn("box-shadow: none", checkbox)
        self.assertNotIn("width: 14px", checkbox)

        self.assertIn("background-color: color-mix(in srgb, var(--text-strong) 82%, transparent)", checked)
        self.assertIn("background-size: 10px 10px", checked)
        self.assertIn("box-shadow: none", checked)
        self.assertNotIn("inset 0 0 0 7px", checked)
        self.assertIn("box-shadow: 0 0 0 2px color-mix(in srgb, var(--text) 7%, transparent)", focus)

        self.assertIn("gap: 5px", raw_text)
        self.assertIn("font-size: 11.25px", raw_strong)
        self.assertIn("font-weight: 600", raw_strong)
        self.assertIn("color: color-mix(in srgb, var(--text) 54%, var(--muted))", raw_strong)
        self.assertIn("font-size: 10.25px", raw_small)
        self.assertIn("color: color-mix(in srgb, var(--muted) 72%, transparent)", raw_small)

        self.assertIn("padding: 6px 0 0", note)
        self.assertIn("border-top: 1px solid color-mix(in srgb, var(--line-soft) 64%, transparent)", note)
        self.assertIn("color: color-mix(in srgb, var(--muted) 78%, transparent)", note)
        self.assertIn("font-size: 10.25px", note)
        self.assertIn("font-size: 10.25px", note_label)
        self.assertIn("font-weight: 600", note_label)
        self.assertIn("width: 3px", note_marker)
        self.assertIn("height: 3px", note_marker)
        self.assertIn("background: var(--subtle)", note_marker)
        self.assertIn("color: color-mix(in srgb, var(--text) 54%, var(--muted))", note_value)
        self.assertIn("font-weight: 500", note_value)

        self.assertIn("background-color: color-mix(in srgb, var(--text-strong) 84%, transparent)", dark_checked)
        self.assertIn("box-shadow: none", dark_checked)

    def test_operation_parameters_read_as_compact_instrument_strip(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        handheld_start = css.index("@media (max-width: 720px)")
        handheld_end = css.index("@media (max-width: 560px)", handheld_start)
        handheld_block = css[handheld_start:handheld_end]
        short_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        short_end = css.index("@media (max-width: 980px)", short_start)
        short_desktop_block = css[short_start:short_end]
        narrow_start = css.index("@media (max-width: 360px)")
        narrow_end = css.index("@media (prefers-reduced-motion: reduce)", narrow_start)
        narrow_block = css[narrow_start:narrow_end]

        grid = css_rule(base_css, ".operation-grid")
        field = css_rule(base_css, ".operation-panel .field-label")
        field_label = css_rule(base_css, ".operation-panel .field-label > span")
        input_rule = css_rule(base_css, ".operation-panel input:not([type=\"checkbox\"])")
        input_focus = css_rule(base_css, ".operation-panel input:not([type=\"checkbox\"]):focus")
        limit_input = css_rule(base_css, "#limitInput")

        self.assertIn("align-items: center", grid)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(106px, 0.36fr)", grid)
        self.assertIn("gap: 7px", grid)
        self.assertNotIn("minmax(160px, 1fr) 118px", grid)

        self.assertIn("gap: 6px", field)
        self.assertIn("padding: 2px", field)
        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-soft) 72%, transparent)", field)
        self.assertIn("border-radius: var(--radius-sm)", field)
        self.assertIn("background: linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 78%, transparent), color-mix(in srgb, var(--surface-soft) 36%, transparent))", field)
        self.assertIn("box-shadow: none", field)
        self.assertNotIn("gap: 10px", field)

        self.assertIn("padding-left: 6px", field_label)
        self.assertIn("font-size: 10.75px", field_label)
        self.assertIn("letter-spacing: 0.01em", field_label)
        self.assertIn("color: color-mix(in srgb, var(--muted) 86%, transparent)", field_label)
        self.assertNotIn("color: #8a94a6", field_label)

        self.assertIn("min-height: 32px", input_rule)
        self.assertIn("padding: 6px 9px", input_rule)
        self.assertIn("border-radius: 8px", input_rule)
        self.assertIn("border-color: color-mix(in srgb, var(--line-soft) 68%, transparent)", input_rule)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 88%, transparent)", input_rule)
        self.assertIn("box-shadow: inset 0 1px 0 color-mix(in srgb, #ffffff 56%, transparent)", input_rule)
        self.assertNotIn("min-height: 36px", input_rule)
        self.assertIn("box-shadow: 0 0 0 2px color-mix(in srgb, var(--text) 6%, transparent)", input_focus)

        self.assertIn("max-width: 44px", limit_input)
        self.assertIn("justify-self: end", limit_input)
        self.assertIn("padding-inline: 6px", limit_input)

        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(106px, 0.36fr)", handheld_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 104px", short_desktop_block)
        self.assertIn("min-height: 32px", short_desktop_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 104px", narrow_block)

    def test_raw_fetch_checkbox_is_not_styled_as_text_input(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]

        self.assertNotIn(".operation-panel input {\n", base_css)
        text_input_rule = css_rule(base_css, ".operation-panel input:not([type=\"checkbox\"])")
        checkbox_rule = css_rule(base_css, ".raw-fetch-toggle input")
        raw_text_rule = css_rule(base_css, ".raw-fetch-toggle span")
        raw_small_rule = css_rule(base_css, ".raw-fetch-toggle small")

        self.assertIn("min-height: 32px", text_input_rule)
        self.assertIn("border-radius: 8px", text_input_rule)
        self.assertIn("font-size: 12.25px", text_input_rule)
        self.assertIn("width: 12px", checkbox_rule)
        self.assertIn("height: 12px", checkbox_rule)
        self.assertIn("min-height: 12px", checkbox_rule)
        self.assertIn("box-shadow: none", checkbox_rule)
        self.assertIn("justify-self: start", checkbox_rule)
        self.assertIn("display: flex", raw_text_rule)
        self.assertIn("align-items: baseline", raw_text_rule)
        self.assertIn("white-space: nowrap", raw_text_rule)
        self.assertIn("text-overflow: ellipsis", raw_small_rule)

    def test_operation_scope_copy_is_product_like_not_debug_copy(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('title="每行一个账号：邮箱----密码----客户端 ID----刷新令牌；粘贴后自动遮蔽敏感字段"', html)
        self.assertIn('placeholder="邮箱----密码----客户端 ID----刷新令牌"', html)
        self.assertNotIn(
            'placeholder="每行一个账号：邮箱----密码----客户端 ID----刷新令牌；粘贴后自动遮蔽敏感字段"',
            html,
        )
        self.assertIn("邮箱----密码----客户端 ID----刷新令牌", html)
        self.assertNotIn("format-separator", html)
        self.assertNotIn('placeholder="email----密码----client_id----refresh_token"', html)
        self.assertNotIn('placeholder="邮箱----密码----client_id----refresh_token"', html)
        self.assertIn("会话模式", html)
        self.assertIn("即时预览，不写入本地库；刷新页面即清空本次结果。", html)
        self.assertNotIn("页面内调试", html)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", css)
        self.assertIn(".operation-note > span::before", css)
        self.assertNotIn(".operation-note span::before", css)
        self.assertIn("background: var(--accent-strong)", css)
        self.assertIn("text-align: left", css)

    def test_operation_note_has_compact_scope_copy_for_constrained_viewports(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        short_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        short_end = css.index("@media (max-width: 980px)", short_start)
        short_block = css[short_start:short_end]
        narrow_start = css.index("@media (max-width: 360px)")
        narrow_end = css.index("@media (prefers-reduced-motion: reduce)", narrow_start)
        narrow_block = css[narrow_start:narrow_end]

        self.assertIn("operation-note-full", html)
        self.assertIn("operation-note-compact", html)
        self.assertIn("即时预览，不写入本地库；刷新页面即清空本次结果。", html)
        self.assertIn('<span class="operation-note-compact" aria-hidden="true">预览 · 不入库 · 刷新清空</span>', html)
        self.assertNotIn('<span class="operation-note-compact" aria-hidden="true">即时预览 · 不入库 · 刷新清空</span>', html)
        self.assertIn(".operation-note > span", css)
        self.assertIn(".operation-note > span::before", css)
        self.assertIn(".operation-note-compact", css)
        self.assertIn("el.operationNote.title = description.full", js)
        self.assertIn('el.operationNote.setAttribute("aria-label", `${description.label}：${description.full}`)', js)
        self.assertIn("display: none", css_rule(base_css, ".operation-note-full"))
        self.assertIn("display: inline", css_rule(base_css, ".operation-note-compact"))
        self.assertIn(".operation-note-full", short_block)
        self.assertIn(".operation-note-compact", short_block)
        self.assertIn("display: none", short_block)
        self.assertIn("display: inline", short_block)
        self.assertIn(".operation-note-full", narrow_block)
        self.assertIn(".operation-note-compact", narrow_block)
        self.assertIn("white-space: nowrap", narrow_block)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", narrow_block)
        self.assertNotIn("min-height: 44px", narrow_block)

    def test_mail_reader_has_compact_toolbar_for_reading_context(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("reader-toolbar", js)
        self.assertIn("reader-stat", js)
        self.assertIn("bodyLength", js)
        self.assertIn("可读正文", js)
        self.assertIn("正文已净化", js)
        self.assertIn("当前会话预览", js)
        self.assertNotIn("HTML 已净化", js)
        self.assertIn("reader-stat is-primary", js)
        self.assertIn("reader-stat is-safe", js)
        self.assertIn("reader-stat is-session", js)
        self.assertIn(".reader-toolbar", css)
        self.assertIn(".reader-stat", css)
        self.assertIn(".reader-stat::before", css)
        self.assertIn(".reader-stat.is-safe", css)
        self.assertIn(".reader-stat.is-session", css)
        self.assertIn("--reader-dot", css)

    def test_mobile_reader_metadata_uses_inline_summary_rail_to_reclaim_body_preview(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        summary_bar = re.search(r"\.detail-summary-bar \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        summary_item = re.search(r"\.detail-summary-item \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        summary_strong = re.search(r"\.detail-summary-item strong \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        first_summary_strong = re.search(
            r"\.detail-summary-item:first-child strong \{\n(?P<body>.*?)\n  \}",
            media_block,
            re.DOTALL,
        )

        self.assertIsNotNone(summary_bar)
        self.assertIsNotNone(summary_item)
        self.assertIsNotNone(summary_strong)
        self.assertIsNotNone(first_summary_strong)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(86px, auto)", summary_bar.group("body"))
        self.assertIn("align-items: start", summary_bar.group("body"))
        self.assertIn("gap: 6px 12px", summary_bar.group("body"))
        self.assertIn("padding: 7px 0 9px", summary_bar.group("body"))
        self.assertNotIn("repeat(2, minmax(0, 1fr))", summary_bar.group("body"))
        self.assertIn(".detail-summary-item:first-child", media_block)
        self.assertIn("grid-column: 1 / -1", media_block)
        self.assertIn("display: grid", summary_item.group("body"))
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", summary_item.group("body"))
        self.assertIn("align-items: baseline", summary_item.group("body"))
        self.assertIn("min-height: 16px", summary_item.group("body"))
        self.assertIn("gap: 6px", summary_item.group("body"))
        self.assertIn("font-size: 11.75px", summary_strong.group("body"))
        self.assertIn("line-height: 1.22", summary_strong.group("body"))
        self.assertIn("white-space: nowrap", summary_strong.group("body"))
        self.assertIn("text-overflow: ellipsis", first_summary_strong.group("body"))
        self.assertIn("white-space: nowrap", first_summary_strong.group("body"))
        self.assertNotIn("white-space: normal", first_summary_strong.group("body"))
        self.assertIn(".reader-stat", media_block)
        self.assertIn("display: flex", media_block)
        self.assertIn("flex-wrap: wrap", media_block)
        self.assertIn("flex: 0 0 auto", media_block)

    def test_mobile_detail_masthead_compacts_like_mail_reader_not_card_header(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        header = re.search(r"\.detail-header \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        title = re.search(r"\.detail-header h2 \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        meta = re.search(r"\.detail-header \.meta \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        actions = re.search(r"\.detail-actions \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        action_pill = re.search(r"\.detail-actions \.pill \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        summary_bar = re.search(r"\.detail-summary-bar \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        toolbar = re.search(r"\.reader-toolbar \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(header)
        self.assertIsNotNone(title)
        self.assertIsNotNone(meta)
        self.assertIsNotNone(actions)
        self.assertIsNotNone(action_pill)
        self.assertIsNotNone(summary_bar)
        self.assertIsNotNone(toolbar)

        self.assertIn("gap: 4px", header.group("body"))
        self.assertIn("padding-bottom: 10px", header.group("body"))
        self.assertIn("font-size: clamp(20px, 5.45vw, 23px)", title.group("body"))
        self.assertIn("line-height: 1.16", title.group("body"))
        self.assertIn("letter-spacing: -0.044em", title.group("body"))
        self.assertIn("max-width: 100%", title.group("body"))
        self.assertIn("margin-top: 4px", meta.group("body"))
        self.assertIn("line-height: 1.34", meta.group("body"))
        self.assertIn("margin-top: 2px", actions.group("body"))
        self.assertIn("min-height: 22px", action_pill.group("body"))
        self.assertIn("padding: 1px 8px", action_pill.group("body"))
        self.assertIn("font-size: 10.75px", action_pill.group("body"))
        self.assertIn("margin-top: 8px", summary_bar.group("body"))
        self.assertIn("padding: 7px 0 9px", summary_bar.group("body"))
        self.assertIn("margin-top: 8px", toolbar.group("body"))
        self.assertNotIn("font-size: clamp(21px, 2.05vw, 26px)", title.group("body"))
        self.assertNotIn("padding-bottom: 16px", header.group("body"))

    def test_mobile_sender_identity_keeps_long_address_polished(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".sender-address", media_block)
        self.assertIn("overflow: hidden", media_block)
        self.assertIn("text-overflow: ellipsis", media_block)
        self.assertIn("white-space: nowrap", media_block)

    def test_mobile_reader_identity_strip_uses_soft_surface_and_hairline_dividers(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        detail_card = re.search(r"\.detail-meta-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        route = re.search(r"\.sender-route\.detail-grid \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(detail_card)
        self.assertIsNotNone(route)
        self.assertIsNotNone(body_card)
        self.assertIn(
            "background: color-mix(in srgb, var(--surface-soft) 26%, transparent)",
            detail_card.group("body"),
        )
        self.assertIn("margin-top: 8px", detail_card.group("body"))
        self.assertNotIn("linear-gradient", detail_card.group("body"))
        self.assertIn(
            "border-top: 1px solid color-mix(in srgb, var(--line-soft) 50%, transparent)",
            route.group("body"),
        )
        self.assertIn(
            "border-top: 1px solid color-mix(in srgb, var(--line-soft) 52%, transparent)",
            body_card.group("body"),
        )

    def test_mobile_sender_identity_flows_into_body_preview_without_card_stack(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        detail_card = re.search(r"\.detail-meta-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        sender_card = re.search(r"\.sender-identity-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        body_title = re.search(r"\.body-card-title \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        body_title_rule = re.search(r"\.body-card-title::before \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(detail_card)
        self.assertIsNotNone(sender_card)
        self.assertIsNotNone(body_card)
        self.assertIsNotNone(body_title)
        self.assertIsNotNone(body_title_rule)

        self.assertIn("margin-top: 8px", detail_card.group("body"))
        self.assertIn("border-radius: 14px", detail_card.group("body"))
        self.assertIn(
            "background: color-mix(in srgb, var(--surface-soft) 26%, transparent)",
            detail_card.group("body"),
        )
        self.assertIn("gap: 8px", sender_card.group("body"))
        self.assertIn("padding: 8px 9px 9px", sender_card.group("body"))
        self.assertIn("margin-top: 10px", body_card.group("body"))
        self.assertIn("padding-top: 10px", body_card.group("body"))
        self.assertIn(
            "border-top: 1px solid color-mix(in srgb, var(--line-soft) 52%, transparent)",
            body_card.group("body"),
        )
        self.assertIn("padding: 0 0 8px", body_title.group("body"))
        self.assertIn("font-size: 11px", body_title.group("body"))
        self.assertIn("font-weight: 640", body_title.group("body"))
        self.assertIn(
            "color: color-mix(in srgb, var(--subtle) 86%, transparent)",
            body_title.group("body"),
        )
        self.assertIn("width: 14px", body_title_rule.group("body"))
        self.assertIn(
            "background: color-mix(in srgb, var(--line-soft) 78%, var(--accent))",
            body_title_rule.group("body"),
        )
        self.assertNotIn("font-size: 11.5px", body_title.group("body"))

    def test_header_status_module_reads_as_quiet_system_gauge(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        mobile_start = css.index("@media (max-width: 720px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        status_module = css_rule(base_css, ".status-module")
        status_orb = css_rule(base_css, ".status-orb")
        status_ready_orb = css_rule(base_css, ".status-module.is-ready .status-orb,\n.status-module.is-success .status-orb")
        status_busy_orb = css_rule(base_css, ".status-module.is-busy .status-orb")

        self.assertIn("border: 1px solid color-mix(in srgb, var(--line-soft) 78%, transparent)", status_module)
        self.assertIn("background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 72%, transparent), color-mix(in srgb, var(--surface-raised) 42%, transparent))", status_module)
        self.assertIn("box-shadow: none", status_module)
        self.assertNotIn("inset 0 1px 0", status_module)

        self.assertIn("width: 8px", status_orb)
        self.assertIn("height: 8px", status_orb)
        self.assertIn("box-shadow: 0 0 0 4px color-mix(in srgb, var(--ok-soft) 48%, transparent)", status_orb)
        self.assertIn("box-shadow: 0 0 0 4px color-mix(in srgb, var(--ok-soft) 48%, transparent)", status_ready_orb)
        self.assertIn("box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-softer) 58%, transparent)", status_busy_orb)

        self.assertIn(".status-module {", mobile_block)
        self.assertIn("gap: 8px", mobile_block)
        self.assertIn("padding: 7px 9px", mobile_block)
        self.assertIn(".status-orb {", mobile_block)
        self.assertIn("width: 7px", mobile_block)
        self.assertIn("height: 7px", mobile_block)

    def test_handheld_header_keeps_system_controls_compact_and_side_by_side(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 720px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".app-header", media_block)
        self.assertIn("gap: 11px", media_block)
        self.assertIn("padding: 12px", media_block)
        self.assertIn(".brand-lockup", media_block)
        self.assertIn("align-items: center", media_block)
        self.assertIn(".brand-mark", media_block)
        self.assertIn("width: 34px", media_block)
        self.assertIn("height: 34px", media_block)
        self.assertIn(".brand-lockup p", media_block)
        self.assertIn("line-height: 1.28", media_block)
        self.assertIn(".workspace", media_block)
        self.assertIn("margin-top: 10px", media_block)
        self.assertIn(".header-actions", media_block)
        self.assertIn("grid-template-columns: minmax(108px, 0.76fr) minmax(0, 1.24fr)", media_block)
        self.assertIn(".status-module", media_block)
        self.assertIn("padding: 7px 9px", media_block)
        self.assertIn(".status-module span", media_block)
        self.assertIn("font-size: 11px", media_block)
        self.assertIn(".status-module strong", media_block)
        self.assertIn("font-size: 12px", media_block)
        self.assertIn("white-space: nowrap", media_block)
        self.assertIn("text-overflow: ellipsis", media_block)

    def test_ultra_narrow_header_density_does_not_regrow_brand_mark(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".app-header", media_block)
        self.assertIn("gap: 9px", media_block)
        self.assertIn("padding: 10px", media_block)
        self.assertIn(".brand-lockup", media_block)
        self.assertIn("gap: 8px", media_block)
        self.assertIn(".brand-lockup p", media_block)
        self.assertIn("display: none", media_block)
        self.assertIn(".brand-mark", media_block)
        self.assertIn("width: 32px", media_block)
        self.assertIn("height: 32px", media_block)
        self.assertIn("font-size: 19px", media_block)
        self.assertIn(".theme-toggle,\n  .status-module", media_block)
        self.assertIn("min-height: 36px", media_block)
        self.assertIn("padding: 6px 8px", media_block)

    def test_tablet_header_actions_do_not_expand_into_oversized_controls(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 561px) and (max-width: 960px)", css)
        media_start = css.index("@media (min-width: 561px) and (max-width: 960px)")
        media_end = css.index("@media (max-width: 820px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".header-actions", media_block)
        self.assertIn("max-width: 640px", media_block)
        self.assertIn("margin-left: auto", media_block)
        self.assertIn("grid-template-columns: minmax(180px, 220px) minmax(240px, 1fr)", media_block)
        self.assertIn(".theme-toggle", media_block)
        self.assertIn("min-width: 0", media_block)
        self.assertIn(".status-module", media_block)
        self.assertIn("min-width: 0", media_block)

    def test_tablet_account_input_uses_mid_density_before_small_tablet_rules(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 721px) and (max-width: 820px)", css)
        media_start = css.index("@media (min-width: 721px) and (max-width: 820px)")
        media_end = css.index("@media (max-width: 820px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".account-input-panel", media_block)
        self.assertIn("gap: 8px", media_block)
        self.assertIn(".account-input-panel textarea", media_block)
        self.assertIn("min-height: 108px", media_block)
        self.assertIn("max-height: 118px", media_block)
        self.assertIn("padding: 10px 12px", media_block)
        self.assertNotIn(".account-format-guide", media_block)
        self.assertIn(".input-quality", media_block)
        self.assertIn("padding: 5px 8px", media_block)
        self.assertIn(".account-list", media_block)
        self.assertIn("max-height: 148px", media_block)
        self.assertNotIn("min-height: 132px", media_block)

    def test_small_tablet_account_header_keeps_privacy_actions_inline(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 561px) and (max-width: 720px)", css)
        media_start = css.index("@media (min-width: 561px) and (max-width: 720px)")
        media_end = css.index("@media (max-width: 560px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".account-input-panel .section-title", media_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", media_block)
        self.assertIn("align-items: center", media_block)
        self.assertIn(".account-input-panel .section-actions", media_block)
        self.assertIn("justify-self: end", media_block)
        self.assertIn("flex-wrap: nowrap", media_block)
        self.assertIn(".account-input-panel .section-title .button", media_block)
        self.assertIn("width: auto", media_block)

    def test_small_tablet_account_input_reduces_empty_textarea_bulk(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 561px) and (max-width: 720px)")
        media_end = css.index("@media (max-width: 560px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".account-input-panel textarea", media_block)
        self.assertIn("min-height: 112px", media_block)
        self.assertIn("max-height: 124px", media_block)
        self.assertIn(".account-input-panel", media_block)
        self.assertIn("gap: 10px", media_block)
        self.assertNotIn("min-height: 142px", media_block)

    def test_desktop_control_column_keeps_log_drawer_while_account_rail_scrolls(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        command = css_rule(base_css, ".control-column.command-center")
        drawer = css_rule(base_css, ".run-log-panel.log-drawer")
        dashboard = css_rule(base_css, ".dashboard-grid")
        account = css_rule(base_css, ".account-input-panel")
        result = css_rule(base_css, ".review-column.mail-review-stage > .result-panel")

        self.assertIn(".control-column", css)
        self.assertIn("display: contents", command)
        self.assertIn("grid-template-columns: minmax(360px, 420px) minmax(0, 1fr)", dashboard)
        self.assertIn("position: fixed", drawer)
        self.assertIn("right: 14px", drawer)
        self.assertIn("min-height: 0", drawer)
        self.assertIn(".account-input-panel", css)
        self.assertIn("gap: 6px", css)
        self.assertIn("grid-template-rows: auto minmax(96px, auto) auto auto minmax(0, 1fr)", css)
        self.assertIn("grid-column: 1", account)
        self.assertIn("grid-row: 1", account)
        self.assertIn("overflow: hidden", account)
        self.assertIn("height: 100%", result)
        self.assertIn("min-height: 78px", css)
        self.assertIn("max-height: 116px", css)
        self.assertIn("max-height: none", css)
        self.assertIn("min-height: 58px", css)
        self.assertIn(".account-status-header .section-kicker", css)
        self.assertIn("display: none", css)
        self.assertIn("padding: 4px 9px", css)
        self.assertIn("line-height: 1.1", css)
        self.assertIn(".run-log-panel", css)
        self.assertIn("transform: translateX(calc(100% + 16px))", drawer)
        operation_panel = css_rule(base_css, ".operation-panel")
        operation_label = css_rule(base_css, ".operation-panel .field-label")
        operation_label_span = css_rule(base_css, ".operation-panel .field-label > span")
        self.assertIn("gap: 12px", operation_panel)
        self.assertIn("padding: 14px", operation_panel)
        self.assertIn("background: #ffffff", operation_panel)
        self.assertIn(".operation-panel .field-label {\n  grid-template-columns: auto minmax(0, 1fr);\n  align-items: center;", base_css)
        self.assertIn("gap: 6px", operation_label)
        self.assertIn("font-size: 10.75px", operation_label_span)
        self.assertIn("color: color-mix(in srgb, var(--muted) 86%, transparent)", operation_label_span)
        self.assertIn("white-space: nowrap", operation_label_span)

    def test_desktop_run_log_can_show_two_recent_events_without_cropping(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        drawer = css_rule(base_css, ".run-log-panel.log-drawer")

        self.assertIn(".activity-toolbar {\n  display: flex;", base_css)
        self.assertIn("min-height: 28px", base_css)
        self.assertIn("top: 122px", drawer)
        self.assertIn("bottom: 18px", drawer)
        self.assertIn("width: min(420px, calc(100vw - 32px))", drawer)
        self.assertIn("grid-template-rows: auto minmax(0, 1fr)", drawer)
        self.assertIn(".activity-log {\n  min-height: 0;\n  padding: 5px;", base_css)
        self.assertIn("gap: 4px", base_css)
        self.assertIn(".activity-event {\n  --event-tone: var(--subtle);", base_css)
        self.assertIn("--event-ring: transparent", base_css)
        self.assertIn("padding: 6px 8px", base_css)
        self.assertIn(
            ".activity-event-body {\n"
            "  min-width: 0;\n"
            "  display: grid;\n"
            "  grid-template-columns: auto minmax(108px, 0.64fr) minmax(0, 1fr) auto;",
            base_css,
        )
        self.assertIn(".activity-event-message {\n  grid-column: 3;\n  grid-row: 1;", base_css)
        self.assertIn(".activity-event-time {\n  grid-column: 4;\n  grid-row: 1;", base_css)

    def test_ultra_narrow_activity_events_use_two_line_product_density(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".activity-event", media_block)
        self.assertIn("padding: 7px 8px", media_block)
        self.assertIn(".activity-event-body", media_block)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto", media_block)
        self.assertIn("grid-template-rows: auto auto", media_block)
        self.assertIn(".activity-event-account", media_block)
        self.assertIn("grid-column: 2", media_block)
        self.assertIn(".activity-event-time", media_block)
        self.assertIn("grid-column: 3", media_block)
        self.assertIn("justify-self: end", media_block)
        self.assertIn(".activity-event-message", media_block)
        self.assertIn("grid-column: 1 / -1", media_block)
        self.assertIn("grid-row: 2", media_block)
        self.assertIn("white-space: nowrap", media_block)

    def test_laptop_height_media_compacts_chrome_without_squeezing_reader(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".app-shell", media_block)
        self.assertIn("padding: 14px 18px", media_block)
        self.assertIn(".app-header", media_block)
        self.assertIn("padding: 12px 14px", media_block)
        self.assertIn(".workspace", media_block)
        self.assertIn("margin: 14px auto 0", media_block)
        self.assertIn(".dashboard-grid", media_block)
        self.assertIn("gap: 12px", media_block)
        self.assertIn("height: calc(100vh - 126px)", media_block)
        self.assertIn(".result-panel", media_block)
        self.assertIn("height: 100%", media_block)
        self.assertIn(".control-column.is-account-compact", media_block)
        self.assertIn("grid-template-rows: auto auto minmax(174px, auto)", media_block)
        self.assertIn(".account-input-panel.is-account-compact", media_block)
        self.assertIn("grid-template-rows: auto minmax(56px, auto) auto auto auto", media_block)

    def test_run_log_exposes_live_context_with_refined_toolbar_hint(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn('id="runLog"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('aria-label="运行记录，最新记录在顶部"', html)
        self.assertIn("activity-frame", html)
        self.assertIn("activity-toolbar", html)
        self.assertIn("activity-pulse", html)
        self.assertIn("activity-hint", html)
        self.assertIn("会话事件", html)
        self.assertIn("最新优先", html)
        self.assertNotIn("terminal-frame", html)
        self.assertNotIn("terminal-toolbar", html)
        self.assertIn(".activity-hint", css)
        self.assertIn("margin-left: auto", css)
        self.assertIn("min-height: 28px", css)
        self.assertIn("padding: 5px", css)
        self.assertIn("line-height: 1.34", css)
        self.assertIn("padding: 6px 8px", css)
        self.assertIn("gap: 5px", css)
        self.assertIn("gap: 2px", css)
        self.assertIn(".activity-event-account", css)
        self.assertIn(".activity-event-message", css)

    def test_run_log_empty_state_reads_as_product_status_not_terminal_placeholder(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("*,\n*::before,\n*::after {\n  box-sizing: border-box;\n}", css)
        self.assertNotIn("等待操作输出", css)
        self.assertNotIn(".terminal-log:empty", css)
        self.assertIn(".activity-log:empty", css)
        self.assertIn("align-content: center", css)
        self.assertIn("justify-items: start", css)
        self.assertIn(".activity-log:empty::before", css)
        self.assertIn('content: "静候会话事件";', css)
        self.assertIn("width: auto", css)
        self.assertIn("max-width: 100%", css)
        self.assertIn("border-left: 2px solid var(--subtle)", css)
        self.assertIn("box-shadow: none", css)
        self.assertIn("font-family: Inter, ui-sans-serif", css)
        self.assertIn(".activity-log:empty::after", css)
        self.assertIn('content: "解析账号或拉取邮件后显示最新记录";', css)
        self.assertIn("font-size: 10.75px", css)

    def test_run_log_empty_state_uses_quiet_event_stream_standby_frame(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        empty_log = css_rule(css, ".activity-log:empty")
        empty_before = css_rule(css, ".activity-log:empty::before")
        empty_after = css_rule(css, ".activity-log:empty::after")

        self.assertIn("position: relative", empty_log)
        self.assertIn(
            "border: 1px solid color-mix(in srgb, var(--activity-line) 48%, transparent)",
            empty_log,
        )
        self.assertIn(
            "border-left-color: color-mix(in srgb, var(--activity-line) 72%, transparent)",
            empty_log,
        )
        self.assertIn("border-radius: var(--radius-sm)", empty_log)
        self.assertIn("radial-gradient(circle at 14px 20px", empty_log)
        self.assertIn(
            "color-mix(in srgb, var(--activity-muted) 54%, transparent) 0 2px",
            empty_log,
        )
        self.assertIn("linear-gradient(180deg, color-mix(in srgb, var(--activity-bar) 38%, transparent)", empty_log)
        self.assertIn("padding: 10px 12px 10px 13px", empty_log)

        self.assertIn("padding: 0 0 0 15px", empty_before)
        self.assertIn(
            "border-left: 2px solid color-mix(in srgb, var(--activity-muted) 34%, transparent)",
            empty_before,
        )
        self.assertIn("letter-spacing: 0.012em", empty_before)
        self.assertIn("padding-left: 17px", empty_after)
        self.assertIn(
            "color: color-mix(in srgb, var(--activity-muted) 78%, transparent)",
            empty_after,
        )

    def test_run_log_clear_action_tracks_empty_and_populated_states(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        js = STATIC_JS.read_text(encoding="utf-8")

        self.assertIn('id="clearLogBtn"', html)
        self.assertIn("disabled", html)
        self.assertIn("function syncLogActions", js)
        self.assertIn("const hasLogs = Boolean(el.runLog?.children.length)", js)
        self.assertIn("el.clearLogBtn.disabled = !hasLogs", js)
        self.assertIn('el.clearLogBtn.setAttribute("aria-disabled", String(!hasLogs))', js)
        self.assertIn('el.clearLogBtn.title = hasLogs ? "清空当前运行记录" : "暂无运行记录"', js)
        self.assertIn("syncLogActions();", js)

    def test_run_log_header_action_reads_as_quiet_event_toolbar(self) -> None:
        html = STATIC_HTML.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        short_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        short_end = css.index("@media (max-width: 980px)", short_start)
        short_block = css[short_start:short_end]
        mobile_start = css.index("@media (max-width: 560px)")
        mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
        mobile_block = css[mobile_start:mobile_end]

        header = css_rule(base_css, ".run-log-panel .section-title")
        clear_button = css_rule(base_css, ".run-log-panel .button.ghost")
        clear_hover = css_rule(base_css, ".run-log-panel .button.ghost:hover:not(:disabled)")
        clear_disabled = css_rule(base_css, '.run-log-panel .button.ghost:disabled:not([aria-busy="true"])')
        clear_icon = css_rule(base_css, ".run-log-panel .button.ghost .icon")

        self.assertIn('id="clearLogBtn"', html)
        self.assertIn('class="button ghost"', html)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", header)
        self.assertIn("min-height: 28px", header)
        self.assertIn("gap: 8px", header)
        self.assertIn("padding: 0 1px", header)

        self.assertIn("min-height: 28px", clear_button)
        self.assertIn("padding: 0 9px", clear_button)
        self.assertIn("border-color: color-mix(in srgb, var(--line-soft) 72%, transparent)", clear_button)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 42%, transparent)", clear_button)
        self.assertIn("color: color-mix(in srgb, var(--muted) 84%, transparent)", clear_button)
        self.assertIn("font-size: 11.5px", clear_button)
        self.assertIn("box-shadow: none", clear_button)
        self.assertNotIn("min-height: 32px", clear_button)

        self.assertIn("transform: none", clear_hover)
        self.assertIn("background: color-mix(in srgb, var(--surface-raised) 62%, transparent)", clear_hover)
        self.assertIn("box-shadow: none", clear_hover)
        self.assertIn("background: transparent", clear_disabled)
        self.assertIn("border-color: transparent", clear_disabled)
        self.assertIn("color: color-mix(in srgb, var(--muted) 48%, transparent)", clear_disabled)
        self.assertIn("opacity: 1", clear_disabled)

        self.assertIn("width: 13px", clear_icon)
        self.assertIn("height: 13px", clear_icon)
        self.assertIn("opacity: 0.68", clear_icon)

        self.assertIn(".run-log-panel .section-title", short_block)
        self.assertIn("min-height: 26px", short_block)
        self.assertIn(".run-log-panel .button.ghost", mobile_block)
        self.assertIn("min-height: 27px", mobile_block)

    def test_desktop_mail_workspace_balances_columns_for_readability(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")

        self.assertIn("grid-template-columns: 1fr", css)
        self.assertIn("grid-template-columns: minmax(360px, 420px) minmax(0, 1fr)", css)
        self.assertNotIn("grid-template-columns: minmax(360px, 0.92fr) minmax(420px, 1.08fr)", css)
        self.assertIn("grid-template-columns: clamp(390px, 42%, 520px) minmax(0, 1fr)", css)
        self.assertIn("grid-template-columns: minmax(0, 1.25fr) repeat(2, minmax(116px, 0.55fr))", css)
        self.assertIn("@media (max-width: 980px)", css)
        self.assertNotIn("@media (max-width: 1180px)", css)
        self.assertIn("grid-template-columns: 1fr", css)

    def test_notebook_width_stacks_mail_reader_inside_two_column_workspace(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-width: 1120px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-workbench", media_block)
        self.assertIn("grid-template-columns: 1fr", media_block)
        self.assertIn(".mail-list-shell", media_block)
        self.assertIn("border-right: 0", media_block)
        self.assertIn("border-bottom: 1px solid var(--line)", media_block)
        self.assertIn(".mail-list", media_block)
        self.assertIn("max-height: 150px", media_block)
        self.assertIn(".mail-detail", media_block)
        self.assertIn("padding: 12px 18px", media_block)
        self.assertNotIn(".dashboard-grid", media_block)

    def test_tablet_width_stacks_mail_workbench_before_phone_breakpoint(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 820px)", css)
        media_start = css.index("@media (max-width: 820px)")
        media_end = css.index("@media (max-width: 720px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-workbench", media_block)
        self.assertIn("grid-template-columns: 1fr", media_block)
        self.assertIn("min-height: 0", media_block)
        self.assertIn(".mail-list-shell", media_block)
        self.assertIn("border-right: 0", media_block)
        self.assertIn("border-bottom: 1px solid var(--line)", media_block)
        self.assertIn(".mail-list", media_block)
        self.assertIn("max-height: 280px", media_block)
        self.assertIn(".mail-reader-shell", media_block)
        self.assertIn("min-height: 420px", media_block)
        self.assertNotIn(".dashboard-grid", media_block)

    def test_notebook_account_format_does_not_need_extra_guide_rules(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-width: 1120px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertNotIn(".account-format-guide", media_block)
        self.assertNotIn(".format-step", media_block)
        self.assertNotIn(".format-separator", media_block)
        self.assertNotIn(".format-token", media_block)

    def test_notebook_reader_compacts_route_without_hiding_recipients(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-width: 1120px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-list", media_block)
        self.assertIn("max-height: 150px", media_block)
        self.assertIn(".detail-header", media_block)
        self.assertIn("padding-bottom: 8px", media_block)
        self.assertIn(".detail-summary-bar", media_block)
        self.assertIn("margin-top: 8px", media_block)
        self.assertIn(".detail-summary-item", media_block)
        self.assertIn("padding: 0", media_block)
        self.assertIn(".reader-toolbar", media_block)
        self.assertIn("margin-top: 7px", media_block)
        self.assertIn(".sender-route.detail-grid", media_block)
        self.assertNotIn(".sender-route.detail-grid {\n    display: none;", media_block)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto minmax(0, 0.82fr)", media_block)
        self.assertIn(".sender-route.detail-grid strong", media_block)
        self.assertIn("white-space: nowrap", media_block)
        self.assertIn("text-overflow: ellipsis", media_block)
        self.assertIn(".body-card-title", media_block)
        self.assertIn("padding: 0 0 8px", media_block)

    def test_notebook_reader_reclaims_vertical_space_for_body_text(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-width: 1120px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-list", media_block)
        self.assertIn("max-height: 150px", media_block)
        self.assertIn(".mail-row", media_block)
        self.assertIn("min-height: 70px", media_block)
        self.assertIn("padding: 9px 11px", media_block)
        self.assertIn(".mail-row-preview", media_block)
        self.assertIn("line-height: 1.3", media_block)
        self.assertIn(".mail-detail", media_block)
        self.assertIn("padding: 12px 18px", media_block)
        self.assertIn(".sender-identity-card", media_block)
        self.assertIn("padding: 8px 10px", media_block)
        self.assertIn(".body-card", media_block)
        self.assertIn("margin-top: 8px", media_block)
        self.assertIn(".body-preview", media_block)
        self.assertIn("padding: 0", media_block)
        self.assertIn("line-height: 1.5", media_block)

    def test_short_desktop_viewports_avoid_clipping_account_status(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn("@media (min-width: 981px) and (max-height: 820px)", css)
        self.assertIn("height: calc(100vh - 126px)", media_block)
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto minmax(174px, 0.52fr)", media_block)
        self.assertIn(".account-input-panel", media_block)
        self.assertIn("overflow: hidden", media_block)
        self.assertIn("grid-template-rows: auto minmax(56px, auto) auto auto minmax(68px, 1fr)", media_block)
        self.assertIn(".account-input-panel.is-account-compact", media_block)
        self.assertIn("grid-template-rows: auto minmax(56px, auto) auto auto auto", media_block)
        self.assertIn("max-height: none", media_block)
        self.assertIn("min-height: 68px", media_block)
        self.assertIn(".account-empty-guide", media_block)
        self.assertIn("display: none", media_block)
        self.assertIn(".run-log-panel", media_block)
        self.assertIn("min-height: 174px", media_block)
        self.assertNotIn("grid-template-rows: auto auto minmax(180px, auto)", media_block)

    def test_short_desktop_operation_controls_compact_without_losing_context(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".operation-panel", media_block)
        self.assertIn("padding: 9px 12px", media_block)
        self.assertIn("gap: 7px", media_block)
        self.assertIn(".operation-panel .section-kicker", media_block)
        self.assertIn("display: none", media_block)
        self.assertIn(".operation-grid", media_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 104px", media_block)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", media_block)
        self.assertIn("white-space: nowrap", media_block)
        self.assertIn(".operation-panel input:not([type=\"checkbox\"])", media_block)
        self.assertIn("min-height: 32px", media_block)
        self.assertIn(".operation-note", media_block)
        self.assertIn("font-size: 11.5px", media_block)
        self.assertIn(".operation-panel .button", media_block)

    def test_short_desktop_run_log_empty_state_stays_readable_in_compact_height(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".activity-log:empty", media_block)
        self.assertIn("align-content: start", media_block)
        self.assertIn(".activity-log:empty::before", media_block)
        self.assertIn('content: "静候事件";', media_block)
        self.assertIn("padding: 0 0 0 7px", media_block)
        self.assertIn("line-height: 1.16", media_block)
        self.assertIn(".activity-log:empty::after", media_block)
        self.assertIn("padding-left: 9px", media_block)
        self.assertIn("font-size: 10.5px", media_block)

    def test_short_desktop_populated_run_log_keeps_events_uncropped(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn("grid-template-rows: minmax(0, 1fr) auto minmax(174px, 0.52fr)", media_block)
        self.assertIn(".run-log-panel {\n    min-height: 174px;", media_block)
        self.assertIn(".activity-event-body", media_block)
        self.assertIn("grid-template-columns: auto minmax(88px, 0.58fr) minmax(0, 1fr) auto", media_block)
        self.assertIn(".activity-event-message", media_block)
        self.assertIn("grid-column: 3", media_block)
        self.assertIn("grid-row: 1", media_block)
        self.assertIn(".activity-event-time", media_block)
        self.assertIn("grid-column: 4", media_block)

    def test_short_desktop_reader_compacts_detail_to_expose_body_preview(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (min-width: 981px) and (max-height: 820px)")
        media_end = css.index("@media (max-width: 980px)", media_start)
        media_block = css[media_start:media_end]

        for selector in [
            ".mail-detail",
            ".detail-header",
            ".detail-summary-bar",
            ".detail-summary-item",
            ".reader-toolbar",
            ".reader-stat",
            ".detail-meta-card",
            ".detail-grid",
            ".body-card",
            ".body-card-title",
            ".body-preview",
        ]:
            self.assertIn(selector, media_block)

        self.assertIn("padding: 20px 28px", media_block)
        self.assertIn("font-size: 22px", media_block)
        self.assertIn("margin-top: 12px", media_block)
        self.assertIn("padding: 10px 13px", media_block)
        self.assertIn("line-height: 1.58", media_block)
        self.assertIn("font-size: 13.5px", media_block)

    def test_mobile_account_input_panel_keeps_primary_controls_above_the_fold(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".account-input-panel", media_block)
        self.assertIn("gap: 8px", media_block)
        self.assertIn(".account-input-panel .section-title", media_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", media_block)
        self.assertIn("align-items: center", media_block)
        self.assertIn(".account-input-panel .section-actions", media_block)
        self.assertIn("justify-self: end", media_block)
        self.assertIn("flex-wrap: nowrap", media_block)
        self.assertIn(".account-input-panel .field-label", media_block)
        self.assertIn("gap: 5px", media_block)
        self.assertIn(".account-input-panel textarea", media_block)
        self.assertIn("min-height: 76px", media_block)
        self.assertIn("max-height: 96px", media_block)
        self.assertNotIn("textarea {\n    min-height: 142px;", media_block)

    def test_mobile_first_viewport_surfaces_mail_result_header_and_summary(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        account_list = re.search(r"\.account-list \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        operation_panel = re.search(r"\.operation-panel \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        result_panel = re.search(r"\.result-panel \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        operation_note = re.search(r"\.operation-note \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        advanced_summary = re.search(r"\.advanced-settings > summary \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_summary = re.search(r"\.mail-result-summary \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(account_list)
        self.assertIsNotNone(operation_panel)
        self.assertIsNotNone(result_panel)
        self.assertIsNotNone(operation_note)
        self.assertIsNotNone(advanced_summary)
        self.assertIsNotNone(mail_summary)

        self.assertIn("max-height: 96px", account_list.group("body"))
        self.assertIn("min-height: 52px", account_list.group("body"))
        self.assertIn("gap: 6px", operation_panel.group("body"))
        self.assertIn("padding: 8px 10px", operation_panel.group("body"))
        self.assertIn("padding: 10px 12px", result_panel.group("body"))
        self.assertIn("scroll-margin-top: 8px", result_panel.group("body"))
        self.assertIn("display: none", operation_note.group("body"))
        self.assertIn("min-height: 28px", advanced_summary.group("body"))
        self.assertIn("padding: 4px 8px", advanced_summary.group("body"))
        self.assertIn("gap: 4px", mail_summary.group("body"))
        self.assertIn("padding: 8px 10px", mail_summary.group("body"))
        self.assertNotIn("max-height: 132px", media_block)

    def test_mobile_page_space_prioritizes_results_before_log_details(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        dashboard_match = re.search(r"^\s*\.dashboard-grid \{\n(?P<body>.*?)\n\s*\}", media_block, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(dashboard_match)
        dashboard_rule = dashboard_match.group("body")
        self.assertIn("display: flex", dashboard_rule)
        self.assertIn("flex-direction: column", dashboard_rule)
        self.assertIn("align-items: stretch", dashboard_rule)
        self.assertIn(".control-column.command-center", media_block)
        self.assertIn(".operation-panel", media_block)
        self.assertIn("order: 2", media_block)
        operation_panel_rule = re.search(
            r"^\s*\.operation-panel \{\n(?P<body>.*?)\n\s*\}",
            media_block,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(operation_panel_rule)
        self.assertIn("width: 100%", operation_panel_rule.group("body"))
        self.assertIn(".review-column.mail-review-stage", media_block)
        self.assertIn("order: 3", media_block)
        log_drawer_rule = re.search(
            r"^\s*\.run-log-panel\.log-drawer \{\n(?P<body>.*?)\n\s*\}",
            media_block,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(log_drawer_rule)
        log_drawer_body = log_drawer_rule.group("body")
        self.assertIn("position: fixed", log_drawer_body)
        self.assertIn("right: 10px", log_drawer_body)
        self.assertIn("width: min(360px, calc(100vw - 20px))", log_drawer_body)
        self.assertIn("transform: translateX(calc(100% + 12px))", log_drawer_body)
        self.assertNotIn("position: sticky", log_drawer_body)
        mobile_action_bar_rule = re.search(
            r"^\s*\.session-action-bar \{\n(?P<body>.*?)\n\s*\}",
            media_block,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(mobile_action_bar_rule)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", mobile_action_bar_rule.group("body"))
        mobile_code_summary_rule = re.search(
            r"^\s*\.operation-code-summary \{\n(?P<body>.*?)\n\s*\}",
            media_block,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(mobile_code_summary_rule)
        self.assertIn("min-height: 44px", mobile_code_summary_rule.group("body"))
        self.assertIn(".mail-empty-panel.mail-list-empty-state", media_block)
        self.assertIn("min-height: 0", media_block)

    def test_mobile_account_format_and_status_rows_use_compact_inline_density(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertNotIn(".account-format-guide", media_block)
        self.assertNotIn(".format-label", media_block)
        self.assertIn(".account-list", media_block)
        self.assertIn("max-height: 96px", media_block)
        self.assertIn("min-height: 52px", media_block)
        self.assertIn(".account-row", media_block)
        self.assertIn("padding: 7px 9px", media_block)
        self.assertIn(".account-row-head strong", media_block)
        self.assertIn("overflow: hidden", media_block)
        self.assertIn("text-overflow: ellipsis", media_block)
        self.assertIn("white-space: nowrap", media_block)
        self.assertIn(".account-row .pill", media_block)
        self.assertIn("min-height: 20px", media_block)
        self.assertIn("padding: 1px 7px", media_block)
        self.assertIn(".operation-panel", media_block)
        self.assertIn("scroll-margin-top: 10px", media_block)

    def test_ultra_narrow_mobile_prioritizes_action_buttons_without_overflow(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 360px)", css)
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".brand-lockup p", media_block)
        self.assertIn("display: none", media_block)
        self.assertIn(".account-input-panel textarea", media_block)
        self.assertIn("min-height: 88px", media_block)
        self.assertIn("max-height: 108px", media_block)
        self.assertIn(".quality-copy {\n    display: grid;\n    grid-template-columns: 1fr", media_block)
        self.assertIn(
            ".quality-copy > span:not(.quality-chip) {\n"
            "    overflow: visible;\n"
            "    text-overflow: clip;\n"
            "    white-space: normal;",
            media_block,
        )
        self.assertIn("grid-template-columns: 1fr", media_block)
        self.assertIn("align-items: start", media_block)
        note_block = re.search(r"\.operation-note \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        self.assertIsNotNone(note_block)
        self.assertIn("display: none", note_block.group("body"))
        self.assertIn(".action-stack", media_block)
        self.assertIn("gap: 8px", media_block)
        self.assertNotIn("overflow-x: auto", media_block)

    def test_ultra_narrow_account_status_rows_stay_inside_panel_with_visible_pills(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".account-list", media_block)
        self.assertIn("min-width: 0", media_block)
        self.assertIn("overflow-x: hidden", media_block)
        self.assertIn(".account-row", media_block)
        self.assertIn("max-width: 100%", media_block)
        self.assertIn("box-sizing: border-box", media_block)
        self.assertIn(".account-row-head", media_block)
        self.assertIn("display: grid", media_block)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", media_block)
        self.assertIn(".account-row-head strong", media_block)
        self.assertIn("min-width: 0", media_block)
        self.assertIn(".account-row .pill", media_block)
        self.assertIn("flex: 0 0 auto", media_block)
        self.assertIn("white-space: nowrap", media_block)

    def test_account_status_card_limits_copy_to_icon_and_uses_main_area_for_selection(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        base_css = css[: css.index("@media")]
        render_accounts = js[js.index("function renderAccounts"):js.index("function mergeFetchedMessagesByAccount")]
        copy_block = render_accounts[render_accounts.index("const copyButton"):render_accounts.index("const selectButton")]

        copy_inner = re.search(r"copyButton\.innerHTML = `(?P<body>.*?)`;", copy_block, re.DOTALL)
        self.assertIsNotNone(copy_inner)
        self.assertIn("copy-account-icon", copy_inner.group("body"))
        self.assertNotIn("account.email", copy_inner.group("body"))
        self.assertNotIn("account-copy-email", copy_inner.group("body"))

        select_inner = re.search(r"selectButton\.innerHTML = `(?P<body>.*?)`;", render_accounts, re.DOTALL)
        self.assertIsNotNone(select_inner)
        self.assertIn('class="account-email-label"', select_inner.group("body"))
        self.assertIn("${escapeHtml(account.email)}", select_inner.group("body"))
        self.assertIn("${statusPill(account)}", select_inner.group("body"))
        self.assertIn('selectButton.addEventListener("click", () => selectAccount(account.email));', render_accounts)
        self.assertIn('setStatus("已选择账号", "ready");', js)

        account_row = css_rule(base_css, ".account-row")
        copy_button = css_rule(base_css, ".copy-account-button")
        select_button = css_rule(base_css, ".account-select-button")
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", account_row)
        self.assertIn("width: 44px", copy_button)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", select_button)
        self.assertNotIn("grid-template-columns: 48px minmax(0, 1fr)", copy_button)
        self.assertNotIn(".copy-account-button::after", base_css)

    def test_ultra_narrow_operation_note_keeps_session_scope_readable(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]
        note_block = re.search(r"\.operation-note \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(note_block)
        self.assertIn("display: none", note_block.group("body"))
        self.assertIn("align-items: center", note_block.group("body"))
        self.assertIn("min-height: 0", note_block.group("body"))
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", note_block.group("body"))
        self.assertNotIn("-webkit-line-clamp: 2", note_block.group("body"))

    def test_mobile_mail_rows_keep_time_inline_for_client_like_scanning(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-row-main", media_block)
        self.assertIn("grid-template-columns: 10px minmax(0, 1fr) max-content", media_block)
        self.assertIn(".mail-time", media_block)
        self.assertIn("grid-column: auto", media_block)
        self.assertIn("justify-self: end", media_block)
        self.assertNotIn("grid-column: 2;", media_block)

    def test_mobile_populated_mail_rows_fit_four_results_without_cutoff(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        mail_list = re.search(r"\.mail-list \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_row = re.search(r"\.mail-row \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_main = re.search(r"\.mail-row-main \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_meta = re.search(r"\.mail-row-meta-line \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_preview = re.search(r"\.mail-row-preview \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(mail_list)
        self.assertIsNotNone(mail_row)
        self.assertIsNotNone(mail_main)
        self.assertIsNotNone(mail_meta)
        self.assertIsNotNone(mail_preview)

        self.assertIn("max-height: 304px", mail_list.group("body"))
        self.assertIn("gap: 6px", mail_list.group("body"))
        self.assertIn("min-height: 70px", mail_row.group("body"))
        self.assertIn("gap: 4px", mail_row.group("body"))
        self.assertIn("padding: 9px 10px 9px 12px", mail_row.group("body"))
        self.assertIn("gap: 6px", mail_main.group("body"))
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(74px, auto)", mail_meta.group("body"))
        self.assertIn("font-size: 11.5px", mail_preview.group("body"))
        self.assertIn("line-height: 1.28", mail_preview.group("body"))
        self.assertLessEqual((4 * 70) + (3 * 6), 304)
        self.assertNotIn("padding: 11px 11px 11px 13px", media_block)

    def test_mobile_selected_mail_row_uses_quiet_inline_marker_without_card_lift(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        selected_row = re.search(
            r"  \.mail-row\.active,\n"
            r"  \.mail-row\[aria-selected=\"true\"\] \{\n(?P<body>.*?)\n  \}",
            media_block,
            re.DOTALL,
        )
        selected_hover = re.search(
            r"  \.mail-row\.active:hover,\n"
            r"  \.mail-row\[aria-selected=\"true\"\]:hover \{\n(?P<body>.*?)\n  \}",
            media_block,
            re.DOTALL,
        )
        selected_rail = re.search(
            r"  \.mail-row\.active::before,\n"
            r"  \.mail-row\[aria-selected=\"true\"\]::before \{\n(?P<body>.*?)\n  \}",
            media_block,
            re.DOTALL,
        )
        selected_dot = re.search(
            r"  \.mail-row\.active \.mail-row-status-dot,\n"
            r"  \.mail-row\[aria-selected=\"true\"\] \.mail-row-status-dot \{\n(?P<body>.*?)\n  \}",
            media_block,
            re.DOTALL,
        )
        mail_row = re.search(r"  \.mail-row \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(selected_row)
        self.assertIsNotNone(selected_hover)
        self.assertIsNotNone(selected_rail)
        self.assertIsNotNone(selected_dot)
        self.assertIsNotNone(mail_row)

        self.assertIn("border-color: color-mix(in srgb, var(--accent) 12%, var(--line-soft))", selected_row.group("body"))
        self.assertIn("color-mix(in srgb, var(--accent-softer) 16%, var(--row-bg))", selected_row.group("body"))
        self.assertIn("box-shadow: none", selected_row.group("body"))
        self.assertIn("transform: none", selected_row.group("body"))
        self.assertIn("box-shadow: none", selected_hover.group("body"))
        self.assertIn("transform: none", selected_hover.group("body"))
        self.assertIn("width: 1px", selected_rail.group("body"))
        self.assertIn("color-mix(in srgb, var(--accent) 44%, transparent)", selected_rail.group("body"))
        self.assertIn("opacity: 0.68", selected_rail.group("body"))
        self.assertIn("width: 6px", selected_dot.group("body"))
        self.assertIn("height: 6px", selected_dot.group("body"))
        self.assertIn("opacity: 0.82", selected_dot.group("body"))
        self.assertIn("min-height: 70px", mail_row.group("body"))
        self.assertIn("padding: 9px 10px 9px 12px", mail_row.group("body"))
        self.assertNotIn("translateY(-1px)", selected_row.group("body"))
        self.assertNotIn("0 8px", selected_row.group("body"))
        self.assertNotIn("0 10px", selected_row.group("body"))

    def test_ultra_narrow_mail_rows_prioritize_subject_and_sender_over_metadata_gutters(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        mail_main = re.search(r"\.mail-row-main \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_meta = re.search(r"\.mail-row-meta-line \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_account = re.search(r"\.mail-row-account \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        mail_time = re.search(r"\.mail-time \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(mail_main)
        self.assertIsNotNone(mail_meta)
        self.assertIsNotNone(mail_account)
        self.assertIsNotNone(mail_time)

        self.assertIn("grid-template-columns: 8px minmax(0, 1fr) max-content", mail_main.group("body"))
        self.assertIn("gap: 5px", mail_main.group("body"))
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(62px, 86px)", mail_meta.group("body"))
        self.assertIn("gap: 5px", mail_meta.group("body"))
        self.assertIn("max-width: 86px", mail_account.group("body"))
        self.assertIn("font-size: 10.25px", mail_account.group("body"))
        self.assertIn("opacity: 0.72", mail_account.group("body"))
        self.assertIn("font-size: 10.25px", mail_time.group("body"))
        self.assertNotIn("min-height: 76px", media_block)

    def test_mobile_mail_workbench_uses_soft_transition_between_list_and_reader(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        list_shell = re.search(r"\.mail-list-shell \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        reader_shell = re.search(r"\.mail-reader-shell \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        reader_hairline = re.search(r"\.mail-reader-shell::before \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIsNotNone(list_shell)
        self.assertIsNotNone(reader_shell)
        self.assertIsNotNone(reader_hairline)
        self.assertIn(
            "border-bottom: 1px solid color-mix(in srgb, var(--line-soft) 58%, transparent)",
            list_shell.group("body"),
        )
        self.assertIn(
            "linear-gradient(180deg, color-mix(in srgb, var(--surface) 72%, transparent), color-mix(in srgb, var(--surface-raised) 42%, transparent))",
            list_shell.group("body"),
        )
        self.assertIn(
            "linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 32%, transparent), transparent 72px)",
            reader_shell.group("body"),
        )
        self.assertIn("content: \"\"", reader_hairline.group("body"))
        self.assertIn("height: 1px", reader_hairline.group("body"))
        self.assertIn(
            "linear-gradient(90deg, transparent, color-mix(in srgb, var(--line-soft) 68%, transparent), transparent)",
            reader_hairline.group("body"),
        )
        self.assertIn("pointer-events: none", reader_hairline.group("body"))
        self.assertNotIn("border-bottom: 1px solid var(--line)", list_shell.group("body"))

    def test_mobile_sender_identity_compacts_route_before_body_preview(self) -> None:
        js = STATIC_JS.read_text(encoding="utf-8")
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]
        route = re.search(r"\.sender-route\.detail-grid \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        route_label = re.search(r"\.sender-route\.detail-grid span \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        route_value = re.search(r"\.sender-route\.detail-grid strong \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIn('title="${escapeHtml(mail.recipients || "-")}"', js)
        self.assertIn('title="${escapeHtml(mail.account_email || "-")}"', js)
        self.assertIsNotNone(route)
        self.assertIsNotNone(route_label)
        self.assertIsNotNone(route_value)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr)", route.group("body"))
        self.assertIn("align-items: baseline", route.group("body"))
        self.assertIn("gap: 4px 7px", route.group("body"))
        self.assertIn("margin-top: 1px", route.group("body"))
        self.assertIn("padding-top: 5px", route.group("body"))
        self.assertIn("font-size: 10.25px", route_label.group("body"))
        self.assertIn("letter-spacing: 0.018em", route_label.group("body"))
        self.assertIn("overflow: hidden", route_value.group("body"))
        self.assertIn("text-overflow: ellipsis", route_value.group("body"))
        self.assertIn("white-space: nowrap", route_value.group("body"))
        self.assertIn("line-height: 1.24", route_value.group("body"))
        self.assertNotIn("grid-template-columns: 1fr", route.group("body"))
        self.assertNotIn("white-space: normal", route_value.group("body"))
        self.assertNotIn("overflow-wrap: anywhere", route_value.group("body"))
        self.assertIn(".body-card", media_block)
        body_card = re.search(r"\.body-card \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        self.assertIsNotNone(body_card)
        self.assertIn("margin-top: 10px", body_card.group("body"))

    def test_mobile_sender_route_spans_full_card_before_ultra_narrow_rules(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (max-width: 360px)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".sender-copy", media_block)
        self.assertIn("display: contents", media_block)
        self.assertIn(".sender-copy-head", media_block)
        self.assertIn("grid-column: 2 / 3", media_block)
        self.assertIn(".sender-address", media_block)
        self.assertIn(".sender-route.detail-grid", media_block)
        self.assertIn("grid-column: 1 / -1", media_block)
        self.assertIn("grid-row: 3", media_block)

    def test_mobile_reader_chips_stay_single_row_before_sender_context(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".reader-toolbar", media_block)
        self.assertIn("display: flex", media_block)
        self.assertIn("flex-wrap: wrap", media_block)
        self.assertIn(".reader-stat", media_block)
        self.assertIn("min-width: 0", media_block)
        self.assertIn("font-size: 10.5px", media_block)
        self.assertIn("white-space: nowrap", media_block)
        self.assertIn(".sender-route.detail-grid span:nth-of-type(2)", media_block)
        self.assertIn(".sender-route.detail-grid strong:nth-of-type(2)", media_block)
        self.assertIn("display: none", media_block)

    def test_ultra_narrow_reader_chips_keep_primary_reading_metric_visible(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".reader-toolbar", media_block)
        self.assertIn("display: flex", media_block)
        self.assertIn("flex-wrap: wrap", media_block)
        self.assertIn(".reader-stat.is-primary", media_block)
        self.assertIn("justify-content: flex-start", media_block)
        self.assertIn(".reader-stat:not(.is-primary)", media_block)
        self.assertNotIn("justify-content: center", media_block)
        self.assertNotIn("grid-template-columns: repeat(3, minmax(0, 1fr))", media_block)

    def test_ultra_narrow_sender_identity_route_spans_full_card_width(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 360px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".sender-identity-card", media_block)
        self.assertIn("grid-template-columns: 34px minmax(0, 1fr)", media_block)
        self.assertIn(".sender-copy", media_block)
        self.assertIn("display: contents", media_block)
        self.assertIn(".sender-copy-head", media_block)
        self.assertIn("grid-column: 2", media_block)
        self.assertIn(".sender-address", media_block)
        self.assertIn(".sender-route.detail-grid", media_block)
        self.assertIn("grid-column: 1 / -1", media_block)
        self.assertIn("margin-top: 2px", media_block)

    def test_mobile_body_preview_starts_inside_first_reader_viewport(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]
        body_title = re.search(r"\.body-card-title \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)
        body_preview = re.search(r"\.body-preview \{\n(?P<body>.*?)\n  \}", media_block, re.DOTALL)

        self.assertIn(".body-card-title", media_block)
        self.assertIsNotNone(body_title)
        self.assertIn("padding: 0 0 8px", body_title.group("body"))
        self.assertIn("font-size: 11px", body_title.group("body"))
        self.assertIn(".body-preview", media_block)
        self.assertIsNotNone(body_preview)
        self.assertIn("padding: 0", body_preview.group("body"))
        self.assertIn("line-height: 1.62", body_preview.group("body"))

    def test_mobile_loading_detail_skeleton_uses_bounded_summary_grid(self) -> None:
        css = STATIC_CSS.read_text(encoding="utf-8")
        media_start = css.index("@media (max-width: 560px)")
        media_end = css.index("@media (prefers-reduced-motion: reduce)", media_start)
        media_block = css[media_start:media_end]

        self.assertIn(".mail-detail-loading", media_block)
        self.assertIn("min-width: 0", media_block)
        self.assertIn("max-width: 100%", media_block)
        self.assertIn(".detail-skeleton-summary", media_block)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", media_block)
        self.assertIn(".detail-skeleton-block:first-child", media_block)
        self.assertIn("grid-column: 1 / -1", media_block)
        self.assertNotIn("minmax(150px, 1.35fr) minmax(92px, 0.8fr) minmax(112px, 0.95fr)", media_block)


if __name__ == "__main__":
    unittest.main()
