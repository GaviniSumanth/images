#!/usr/bin/env python3
"""Validate that an image has the files required to run its tests."""

import sys
from pathlib import Path

from release_config import IMAGE_PATTERN, image_test_file

REPO_ROOT = Path(__file__).resolve().parents[2]


class ValidationError(Exception):
    """Raised when the test configuration is incomplete."""


def integration_test_file(image: str) -> Path:
    """Return the integration test path for an image."""
    return REPO_ROOT / "tests" / "images" / image_test_file(image)


def validate_test_config(image: str) -> None:
    if not IMAGE_PATTERN.fullmatch(image):
        raise ValidationError(f"Invalid image name: {image!r}")

    test_file = integration_test_file(image)
    requirements_file = REPO_ROOT / "tests" / "requirements-test.txt"

    if not test_file.is_file():
        raise ValidationError(
            f"Missing pytest entrypoint: {test_file.relative_to(REPO_ROOT)}"
        )

    if not requirements_file.is_file():
        raise ValidationError("Missing test requirements: tests/requirements-test.txt")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: validate_test_config.py IMAGE", file=sys.stderr)
        sys.exit(2)

    try:
        validate_test_config(sys.argv[1])
    except ValidationError as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
