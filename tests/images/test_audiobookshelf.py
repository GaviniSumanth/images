import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from container_test_common import (
    check_image_contract,
    container_name,
    docker_client,
    managed_container,
    published_port,
    wait_for_container,
)
from image_contract import EXPECTED_PORTS


IMAGE = os.environ.get("TEST_IMAGE")
TEST_SCRIPT = Path(__file__).with_name("assets").joinpath(
    "test-ffmpeg-runtime.cjs"
).resolve()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(IMAGE is None, reason="TEST_IMAGE is not set"),
]


def test_image_contract():
    check_image_contract(IMAGE, EXPECTED_PORTS["audiobookshelf"])


def test_ffmpeg_runtime():
    docker_client().containers.run(
        IMAGE,
        command=["/tests/test-ffmpeg-runtime.cjs"],
        entrypoint="node",
        remove=True,
        tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m,uid=1000,gid=1000"},
        volumes={
            str(TEST_SCRIPT): {
                "bind": "/tests/test-ffmpeg-runtime.cjs",
                "mode": "ro",
            }
        },
    )


def test_nusqlite_library_is_present():
    script = (
        "const fs=require('node:fs');"
        "const path=process.env.NUSQLITE3_PATH;"
        "if (!path || !fs.existsSync(path)) { console.error('missing ' + path); process.exit(1); }"
        "if (fs.statSync(path).size === 0) { console.error('empty ' + path); process.exit(1); }"
    )
    docker_client().containers.run(IMAGE, command=["node", "-e", script], remove=True)


def test_container_becomes_ready():
    name = container_name("audiobookshelf")
    container = docker_client().containers.run(
        IMAGE,
        detach=True,
        name=name,
        ports={"8000/tcp": ("127.0.0.1", None)},
    )
    with managed_container(container):
        health_url = f"http://127.0.0.1:{published_port(container, 8000)}/healthcheck"

        def is_ready(_running_container):
            try:
                with urlopen(health_url, timeout=5) as response:
                    return response.status == 200
            except (URLError, TimeoutError, ConnectionError):
                return False

        wait_for_container(container, is_ready)
