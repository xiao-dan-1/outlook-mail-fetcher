import ast
import importlib
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


class ArchitectureTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
