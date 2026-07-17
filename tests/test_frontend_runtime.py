import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is required for frontend behavior tests")
class FrontendRuntimeTests(unittest.TestCase):
    def assert_node_test_passes(self, test_file: str) -> None:
        result = subprocess.run(
            [NODE, "--test", test_file],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_fetch_failure_runtime(self) -> None:
        self.assert_node_test_passes("tests/frontend_fetch_failure_runtime.test.js")

    def test_message_selection_runtime(self) -> None:
        self.assert_node_test_passes("tests/frontend_message_selection.test.js")

    def test_mail_list_aria_runtime(self) -> None:
        self.assert_node_test_passes("tests/frontend_mail_list_aria_runtime.test.js")

    def test_theme_runtime(self) -> None:
        self.assert_node_test_passes("tests/frontend_theme_runtime.test.js")

    def test_account_validation_runtime(self) -> None:
        self.assert_node_test_passes("tests/frontend_account_validation_runtime.test.js")


if __name__ == "__main__":
    unittest.main()
