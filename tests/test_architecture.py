import ast
import importlib
import inspect
from pathlib import Path
from tempfile import NamedTemporaryFile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SAFE_ACCOUNT_BATCH_TERMINALS = {"fetch_accounts", "check_accounts"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    modules.add(node.module)
                continue

            package_parts = list(
                path.resolve().parent.relative_to(ROOT.resolve()).parts
            )
            keep_count = max(0, len(package_parts) - node.level + 1)
            base_parts = package_parts[:keep_count]
            if node.module:
                modules.add(".".join([*base_parts, *node.module.split(".")]))
            else:
                modules.update(
                    ".".join([*base_parts, alias.name]) for alias in node.names
                )
    return modules


def function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function not found: {name}")


def account_batch_loops(function: ast.FunctionDef) -> list[ast.AST]:
    nodes = list(_function_body_nodes(function))
    tainted_names = {"accounts"}
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
            if value is None or not _is_account_batch(value, tainted_names):
                continue
            new_names = assigned_names - tainted_names
            if new_names:
                tainted_names.update(new_names)
                changed = True

    prohibited: list[ast.AST] = []
    for node in nodes:
        if isinstance(node, (ast.For, ast.AsyncFor)):
            if _is_account_batch(node.iter, tainted_names):
                prohibited.append(node)
        elif isinstance(node, ast.comprehension):
            if _is_account_batch(node.iter, tainted_names):
                prohibited.append(node)
    return prohibited


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


def _is_account_batch(node: ast.AST, tainted_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted_names
    if isinstance(node, ast.Call):
        call_name = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        if call_name in SAFE_ACCOUNT_BATCH_TERMINALS:
            return False
        if isinstance(node.func, ast.Attribute) and _is_account_batch(
            node.func.value,
            tainted_names,
        ):
            return True
        return any(
            _is_account_batch(argument, tainted_names) for argument in node.args
        ) or any(
            _is_account_batch(keyword.value, tainted_names)
            for keyword in node.keywords
        )
    return any(
        _is_account_batch(child, tainted_names)
        for child in ast.iter_child_nodes(node)
    )


class ArchitectureTests(unittest.TestCase):
    def test_account_batch_loop_detection_catches_aliases_wrappers_and_comprehensions(self) -> None:
        sources = (
            (
                "list comprehension alias",
                "def entry(accounts):\n"
                "    alias = list(accounts)\n"
                "    return [mailbox for mailbox in alias]\n",
            ),
            (
                "enumerated loop alias",
                "def entry(accounts):\n"
                "    pending = accounts\n"
                "    for mailbox in enumerate(pending):\n"
                "        pass\n",
            ),
            (
                "set wrapper",
                "def entry(accounts):\n"
                "    pending = set(accounts)\n"
                "    for mailbox in pending:\n"
                "        pass\n",
            ),
            (
                "frozenset wrapper",
                "def entry(accounts):\n"
                "    pending = frozenset(accounts)\n"
                "    return [mailbox for mailbox in pending]\n",
            ),
            (
                "filter wrapper",
                "def entry(accounts):\n"
                "    pending = filter(None, accounts)\n"
                "    return tuple(mailbox for mailbox in pending)\n",
            ),
            (
                "custom wrapper",
                "def entry(accounts, wrap):\n"
                "    pending = wrap(accounts)\n"
                "    for mailbox in pending:\n"
                "        pass\n",
            ),
        )

        for name, source in sources:
            with self.subTest(name=name):
                function = ast.parse(source).body[0]
                self.assertEqual(len(account_batch_loops(function)), 1)

    def test_account_batch_loop_detection_does_not_taint_batch_service_results(self) -> None:
        function = ast.parse(
            "def entry(accounts, service):\n"
            "    results = service.fetch_accounts(accounts)\n"
            "    for result in results:\n"
            "        pass\n"
        ).body[0]

        self.assertEqual(account_batch_loops(function), [])

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

        self.assertEqual(imports, {"mail_receiver.imap_client"})

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
