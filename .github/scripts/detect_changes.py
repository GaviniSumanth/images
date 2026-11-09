#!/usr/bin/env python3
"""Calculate build and verification matrices for changed releases."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from release_config import (
    ReleaseConfigError,
    github_slug,
    load_repositories,
    repositories_from_data,
    image_test_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
FULL_REBUILD = "__full_rebuild__"
WORKFLOW_FILES = {
    ".github/workflows/build-container.yml",
    ".github/workflows/container-pipeline.yml",
}
SHARED_VERIFY_PATHS = {
    "pyproject.toml",
    "tests/image_contract.py",
    "tests/requirements-test.txt",
}


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or f"exit code {result.returncode}"
        raise ReleaseConfigError(f"git {' '.join(args)} failed: {details}")

    return result.stdout


def parse_config(data: object) -> list[dict]:
    repositories = repositories_from_data(data)
    if not isinstance(repositories, list):
        return []

    return [entry for entry in repositories if isinstance(entry, dict)]


def revision_exists(revision: str, cwd: Path = REPO_ROOT) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=cwd,
        capture_output=True,
    )
    return result.returncode == 0


def load_previous_releases(before: str, cwd: Path = REPO_ROOT) -> list[dict]:
    if not SHA_PATTERN.fullmatch(before) or before == ZERO_SHA:
        return []

    try:
        data = json.loads(git("show", f"{before}:releases.json", cwd=cwd))
    except (ReleaseConfigError, json.JSONDecodeError):
        return []

    return parse_config(data)


def changed_files(before: str, current: str, cwd: Path = REPO_ROOT) -> list[str]:
    current = current or "HEAD"
    if current != "HEAD" and (
        not SHA_PATTERN.fullmatch(current) or not revision_exists(current, cwd)
    ):
        raise ReleaseConfigError(f"Current revision does not exist: {current!r}")

    if (
        not SHA_PATTERN.fullmatch(before)
        or before == ZERO_SHA
        or not revision_exists(before, cwd)
    ):
        return [FULL_REBUILD]

    output = git("diff", "--name-only", "-z", before, current, "--", cwd=cwd)
    return [path for path in output.split("\0") if path]


def previous_for(previous_repositories: list[dict], repository: object) -> dict | None:
    for entry in previous_repositories:
        if entry.get("repository") == repository:
            return entry

    return None


def build_required(entry: dict, previous: dict | None, changed: list[str]) -> bool:
    if FULL_REBUILD in changed or previous is None:
        return True

    if any(
        previous.get(field) != entry.get(field)
        for field in ("version", "containerfile", "image", "metadata")
    ):
        return True

    containerfiles = {entry["containerfile"]}
    if previous.get("containerfile"):
        containerfiles.add(previous["containerfile"])

    asset_prefixes = (
        f"{entry['image']}/assets/",
        f"images/{entry['image']}/assets/",
    )
    return any(
        path in (containerfile, f"{containerfile}.dockerignore")
        or path.startswith(asset_prefixes)
        for containerfile in containerfiles
        for path in changed
    )


def verify_required(
    entry: dict, changed: list[str], all_test_files: set[str]
) -> bool:
    if FULL_REBUILD in changed:
        return False

    test_file = f"tests/images/{image_test_file(entry['image'])}"
    for path in changed:
        if path == test_file:
            return True
        if path in SHARED_VERIFY_PATHS:
            return True
        if path.startswith(".github/scripts/") or path in WORKFLOW_FILES:
            return True
        if path.startswith("tests/images/") and path not in all_test_files:
            return True

    return False


PREBUILD_TEST_FALLBACK = "tests/containerfiles/test_prebuild.py"


def prebuild_test_file(image: str, root: Path = REPO_ROOT) -> str:
    """Return the most specific pre-build test file for an image."""
    specific = f"tests/containerfiles/test_{image.replace('-', '_')}_prebuild.py"
    if (Path(root) / specific).is_file():
        return specific

    return PREBUILD_TEST_FALLBACK


def matrix_entry(entry: dict, root: Path = REPO_ROOT) -> dict:
    return {
        "repo": github_slug(entry["repository"]),
        "repository": entry["repository"],
        "tag": entry["version"],
        "containerfile": entry["containerfile"],
        "image": entry["image"],
        "metadata": entry["metadata"],
        "test_file": f"tests/images/{image_test_file(entry['image'])}",
        "prebuild_test": prebuild_test_file(entry["image"], root),
    }


def matrices_for(
    repositories: list[dict],
    previous: list[dict],
    changed: list[str],
    root: Path = REPO_ROOT,
) -> dict[str, list[dict]]:
    build = []
    for entry in repositories:
        if build_required(entry, previous_for(previous, entry["repository"]), changed):
            build.append(matrix_entry(entry, root))

    build_images = {entry["image"] for entry in build}
    all_test_files = {
        f"tests/images/{image_test_file(entry['image'])}" for entry in repositories
    }

    verify = []
    for entry in repositories:
        if entry["image"] in build_images:
            continue
        if verify_required(entry, changed, all_test_files):
            verify.append(matrix_entry(entry, root))

    return {"build": build, "verify": verify}


def build_matrices(
    before: str, current: str, cwd: Path = REPO_ROOT
) -> dict[str, list[dict]]:
    previous = load_previous_releases(before, cwd)
    changed = changed_files(before, current, cwd)
    repositories = load_repositories(Path(cwd) / "releases.json")
    return matrices_for(repositories, previous, changed, Path(cwd))


def write_output(path: str, name: str, value: str) -> None:
    with open(path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def main() -> None:
    before = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BEFORE", "")
    current = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("CURRENT", "")

    try:
        matrices = build_matrices(before, current)
        build = json.dumps(matrices["build"], separators=(",", ":"))
        verify = json.dumps(matrices["verify"], separators=(",", ":"))
    except (KeyError, OSError, ReleaseConfigError, TypeError) as error:
        print(f"::error::Unable to determine changed releases: {error}")
        sys.exit(1)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        write_output(output_path, "build_matrix", build)
        write_output(output_path, "verify_matrix", verify)
    else:
        print(f"build_matrix={build}")
        print(f"verify_matrix={verify}")

    print(f"Build matrix: {build}")
    print(f"Verify matrix: {verify}")


if __name__ == "__main__":
    main()
