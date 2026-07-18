from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GHCR_IMAGE = "ghcr.io/xiao-dan-1/outlook-mail-fetcher:latest"


def markdown_h2_section(markdown: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        markdown,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"README section not found: {title}")
    return match.group("body")


def workflow_job(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\s*$\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"workflow job not found: {name}")
    return match.group("body")


class DockerDeploymentTests(unittest.TestCase):
    def read_root_file(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_dockerfile_runs_web_ui_without_account_file(self) -> None:
        dockerfile = self.read_root_file("Dockerfile")

        self.assertIn("ARG PYTHON_IMAGE=python:3.11-slim", dockerfile)
        self.assertIn("FROM ${PYTHON_IMAGE}", dockerfile)
        self.assertIn("python:3.11-slim", dockerfile)
        self.assertIn("WORKDIR /app", dockerfile)
        self.assertIn("USER appuser", dockerfile)
        self.assertIn("EXPOSE 8765", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn('"mail_receiver.web"', dockerfile)
        self.assertIn('"--host"', dockerfile)
        self.assertIn('"0.0.0.0"', dockerfile)
        self.assertIn('"--port"', dockerfile)
        self.assertIn('"8765"', dockerfile)
        self.assertNotIn("--account-file", dockerfile)
        self.assertNotRegex(dockerfile, re.compile(r"order_\d+\.txt", re.IGNORECASE))

    def test_compose_uses_prebuilt_ghcr_image_without_account_mount(self) -> None:
        compose = self.read_root_file("docker-compose.yml")

        self.assertIn("services:", compose)
        self.assertIn("outlook-mail-fetcher:", compose)
        self.assertIn(f"image: {GHCR_IMAGE}", compose)
        self.assertIn('"8765:8765"', compose)
        self.assertIn("restart: unless-stopped", compose)
        self.assertIn("init: true", compose)
        self.assertNotIn("build:", compose)
        self.assertNotIn("APP_PORT", compose)
        self.assertNotIn("--account-file", compose)
        self.assertNotIn("ACCOUNT_FILE", compose)
        self.assertNotIn("volumes:", compose)
        self.assertNotRegex(compose, re.compile(r"order_\d+\.txt", re.IGNORECASE))

    def test_local_build_override_keeps_build_configuration_out_of_default_compose(self) -> None:
        override = self.read_root_file("docker-compose.build.yml")

        self.assertIn("outlook-mail-fetcher:", override)
        self.assertIn("build:", override)
        self.assertIn("PYTHON_IMAGE: python:3.11-slim", override)
        self.assertIn("image: outlook-mail-fetcher:local", override)
        self.assertNotIn("--account-file", override)
        self.assertNotIn("ACCOUNT_FILE", override)

    def test_github_actions_publishes_prebuilt_image_to_ghcr(self) -> None:
        workflow = self.read_root_file(".github/workflows/docker-image.yml")
        build_job = workflow_job(workflow, "build")

        self.assertIn("contents: read", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("docker/setup-buildx-action@v3", build_job)
        self.assertIn("docker/login-action", build_job)
        self.assertIn("if: github.event_name != 'pull_request'", build_job)
        self.assertIn("registry: ghcr.io", build_job)
        self.assertIn("docker/metadata-action@v5", build_job)
        self.assertIn("docker/build-push-action", build_job)
        self.assertIn("context: .", build_job)
        self.assertIn("file: ./Dockerfile", build_job)
        self.assertIn("push: ${{ github.event_name != 'pull_request' }}", build_job)
        self.assertIn("images: ghcr.io/${{ github.repository }}", build_job)
        self.assertIn("type=raw,value=latest", build_job)
        self.assertIn("tags: ${{ steps.meta.outputs.tags }}", build_job)
        self.assertIn("labels: ${{ steps.meta.outputs.labels }}", build_job)

    def test_github_actions_runs_python_and_node_tests_before_docker_build(self) -> None:
        workflow = self.read_root_file(".github/workflows/docker-image.yml")
        test_job = workflow_job(workflow, "test")
        build_job = workflow_job(workflow, "build")

        self.assertLess(workflow.index("  test:"), workflow.index("  build:"))
        self.assertIn("runs-on: ubuntu-latest", test_job)
        self.assertIn("actions/checkout@v4", test_job)
        self.assertIn("actions/setup-python@v5", test_job)
        self.assertRegex(test_job, re.compile(r"python-version:\s*['\"]?3\.11['\"]?"))
        self.assertIn("actions/setup-node@v4", test_job)
        self.assertRegex(test_job, re.compile(r"node-version:\s*['\"]?22['\"]?"))
        self.assertIn("run: python -m unittest discover -s tests", test_job)
        self.assertIn("run: node --test tests/*.test.js", test_job)
        self.assertRegex(build_job, re.compile(r"^\s+needs:\s*test\s*$", re.MULTILINE))

    def test_dockerignore_excludes_local_and_sensitive_files(self) -> None:
        dockerignore = self.read_root_file(".dockerignore")

        required_patterns = [
            ".git",
            "__pycache__/",
            "*.py[cod]",
            "*.sqlite3",
            "mail.sqlite3",
            ".env",
            "order_*.txt",
            "tests/",
        ]
        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, dockerignore)

    def test_readme_documents_docker_one_command_without_account_file(self) -> None:
        readme = self.read_root_file("README.md")

        self.assertIn("## Docker", readme)
        self.assertIn(GHCR_IMAGE, readme)
        self.assertIn("docker compose up -d", readme)
        self.assertIn("http://127.0.0.1:8765/", readme)
        docker_section = markdown_h2_section(readme, "Docker")
        self.assertIn('"9876:8765"', docker_section)
        self.assertIn("mail.sqlite3", docker_section)
        self.assertIn("docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build", docker_section)
        self.assertIn("GHCR", docker_section)
        self.assertIn("PYTHON_IMAGE", docker_section)
        self.assertNotIn("APP_PORT", docker_section)
        self.assertNotIn("$env:", docker_section)
        self.assertNotIn("--account-file", docker_section)
        self.assertNotIn("ACCOUNT_FILE", docker_section)
        self.assertNotRegex(docker_section, re.compile(r"order_\d+\.txt", re.IGNORECASE))

    def test_readme_documents_docker_update_commands(self) -> None:
        readme = self.read_root_file("README.md")
        docker_section = markdown_h2_section(readme, "Docker")

        self.assertIn("### Update", docker_section)
        self.assertIn("docker compose pull", docker_section)
        self.assertIn("docker compose pull && docker compose up -d", docker_section)
        self.assertIn("git pull", docker_section)
        self.assertIn("docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build", docker_section)

    def test_readme_uses_generic_account_file_names_for_public_repo(self) -> None:
        readme = self.read_root_file("README.md")

        self.assertNotRegex(readme, re.compile(r"order_\d+\.txt", re.IGNORECASE))
        self.assertIn("accounts.txt", readme)

    def test_readme_documents_cli_placement_raw_output_and_ci_gate(self) -> None:
        readme = self.read_root_file("README.md")

        self.assertIn("`--db` 和 `--debug` 可放在子命令前或后", readme)
        self.assertIn("`show --raw`", readme)
        self.assertIn("重定向", readme)
        self.assertIn("原始字节", readme)
        self.assertIn("Python 3.11", readme)
        self.assertIn("Node.js 22", readme)
        self.assertIn("测试通过后才构建 Docker 镜像", readme)


if __name__ == "__main__":
    unittest.main()
