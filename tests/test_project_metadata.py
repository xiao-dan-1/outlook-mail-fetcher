from __future__ import annotations

from pathlib import Path
import re
import unittest

import mail_receiver


ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def read_root_file(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_repository_declares_mit_license_file(self) -> None:
        license_text = self.read_root_file("LICENSE")

        self.assertTrue(license_text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 xiao-dan-1", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn("THE SOFTWARE IS PROVIDED \"AS IS\"", license_text)

    def test_readme_links_license_section(self) -> None:
        readme = self.read_root_file("README.md")

        self.assertRegex(readme, re.compile(r"^## License\s+MIT License", re.MULTILINE))
        self.assertIn("[MIT License](LICENSE)", readme)

    def test_package_declares_semantic_version(self) -> None:
        version = getattr(mail_receiver, "__version__", None)

        self.assertIsNotNone(version)
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

        init_file = self.read_root_file("mail_receiver/__init__.py")
        self.assertIn("__version__", init_file)

    def test_readme_documents_project_versioning(self) -> None:
        readme = self.read_root_file("README.md")

        self.assertRegex(readme, re.compile(r"当前版本：`\d+\.\d+\.\d+`"))
        self.assertIn("git tag v", readme)
        self.assertIn("GHCR", readme)

    def test_readme_has_concise_public_project_structure(self) -> None:
        readme = self.read_root_file("README.md")

        expected_sections = [
            "# Outlook Mail Fetcher",
            "## Features",
            "## Account Format",
            "## Quick Start",
            "## Docker",
            "## CLI",
            "## Data and Privacy",
            "## Development",
            "## License",
        ]
        last_index = -1
        for section in expected_sections:
            with self.subTest(section=section):
                index = readme.find(section)
                self.assertGreater(index, last_index)
                last_index = index

        self.assertNotIn("本次界面变更摘要", readme)
        self.assertNotIn("Outlook 邮件调试台", readme.splitlines()[0])
        self.assertLessEqual(len(readme.splitlines()), 140)


if __name__ == "__main__":
    unittest.main()
