#!/usr/bin/env python3
"""Shared helpers for reading and validating releases.json."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASES_FILE = REPO_ROOT / "releases.json"

OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPOSITORY_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}")
IMAGE_PATTERN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
VERSION_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
CONTAINERFILE_PATTERN = re.compile(
    r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/Containerfile"
)
MAX_TAG_LENGTH = 128


class ReleaseConfigError(Exception):
    """Raised when releases.json cannot be read or contains invalid data."""


def required_env(name: str, error_type: type[Exception] = ReleaseConfigError) -> str:
    """Return a required environment variable or raise a typed error."""
    value = os.environ.get(name)
    if not value:
        raise error_type(f"Missing required environment variable: {name}")

    return value


def image_test_file(image: str) -> str:
    """Return the integration test filename for an image."""
    return f"test_{image.replace('-', '_')}.py"


def release_tag(version: str, run_number: str, run_attempt: str) -> str:
    """Return the immutable release tag for a workflow run."""
    if not run_number.isdigit() or not run_attempt.isdigit():
        raise ReleaseConfigError(
            "GITHUB_RUN_NUMBER and GITHUB_RUN_ATTEMPT must be numeric"
        )

    tag = f"{version}-{run_number}-{run_attempt}"
    if len(tag) > MAX_TAG_LENGTH:
        raise ReleaseConfigError(
            f"Release tag is longer than {MAX_TAG_LENGTH} characters: {tag}"
        )

    return tag


def repositories_from_data(data: object) -> list | None:
    """Return the repository list from a releases.json document."""
    if isinstance(data, dict):
        return data.get("repositories")

    if isinstance(data, list):
        return data

    return None


def load_repositories(path: Path = RELEASES_FILE) -> list[dict]:
    """Read releases.json and return its non-empty list of repository entries."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ReleaseConfigError(f"Unable to read {path.name}: {error}") from error
    except json.JSONDecodeError as error:
        raise ReleaseConfigError(f"Invalid JSON in {path.name}: {error}") from error

    repositories = repositories_from_data(data)
    if not isinstance(repositories, list) or not repositories:
        raise ReleaseConfigError(
            f"{path.name} must contain a non-empty repositories array"
        )

    if not all(isinstance(entry, dict) for entry in repositories):
        raise ReleaseConfigError(f"{path.name} entries must be objects")

    return repositories


def validate_repository_slug(value: object) -> str:
    """Return a validated GitHub owner/name slug."""
    if not isinstance(value, str):
        raise ReleaseConfigError("repository slug must be a string")

    parts = value.split("/")
    if len(parts) != 2:
        raise ReleaseConfigError("repository slug must contain an owner and a name")

    owner, name = parts
    if not OWNER_PATTERN.fullmatch(owner) or not REPOSITORY_NAME_PATTERN.fullmatch(name):
        raise ReleaseConfigError("repository owner or name is invalid")

    if name in (".", "..") or name.lower().endswith(".git"):
        raise ReleaseConfigError("repository name is ambiguous or invalid")

    return f"{owner}/{name}"


def github_slug(repository: object) -> str:
    """Return the owner/name slug for a GitHub HTTPS repository URL."""
    if not isinstance(repository, str):
        raise ReleaseConfigError("repository must be a string")

    parsed = urlparse(repository)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ReleaseConfigError("repository must use an https://github.com URL")

    if (
        parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ReleaseConfigError(
            "repository must not include credentials, parameters, a query, or a fragment"
        )

    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise ReleaseConfigError("repository must contain an owner and a name")

    return validate_repository_slug("/".join(parts))
