from __future__ import annotations

from pathlib import Path
import re
import unittest


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


if __name__ == "__main__":
    unittest.main()
