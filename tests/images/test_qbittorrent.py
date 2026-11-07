import io
import os
import tarfile
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from docker.errors import NotFound

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


@contextmanager
def managed_config_volume():
    volume = docker_client().volumes.create()
    try:
        yield volume
    finally:
        volume.remove(force=True)


def archive_file(name, contents):
    data = contents.encode("utf-8")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
    archive.seek(0)
    return archive


def read_container_file(container, path):
    archive, _ = container.get_archive(path)
    with tarfile.open(fileobj=io.BytesIO(b"".join(archive))) as tar:
        file_name = path.rsplit("/", 1)[-1]
        config_file = tar.extractfile(file_name)
        assert config_file is not None
        return config_file.read().decode("utf-8")


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
    with managed_config_volume() as config_volume:
        container = docker_client().containers.run(
            IMAGE,
            detach=True,
            name=container_name("qbittorrent"),
            ports={"8080/tcp": ("127.0.0.1", None)},
            volumes={config_volume.name: {"bind": "/config", "mode": "rw"}},
        )
        with managed_container(container):
            wait_for_web_ui(container)
            config = read_container_file(
                container, "/config/qBittorrent/config/qBittorrent.conf"
            )

            assert "Connection\\UPnP=false" in config
            assert "Downloads\\SavePath=/downloads/" in config
            assert "Downloads\\TempPath=/downloads/incomplete/" in config
            assert "WebUI\\Address=*" in config


def test_nonempty_config_directory_is_not_seeded():
    with managed_config_volume() as config_volume:
        container = docker_client().containers.create(
            IMAGE,
            command=["--version"],
            volumes={config_volume.name: {"bind": "/config", "mode": "rw"}},
        )
        with managed_container(container):
            assert container.put_archive(
                "/config", archive_file("keep-me", "existing config data")
            )
            container.start()
            result = container.wait(timeout=30)

            assert result["StatusCode"] == 0
            assert b"qBittorrent v5.3.0" in container.logs()
            assert (
                read_container_file(container, "/config/keep-me")
                == "existing config data"
            )

            with pytest.raises(NotFound):
                container.get_archive(
                    "/config/qBittorrent/config/qBittorrent.conf"
                )
