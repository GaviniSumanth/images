#!/usr/bin/env python3
"""Write image names and immutable release tags to the GitHub Actions outputs."""

import sys

from release_config import (
    IMAGE_PATTERN,
    OWNER_PATTERN,
    ReleaseConfigError,
    VERSION_PATTERN,
    release_tag,
    required_env,
)


def image_names(owner: str, image: str, version: str, run_number: str, run_attempt: str) -> dict:
    """Return the image, tag, alias, and artifact names for one release."""
    owner = owner.strip().lower()

    if not OWNER_PATTERN.fullmatch(owner):
        raise ReleaseConfigError(f"Invalid owner: {owner!r}")

    if not IMAGE_PATTERN.fullmatch(image):
        raise ReleaseConfigError(f"Invalid image name: {image!r}")

    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseConfigError(f"Invalid version: {version!r}")

    return {
        "name": f"ghcr.io/{owner}/{image}",
        "release_tag": release_tag(version, run_number, run_attempt),
        "alias": version,
        "artifact": f"image-{image}",
    }


def write_outputs(path: str, values: dict) -> None:
    """Append key=value pairs to a GitHub Actions output file."""
    with open(path, "a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: set_image_names.py OWNER IMAGE VERSION", file=sys.stderr)
        sys.exit(2)

    try:
        values = image_names(
            sys.argv[1],
            sys.argv[2],
            sys.argv[3],
            required_env("GITHUB_RUN_NUMBER"),
            required_env("GITHUB_RUN_ATTEMPT"),
        )
        write_outputs(required_env("GITHUB_OUTPUT"), values)
    except (OSError, ReleaseConfigError) as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
