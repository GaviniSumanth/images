import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def upstream_source():
    value = os.environ.get("UPSTREAM_SOURCE")
    if not value:
        pytest.skip("UPSTREAM_SOURCE is not set")

    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"Upstream source directory is missing: {path}")

    return path


@pytest.fixture(scope="session")
def upstream_dockerfile():
    value = os.environ.get("UPSTREAM_DOCKERFILE")
    if not value:
        pytest.skip("UPSTREAM_DOCKERFILE is not set")

    path = Path(value)
    if not path.is_file():
        pytest.fail(f"Upstream Dockerfile is missing: {path}")

    return path
