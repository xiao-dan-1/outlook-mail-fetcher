import ast
import importlib
import inspect
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function not found: {name}")


class ArchitectureTests(unittest.TestCase):
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
                prohibited = [
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == "account"
                    and isinstance(node.iter, ast.Name)
                    and node.iter.id == "accounts"
                ]
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
