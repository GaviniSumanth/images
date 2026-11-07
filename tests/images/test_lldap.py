import os
import secrets
import tempfile

import pytest

from container_test_common import (
    check_image_contract,
    container_name,
    docker_client,
    managed_container,
    wait_for_container,
)
from image_contract import EXPECTED_PORTS


IMAGE = os.environ.get("TEST_IMAGE")
CONFIG_FILE = "/data/lldap_config.toml"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(IMAGE is None, reason="TEST_IMAGE is not set"),
]


def environment():
    return {
        "LLDAP_JWT_SECRET": secrets.token_hex(32),
        "LLDAP_KEY_SEED": secrets.token_hex(32),
        "LLDAP_LDAP_BASE_DN": "dc=example,dc=com",
        "LLDAP_LDAP_USER_PASS": secrets.token_hex(16),
    }


def is_ready(container):
    result = container.exec_run(
        ["/app/lldap", "healthcheck", "--config-file", CONFIG_FILE]
    )
    return result.exit_code == 0


def test_image_contract():
    check_image_contract(IMAGE, EXPECTED_PORTS["lldap"])


def test_container_becomes_ready():
    name = container_name("lldap")
    container = docker_client().containers.run(
        IMAGE,
        detach=True,
        name=name,
        environment=environment(),
    )
    with managed_container(container):
        wait_for_container(container, is_ready)


def test_empty_data_directory_is_bootstrapped():
    with tempfile.TemporaryDirectory() as data_dir:
        os.chmod(data_dir, 0o777)

        name = container_name("lldap")
        container = docker_client().containers.run(
            IMAGE,
            detach=True,
            name=name,
            environment=environment(),
            volumes={data_dir: {"bind": "/data", "mode": "rw"}},
        )
        with managed_container(container):
            wait_for_container(container, is_ready)
            assert os.path.isfile(os.path.join(data_dir, "lldap_config.toml"))
