import ast
import importlib
import inspect
from pathlib import Path
from tempfile import NamedTemporaryFile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_BATCH_SOURCES = {"load_accounts", "resolve_accounts"}
BATCH_SERVICE_TERMINALS = {
    "BatchFetchService": "fetch_accounts",
    "BatchCheckService": "check_accounts",
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base_module = _import_from_base(path, node)
            if not base_module:
                continue
            modules.add(base_module)
            modules.update(
                f"{base_module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )
    return modules


def _import_from_base(path: Path, node: ast.ImportFrom) -> str | None:
    if not node.level:
        return node.module
    package_parts = list(path.resolve().parent.relative_to(ROOT.resolve()).parts)
    keep_count = max(0, len(package_parts) - node.level + 1)
    base_parts = package_parts[:keep_count]
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts) or None


def function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function not found: {name}")


def account_batch_loops(function: ast.FunctionDef) -> list[ast.AST]:
    nodes = list(_function_body_nodes(function))
    service_types = _batch_service_types(nodes)
    tainted_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in nodes:
            assigned_names: set[str] = set()
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                for target in node.targets:
                    assigned_names.update(_target_names(target))
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                assigned_names.update(_target_names(node.target))
            if value is None or not _is_account_batch(
                value,
                tainted_names,
                service_types,
            ):
                continue
            new_names = assigned_names - tainted_names
            if new_names:
                tainted_names.update(new_names)
                changed = True

    prohibited: list[ast.AST] = []
    for node in nodes:
        if isinstance(node, (ast.For, ast.AsyncFor)):
            if _is_account_batch(node.iter, tainted_names, service_types):
                prohibited.append(node)
        elif isinstance(node, ast.comprehension):
            if _is_account_batch(node.iter, tainted_names, service_types):
                prohibited.append(node)
    return prohibited


def _batch_service_types(nodes: list[ast.AST]) -> dict[str, str]:
    service_types: dict[str, str] = {}
    for node in nodes:
        targets: list[ast.AST] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        service_type = _batch_service_constructor(value)
        if service_type is None:
            continue
        for target in targets:
            for name in _target_names(target):
                service_types[name] = service_type
    return service_types


def _batch_service_constructor(node: ast.AST | None) -> str | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in BATCH_SERVICE_TERMINALS
    ):
        return node.func.id
    return None


def _function_body_nodes(function: ast.FunctionDef) -> list[ast.AST]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            nodes.append(child)
            visit(child)

    visit(function)
    return nodes


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_target_names(element))
        return names
    return set()


def _is_account_batch(
    node: ast.AST,
    tainted_names: set[str],
    service_types: dict[str, str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted_names
    if isinstance(node, ast.Call):
        call_name = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        if call_name in ACCOUNT_BATCH_SOURCES:
            return True
        if _is_safe_batch_terminal(node, service_types):
            return False
        if isinstance(node.func, ast.Attribute) and _is_account_batch(
            node.func.value,
            tainted_names,
            service_types,
        ):
            return True
        return any(
            _is_account_batch(argument, tainted_names, service_types)
            for argument in node.args
        ) or any(
            _is_account_batch(keyword.value, tainted_names, service_types)
            for keyword in node.keywords
        )
    return any(
        _is_account_batch(child, tainted_names, service_types)
        for child in ast.iter_child_nodes(node)
    )


def _is_safe_batch_terminal(
    node: ast.Call,
    service_types: dict[str, str],
) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    receiver = node.func.value
    service_type = None
    if isinstance(receiver, ast.Name):
        service_type = service_types.get(receiver.id)
    else:
        service_type = _batch_service_constructor(receiver)
    return (
        service_type is not None
        and BATCH_SERVICE_TERMINALS[service_type] == node.func.attr
    )


class ArchitectureTests(unittest.TestCase):
    def test_account_batch_loop_detection_catches_aliases_wrappers_and_comprehensions(self) -> None:
        sources = (
            (
                "list comprehension alias",
                "def entry(path):\n"
                "    accounts = load_accounts(path)\n"
                "    alias = list(accounts)\n"
                "    return [mailbox for mailbox in alias]\n",
            ),
            (
                "enumerated loop alias",
                "def entry(path):\n"
                "    accounts = load_accounts(path)\n"
                "    pending = accounts\n"
                "    for mailbox in enumerate(pending):\n"
                "        pass\n",
            ),
            (
                "set wrapper",
                "def entry(path):\n"
                "    accounts = load_accounts(path)\n"
                "    pending = set(accounts)\n"
                "    for mailbox in pending:\n"
                "        pass\n",
            ),
            (
                "frozenset wrapper",
                "def entry(path):\n"
                "    accounts = load_accounts(path)\n"
                "    pending = frozenset(accounts)\n"
                "    return [mailbox for mailbox in pending]\n",
            ),
            (
                "filter wrapper",
                "def entry(path):\n"
                "    accounts = load_accounts(path)\n"
                "    pending = filter(None, accounts)\n"
                "    return tuple(mailbox for mailbox in pending)\n",
            ),
            (
                "custom wrapper",
                "def entry(path, wrap):\n"
                "    accounts = load_accounts(path)\n"
                "    pending = wrap(accounts)\n"
                "    for mailbox in pending:\n"
                "        pass\n",
            ),
        )

        for name, source in sources:
            with self.subTest(name=name):
                function = ast.parse(source).body[0]
                self.assertEqual(len(account_batch_loops(function)), 1)

    def test_account_batch_loop_detection_finds_named_sources_and_direct_source_loops(self) -> None:
        sources = (
            "def entry(payload, config):\n"
            "    resolved_accounts = resolve_accounts(payload, config)\n"
            "    alias = list(resolved_accounts)\n"
            "    return [mailbox for mailbox in alias]\n",
            "def entry(path):\n"
            "    pending_accounts = load_accounts(path)\n"
            "    for mailbox in enumerate(pending_accounts):\n"
            "        pass\n",
            "def entry(path):\n"
            "    for mailbox in load_accounts(path):\n"
            "        pass\n",
        )

        for source in sources:
            with self.subTest(source=source):
                function = ast.parse(source).body[0]
                self.assertEqual(len(account_batch_loops(function)), 1)

    def test_account_batch_loop_detection_only_trusts_real_batch_service_results(self) -> None:
        safe_sources = (
            "def entry(path, fetcher):\n"
            "    accounts = load_accounts(path)\n"
            "    batch = BatchFetchService(fetcher).fetch_accounts(accounts)\n"
            "    for result in batch.account_results:\n"
            "        pass\n",
            "def entry(path, checker):\n"
            "    accounts = load_accounts(path)\n"
            "    service = BatchCheckService(checker)\n"
            "    batch = service.check_accounts(accounts)\n"
            "    for result in batch.account_results:\n"
            "        pass\n",
        )

        for source in safe_sources:
            with self.subTest(source=source):
                function = ast.parse(source).body[0]
                self.assertEqual(account_batch_loops(function), [])

        unsafe_function = ast.parse(
            "def entry(path, wrap):\n"
            "    resolved_accounts = load_accounts(path)\n"
            "    fetch_accounts = wrap\n"
            "    batch = fetch_accounts(resolved_accounts)\n"
            "    for row in batch:\n"
            "        pass\n"
        ).body[0]

        self.assertEqual(len(account_batch_loops(unsafe_function)), 1)

    def test_imported_modules_records_base_and_imported_alias_modules(self) -> None:
        with NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir=ROOT / "mail_receiver",
            encoding="utf-8",
            delete=False,
        ) as fixture:
            fixture.write(
                "from mail_receiver import imap_client\n"
                "from http import server\n"
                "from . import imap_client\n"
            )
            fixture_path = Path(fixture.name)

        try:
            imports = imported_modules(fixture_path)
        finally:
            fixture_path.unlink(missing_ok=True)

        self.assertTrue(
            {
                "mail_receiver",
                "mail_receiver.imap_client",
                "http",
                "http.server",
            }.issubset(imports)
        )

    def test_imported_modules_normalizes_relative_imports_to_package_names(self) -> None:
        with NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir=ROOT / "mail_receiver",
            encoding="utf-8",
            delete=False,
        ) as fixture:
            fixture.write("from .imap_client import fetch_messages\n")
            fixture_path = Path(fixture.name)

        try:
            imports = imported_modules(fixture_path)
        finally:
            fixture_path.unlink(missing_ok=True)

        self.assertEqual(
            imports,
            {
                "mail_receiver.imap_client",
                "mail_receiver.imap_client.fetch_messages",
            },
        )

    def test_architecture_modules_avoid_vague_public_type_names(self) -> None:
        prohibited = {"Manager", "Helper", "Utils", "Processor", "Data"}
        public_types: set[str] = set()
        for module_name in (
            "mail_receiver.application",
            "mail_receiver.mail_fetching",
            "mail_receiver.message_parsing",
            "mail_receiver.repositories",
        ):
            module = importlib.import_module(module_name)
            public_types.update(
                name
                for name, value in vars(module).items()
                if not name.startswith("_")
                and inspect.isclass(value)
                and value.__module__ == module_name
            )

        self.assertTrue(prohibited.isdisjoint(public_types), public_types & prohibited)

    def test_application_layer_does_not_import_entrypoints_or_infrastructure(self) -> None:
        imports = imported_modules(ROOT / "mail_receiver" / "application.py")
        prohibited = {
            "argparse",
            "http.server",
            "imaplib",
            "sqlite3",
            "mail_receiver.cli",
            "mail_receiver.imap_client",
            "mail_receiver.storage",
            "mail_receiver.web",
        }

        self.assertTrue(prohibited.isdisjoint(imports), imports & prohibited)

    def test_message_parsing_layer_does_not_import_imap_transport(self) -> None:
        imports = imported_modules(ROOT / "mail_receiver" / "message_parsing.py")

        self.assertNotIn("imaplib", imports)
        self.assertNotIn("mail_receiver.imap_client", imports)

    def test_web_and_cli_depend_on_shared_batch_service(self) -> None:
        for module_name in ("mail_receiver.web", "mail_receiver.cli"):
            module = importlib.import_module(module_name)
            self.assertTrue(
                hasattr(module, "BatchFetchService"),
                f"{module_name} must compose BatchFetchService",
            )

    def test_entrypoints_do_not_loop_over_accounts_for_batch_business_logic(self) -> None:
        entrypoints = (
            (ROOT / "mail_receiver" / "web.py", "check_accounts_data"),
            (ROOT / "mail_receiver" / "cli.py", "fetch"),
        )

        for path, function_name in entrypoints:
            with self.subTest(path=path.name, function=function_name):
                function = function_node(path, function_name)
                prohibited = account_batch_loops(function)
                self.assertEqual(
                    prohibited,
                    [],
                    f"{path.name}:{function_name} must delegate account batches",
                )

    def test_web_check_composes_batch_check_service(self) -> None:
        function = function_node(
            ROOT / "mail_receiver" / "web.py",
            "check_accounts_data",
        )
        called_names = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertIn("BatchCheckService", called_names)


if __name__ == "__main__":
    unittest.main()
