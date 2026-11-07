import os
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
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

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(IMAGE is None, reason="TEST_IMAGE is not set"),
]


def wait_for_web_ui(container):
    web_ui_url = f"http://127.0.0.1:{published_port(container, 8080)}/"

    def is_ready(_container):
        try:
            with urlopen(web_ui_url, timeout=5) as response:
                return response.status == 200 and bool(response.read())
        except HTTPError as error:
            return error.code == 401 and error.read() == b"Unauthorized"
        except (URLError, TimeoutError, ConnectionError):
            return False

    wait_for_container(container, is_ready)


def test_image_contract():
    check_image_contract(IMAGE, EXPECTED_PORTS["qbittorrent"])
    exposed_ports = (
        docker_client().images.get(IMAGE).attrs["Config"].get("ExposedPorts") or {}
    )
    assert "6881/udp" in exposed_ports


def test_web_ui_becomes_ready_and_seeds_default_config():
    with tempfile.TemporaryDirectory() as config_dir:
        os.chmod(config_dir, 0o777)
        config_file = (
            Path(config_dir) / "qBittorrent" / "config" / "qBittorrent.conf"
        )
        container = docker_client().containers.run(
            IMAGE,
            detach=True,
            name=container_name("qbittorrent"),
            ports={"8080/tcp": ("127.0.0.1", None)},
            volumes={config_dir: {"bind": "/config", "mode": "rw"}},
        )
        with managed_container(container):
            wait_for_web_ui(container)
            config = config_file.read_text(encoding="utf-8")

            assert "Connection\\UPnP=false" in config
            assert "Downloads\\SavePath=/downloads/" in config
            assert "Downloads\\TempPath=/downloads/incomplete/" in config
            assert "WebUI\\Address=*" in config


def test_nonempty_config_directory_is_not_seeded():
    with tempfile.TemporaryDirectory() as config_dir:
        os.chmod(config_dir, 0o777)
        marker = Path(config_dir) / "keep-me"
        marker.write_text("existing config data", encoding="utf-8")
        config_file = (
            Path(config_dir) / "qBittorrent" / "config" / "qBittorrent.conf"
        )
        container = docker_client().containers.run(
            IMAGE,
            command=["--version"],
            remove=True,
            volumes={config_dir: {"bind": "/config", "mode": "rw"}},
        )
        assert b"qBittorrent v5.3.0" in container
        assert marker.read_text(encoding="utf-8") == "existing config data"
        assert not config_file.exists()
