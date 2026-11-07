#!/usr/bin/env python3
"""Verify that each release points at an exact upstream tag."""

import subprocess
import sys

from release_config import (
    ReleaseConfigError,
    load_repositories,
)

TIMEOUT_SECONDS = 60


class UpstreamError(Exception):
    """Raised when an upstream repository or tag cannot be verified."""


def validate_tag(
    entry: dict,
    runner=subprocess.run,
    timeout: int = TIMEOUT_SECONDS,
) -> None:
    """Verify one upstream tag, distinguishing a missing tag from an unreachable remote."""
    repository = entry["repository"]
    version = entry["version"]

    try:
        result = runner(
            [
                "git",
                "ls-remote",
                "--tags",
                "--refs",
                repository,
                f"refs/tags/{version}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise UpstreamError(
            f"Timed out after {timeout}s while checking {repository} for tag {version}"
        ) from error
    except OSError as error:
        raise UpstreamError(f"Unable to run git while checking {repository}: {error}") from error

    if result.returncode != 0:
        details = (result.stderr or "").strip() or f"exit code {result.returncode}"
        raise UpstreamError(f"Unable to reach {repository}: {details}")

    if not result.stdout.strip():
        raise UpstreamError(f"Tag {version} does not exist in {repository}")


def select_entries(images: list[str]) -> list[dict]:
    repositories = load_repositories()
    if not images:
        return repositories

    by_image = {entry["image"]: entry for entry in repositories}
    unknown = sorted(set(images) - set(by_image))
    if unknown:
        raise UpstreamError(f"Unknown image(s): {', '.join(unknown)}")

    return [by_image[image] for image in images]


def main() -> None:
    try:
        for entry in select_entries(sys.argv[1:]):
            validate_tag(entry)
            print(f"Verified {entry['repository']} tag {entry['version']}")
    except (KeyError, ReleaseConfigError, UpstreamError) as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
