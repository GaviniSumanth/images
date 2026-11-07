#!/usr/bin/env python3
"""Stage optional image assets into the upstream build context."""

import shutil
import sys
from pathlib import Path


class BuildContextError(Exception):
    """Raised when image assets cannot be staged safely."""


def stage_image_assets(build_context: Path, image_assets: Path) -> bool:
    """Copy an image's assets to container-assets in the build context."""
    build_context = build_context.resolve()
    image_assets = image_assets.resolve()

    if not build_context.is_dir():
        raise BuildContextError(f"Build context does not exist: {build_context}")
    if not image_assets.exists():
        return False
    if not image_assets.is_dir():
        raise BuildContextError(f"Image assets path is not a directory: {image_assets}")

    destination = build_context / "container-assets"
    if destination.exists():
        raise BuildContextError(
            f"Build context already contains the reserved path: {destination}"
        )

    for path in image_assets.rglob("*"):
        if path.is_symlink():
            raise BuildContextError(f"Image assets must not contain symlinks: {path}")

    try:
        shutil.copytree(image_assets, destination)
    except OSError as error:
        raise BuildContextError(
            f"Unable to stage image assets from {image_assets}: {error}"
        ) from error

    print(f"Staged image assets from {image_assets} into {destination}")
    return True


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "::error::Usage: prepare_build_context.py <build-context> <image-assets>"
        )
        sys.exit(1)

    try:
        stage_image_assets(Path(sys.argv[1]), Path(sys.argv[2]))
    except BuildContextError as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
