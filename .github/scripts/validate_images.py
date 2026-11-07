#!/usr/bin/env python3
"""Validate image Containerfiles, test files, and build-context ignores."""

import sys
from pathlib import Path

from release_config import (
    CONTAINERFILE_PATTERN,
    IMAGE_PATTERN,
    VERSION_PATTERN,
    ReleaseConfigError,
    github_slug,
    load_repositories,
)
from validate_test_config import ValidationError, validate_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def validate_images() -> None:
    if (REPO_ROOT / "_shared").exists():
        raise ValidationError("_shared/ must not exist; all tests live under tests/")

    for entry in load_repositories():
        try:
            image = entry["image"]
            containerfile = entry["containerfile"]
            repository = entry["repository"]
            version = entry["version"]
        except KeyError as error:
            raise ValidationError(f"Missing required field: {error.args[0]}") from error

        if not all(
            isinstance(value, str)
            for value in (image, containerfile, repository, version)
        ):
            raise ValidationError(
                "image, containerfile, repository, and version must be strings"
            )

        if not IMAGE_PATTERN.fullmatch(image):
            raise ValidationError(f"Invalid image name: {image!r}")
        if not CONTAINERFILE_PATTERN.fullmatch(containerfile):
            raise ValidationError(f"Invalid Containerfile path: {containerfile!r}")
        if not VERSION_PATTERN.fullmatch(version):
            raise ValidationError(f"Invalid version: {version!r}")
        try:
            github_slug(repository)
        except ReleaseConfigError as error:
            raise ValidationError(str(error)) from error

        containerfile_path = (REPO_ROOT / containerfile).resolve()
        if not containerfile_path.is_relative_to(REPO_ROOT):
            raise ValidationError(
                f"Containerfile must be inside the repository: {containerfile}"
            )

        if containerfile_path.parent.name != image:
            raise ValidationError(
                f"Containerfile directory must match image name: {containerfile}"
            )

        if not containerfile_path.is_file():
            raise ValidationError(f"Missing Containerfile: {containerfile}")

        ignorefile = containerfile_path.with_name(
            f"{containerfile_path.name}.dockerignore"
        )
        if not ignorefile.is_file():
            raise ValidationError(
                f"Missing build-context ignore file: {ignorefile.relative_to(REPO_ROOT)}"
            )

        validate_test_config(image)


def main() -> None:
    try:
        validate_images()
    except (ReleaseConfigError, ValidationError) as error:
        print(f"::error::{error}")
        sys.exit(1)

    print("image configuration is valid")


if __name__ == "__main__":
    main()
