#!/usr/bin/env python3
"""Load a tested OCI image archive into the local Docker daemon."""

import os
import subprocess
import sys

from release_config import ReleaseConfigError, required_env


def load_image(
    oci_archive: str,
    image: str,
    docker_archive: str | None = None,
    runner=subprocess.run,
) -> str:
    """Convert an OCI archive to a docker archive and load it."""
    docker_archive = docker_archive or f"{oci_archive}.docker.tar"

    runner(
        [
            "skopeo",
            "copy",
            "--multi-arch",
            "system",
            f"oci-archive:{oci_archive}",
            f"docker-archive:{docker_archive}:{image}",
        ],
        check=True,
        timeout=600,
    )
    runner(
        ["docker", "load", "-i", docker_archive],
        check=True,
        timeout=600,
    )
    runner(
        ["docker", "image", "inspect", image],
        check=True,
        capture_output=True,
        timeout=60,
    )

    return docker_archive


def main() -> None:
    try:
        load_image(
            required_env("OCI_ARCHIVE"),
            required_env("TEST_IMAGE"),
            os.environ.get("DOCKER_ARCHIVE"),
        )
    except (ReleaseConfigError, OSError, subprocess.SubprocessError) as error:
        print(f"::error::Unable to load image archive: {error}")
        sys.exit(1)

    print(f"Loaded {os.environ['TEST_IMAGE']}")


if __name__ == "__main__":
    main()
