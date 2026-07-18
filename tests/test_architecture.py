import ast
import importlib
import inspect
from pathlib import Path
from tempfile import NamedTemporaryFile
import unittest


ROOT = Path(__file__).resolve().parents[1]


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


def loop_nodes(function: ast.FunctionDef) -> list[ast.AST]:
    loop_types = (
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )
    return [node for node in ast.walk(function) if isinstance(node, loop_types)]


class ArchitectureTests(unittest.TestCase):
    def test_loop_nodes_detects_while_statements(self) -> None:
        function = ast.parse(
            "def entry(accounts):\n"
            "    while accounts:\n"
            "        accounts.pop()\n"
        ).body[0]

        loops = loop_nodes(function)

        self.assertEqual(len(loops), 1)
        self.assertIsInstance(loops[0], ast.While)

    def test_batch_entrypoints_contain_no_loops(self) -> None:
        entrypoints = (
            (ROOT / "mail_receiver" / "web.py", "check_accounts_data"),
            (ROOT / "mail_receiver" / "cli.py", "fetch"),
        )

        for path, function_name in entrypoints:
            with self.subTest(path=path.name, function=function_name):
                function = function_node(path, function_name)
                self.assertEqual(loop_nodes(function), [])

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

    def test_batch_entrypoints_compose_application_services(self) -> None:
        entrypoints = (
            (
                ROOT / "mail_receiver" / "web.py",
                "check_accounts_data",
                "BatchCheckService",
                "check_accounts",
            ),
            (
                ROOT / "mail_receiver" / "cli.py",
                "fetch",
                "BatchFetchService",
                "fetch_accounts",
            ),
        )

        for path, function_name, expected_service, expected_method in entrypoints:
            with self.subTest(path=path.name, function=function_name):
                function = function_node(path, function_name)
                called_names = {
                    node.func.id
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                called_attributes = {
                    node.func.attr
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                }
                self.assertIn(expected_service, called_names)
                self.assertIn(expected_method, called_attributes)


if __name__ == "__main__":
    unittest.main()
