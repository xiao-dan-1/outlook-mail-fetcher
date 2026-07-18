from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any
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


def _yaml_scalar(value: str) -> Any:
    if value.startswith(('"', "'")):
        return ast.literal_eval(value)
    if value == "true":
        return True
    if value == "false":
        return False
    if value in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _yaml_pair(text: str) -> tuple[str, str]:
    match = re.fullmatch(r"([^:]+):(.*)", text)
    if match is None:
        raise AssertionError(f"unsupported YAML entry: {text}")
    return match.group(1).strip(), match.group(2).strip()


def _yaml_value(
    lines: list[tuple[int, str, str]],
    index: int,
    parent_indent: int,
    value: str,
) -> tuple[Any, int]:
    if value == "|":
        block: list[str] = []
        block_indent = lines[index][0] if index < len(lines) else parent_indent + 2
        while index < len(lines) and lines[index][0] > parent_indent:
            block.append(lines[index][2][block_indent:])
            index += 1
        return "\n".join(block), index
    if value:
        return _yaml_scalar(value), index
    if index < len(lines) and lines[index][0] > parent_indent:
        return _yaml_block(lines, index, lines[index][0])
    return {}, index


def _yaml_mapping(
    lines: list[tuple[int, str, str]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text, _raw = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        key, value = _yaml_pair(text)
        index += 1
        result[key], index = _yaml_value(lines, index, indent, value)
    return result, index


def _yaml_sequence(
    lines: list[tuple[int, str, str]], index: int, indent: int
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line_indent, text, _raw = lines[index]
        if line_indent != indent or not text.startswith("- "):
            break
        item = text[2:].strip()
        index += 1
        if ":" not in item:
            result.append(_yaml_scalar(item))
            continue

        key, value = _yaml_pair(item)
        item_indent = indent + 2
        mapping: dict[str, Any] = {}
        mapping[key], index = _yaml_value(lines, index, item_indent, value)
        if index < len(lines) and lines[index][0] == item_indent:
            remainder, index = _yaml_mapping(lines, index, item_indent)
            mapping.update(remainder)
        result.append(mapping)
    return result, index


def _yaml_block(
    lines: list[tuple[int, str, str]], index: int, indent: int
) -> tuple[Any, int]:
    if lines[index][1].startswith("- "):
        return _yaml_sequence(lines, index, indent)
    return _yaml_mapping(lines, index, indent)


def parse_workflow_yaml(workflow: str) -> dict[str, Any]:
    lines: list[tuple[int, str, str]] = []
    for raw in workflow.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            raise AssertionError("workflow YAML must not use tabs for indentation")
        lines.append((indent, raw[indent:], raw))
    if not lines:
        raise AssertionError("workflow YAML is empty")
    parsed, index = _yaml_block(lines, 0, lines[0][0])
    if index != len(lines) or not isinstance(parsed, dict):
        raise AssertionError("workflow YAML did not parse as one mapping")
    return parsed


def workflow_step(job: dict[str, Any], action: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("uses") == action]
    if len(matches) != 1:
        raise AssertionError(f"expected one {action} step, found {len(matches)}")
    return matches[0]


def job_runs_for_event(job: dict[str, Any], event_name: str) -> bool:
    condition = job.get("if")
    if condition is None:
        return True
    if condition == "github.event_name == 'pull_request'":
        return event_name == "pull_request"
    if condition == "github.event_name != 'pull_request'":
        return event_name != "pull_request"
    raise AssertionError(f"unsupported job condition: {condition}")


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

    def test_github_actions_limits_package_write_permission_to_publish_job(self) -> None:
        workflow = parse_workflow_yaml(
            self.read_root_file(".github/workflows/docker-image.yml")
        )
        jobs = workflow["jobs"]

        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(list(jobs), ["test", "build", "publish"])
        self.assertNotIn("permissions", jobs["test"])
        self.assertNotIn("permissions", jobs["build"])
        self.assertEqual(
            jobs["publish"]["permissions"],
            {"contents": "read", "packages": "write"},
        )
        login_jobs = [
            name
            for name, job in jobs.items()
            if any(step.get("uses") == "docker/login-action@v3" for step in job["steps"])
        ]
        self.assertEqual(login_jobs, ["publish"])

    def test_github_actions_tests_then_runs_one_image_job_for_each_event(self) -> None:
        workflow = parse_workflow_yaml(
            self.read_root_file(".github/workflows/docker-image.yml")
        )
        jobs = workflow["jobs"]
        self.assertIn("publish", jobs)
        test_job = jobs["test"]
        build_job = jobs["build"]
        publish_job = jobs["publish"]

        self.assertEqual(
            workflow["on"],
            {
                "push": {
                    "branches": ["main", "master"],
                    "tags": ["v*.*.*"],
                },
                "pull_request": {"branches": ["main", "master"]},
                "workflow_dispatch": {},
            },
        )

        self.assertEqual(test_job["runs-on"], "ubuntu-latest")
        self.assertEqual(
            [step.get("uses") for step in test_job["steps"] if "uses" in step],
            [
                "actions/checkout@v4",
                "actions/setup-python@v5",
                "actions/setup-node@v4",
            ],
        )
        self.assertEqual(test_job["steps"][1]["with"]["python-version"], "3.11")
        self.assertEqual(test_job["steps"][2]["with"]["node-version"], "22")
        self.assertEqual(
            [step["run"] for step in test_job["steps"] if "run" in step],
            [
                "python -m unittest discover -s tests",
                "node --test tests/*.test.js",
            ],
        )
        self.assertEqual(build_job["needs"], "test")
        self.assertEqual(publish_job["needs"], "test")
        self.assertEqual(build_job["if"], "github.event_name == 'pull_request'")
        self.assertEqual(publish_job["if"], "github.event_name != 'pull_request'")

        for event_name, expected_job in (
            ("pull_request", "build"),
            ("push", "publish"),
            ("workflow_dispatch", "publish"),
        ):
            with self.subTest(event_name=event_name):
                selected = [
                    name
                    for name in ("build", "publish")
                    if job_runs_for_event(jobs[name], event_name)
                ]
                self.assertEqual(selected, [expected_job])

        self.assertFalse(
            workflow_step(build_job, "docker/build-push-action@v6")["with"]["push"]
        )
        publish_push = workflow_step(
            publish_job, "docker/build-push-action@v6"
        )["with"]["push"]
        self.assertIn(
            publish_push,
            (True, "${{ github.event_name != 'pull_request' }}"),
        )

    def test_github_actions_preserves_docker_build_and_publish_steps(self) -> None:
        workflow = parse_workflow_yaml(
            self.read_root_file(".github/workflows/docker-image.yml")
        )
        jobs = workflow["jobs"]
        self.assertIn("publish", jobs)
        build_job = jobs["build"]
        publish_job = jobs["publish"]

        self.assertEqual(
            [step.get("uses") for step in build_job["steps"]],
            [
                "actions/checkout@v4",
                "docker/setup-buildx-action@v3",
                "docker/metadata-action@v5",
                "docker/build-push-action@v6",
            ],
        )
        self.assertEqual(
            [step.get("uses") for step in publish_job["steps"]],
            [
                "actions/checkout@v4",
                "docker/setup-buildx-action@v3",
                "docker/login-action@v3",
                "docker/metadata-action@v5",
                "docker/build-push-action@v6",
            ],
        )
        login = workflow_step(publish_job, "docker/login-action@v3")
        self.assertEqual(login["if"], "github.event_name != 'pull_request'")
        self.assertEqual(login["with"]["registry"], "ghcr.io")
        self.assertEqual(login["with"]["username"], "${{ github.actor }}")
        self.assertEqual(login["with"]["password"], "${{ secrets.GITHUB_TOKEN }}")

        for job_name in ("build", "publish"):
            with self.subTest(job=job_name):
                metadata = workflow_step(jobs[job_name], "docker/metadata-action@v5")
                image_build = workflow_step(
                    jobs[job_name], "docker/build-push-action@v6"
                )
                self.assertEqual(
                    metadata["with"]["images"],
                    "ghcr.io/${{ github.repository }}",
                )
                self.assertIn("type=raw,value=latest", metadata["with"]["tags"])
                self.assertEqual(image_build["with"]["context"], ".")
                self.assertEqual(image_build["with"]["file"], "./Dockerfile")
                self.assertEqual(
                    image_build["with"]["tags"], "${{ steps.meta.outputs.tags }}"
                )
                self.assertEqual(
                    image_build["with"]["labels"],
                    "${{ steps.meta.outputs.labels }}",
                )

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
        self.assertIn("mail_store.sqlite3", docker_section)
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
        self.assertIn("测试通过后才构建或发布 Docker 镜像", readme)


if __name__ == "__main__":
    unittest.main()
