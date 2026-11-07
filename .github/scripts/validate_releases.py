#!/usr/bin/env python3
"""Validate the structure of releases.json."""

import sys

from release_config import (
    CONTAINERFILE_PATTERN,
    IMAGE_PATTERN,
    VERSION_PATTERN,
    ReleaseConfigError,
    github_slug,
    load_repositories,
)

ALLOWED_METADATA = {
    "org.opencontainers.image.title",
    "org.opencontainers.image.description",
    "org.opencontainers.image.url",
    "org.opencontainers.image.documentation",
    "org.opencontainers.image.licenses",
    "org.opencontainers.image.authors",
}

REQUIRED_METADATA = {
    "org.opencontainers.image.title",
    "org.opencontainers.image.description",
    "org.opencontainers.image.url",
    "org.opencontainers.image.documentation",
    "org.opencontainers.image.licenses",
}


class ValidationError(Exception):
    """Raised when releases.json does not match the expected structure."""


def fail(message: str) -> None:
    raise ValidationError(message)


def matches(value: object, pattern, label: str, entry: str) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(f"{entry}: invalid {label}: {value!r}")


def validate_metadata(metadata: object, entry: str) -> None:
    if not isinstance(metadata, dict):
        fail(f"{entry}: metadata must be an object")

    for key in REQUIRED_METADATA:
        value = metadata.get(key)
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            fail(f"{entry}: metadata {key} must be a non-empty single-line string")

    for key, value in metadata.items():
        if key not in ALLOWED_METADATA:
            fail(f"{entry}: metadata key is not allowed: {key}")
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            fail(f"{entry}: metadata {key} must be a non-empty single-line string")


def validate_entry(entry: object, index: int) -> None:
    label = f"repositories[{index}]"

    if not isinstance(entry, dict):
        fail(f"{label}: entry must be an object")

    try:
        github_slug(entry.get("repository"))
    except ReleaseConfigError as error:
        fail(f"{label}: {error}")

    matches(entry.get("version"), VERSION_PATTERN, "version", label)
    matches(entry.get("containerfile"), CONTAINERFILE_PATTERN, "containerfile", label)
    matches(entry.get("image"), IMAGE_PATTERN, "image", label)
    validate_metadata(entry.get("metadata"), label)


def validate_unique(repositories: list[dict]) -> None:
    images = [entry["image"] for entry in repositories]
    slugs = [github_slug(entry["repository"]).lower() for entry in repositories]

    if len(set(images)) != len(images):
        fail("releases.json contains duplicate image names")

    if len(set(slugs)) != len(slugs):
        fail("releases.json contains duplicate repositories")


def validate_repositories(repositories: list[dict]) -> None:
    for index, entry in enumerate(repositories):
        validate_entry(entry, index)

    validate_unique(repositories)


def main() -> None:
    try:
        validate_repositories(load_repositories())
    except (ReleaseConfigError, ValidationError) as error:
        print(f"::error::{error}")
        sys.exit(1)

    print("releases.json is valid")


if __name__ == "__main__":
    main()
