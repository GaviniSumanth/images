import json
import os
import secrets
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
import yaml

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
USERS_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$qOKNq+u5lZHOTnsJY1Sp3g$"
    "s6zT9EKncfkmIJmykzZProUigRRJ26hlTl1WC+mG2do"
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(IMAGE is None, reason="TEST_IMAGE is not set"),
]


def configuration():
    session_secret = secrets.token_hex(32)
    storage_key = secrets.token_hex(32)
    jwt_secret = secrets.token_hex(32)

    return {
        "server": {"address": "tcp://0.0.0.0:9091"},
        "log": {"level": "info"},
        "totp": {"issuer": "example.com"},
        "identity_validation": {
            "reset_password": {"jwt_secret": jwt_secret},
        },
        "authentication_backend": {
            "file": {"path": "/config/users_database.yml"},
        },
        "access_control": {
            "default_policy": "one_factor",
            "rules": [
                {
                    "domain": "example.com",
                    "policy": "one_factor",
                }
            ],
        },
        "session": {
            "secret": session_secret,
            "cookies": [
                {
                    "name": "authelia_session",
                    "domain": "example.com",
                    "authelia_url": "https://example.com:9091",
                    "expiration": "1 hour",
                    "inactivity": "5 minutes",
                }
            ],
        },
        "regulation": {
            "max_retries": 3,
            "find_time": "2 minutes",
            "ban_time": "5 minutes",
        },
        "storage": {
            "encryption_key": storage_key,
            "local": {"path": "/config/db.sqlite3"},
        },
        "notifier": {"filesystem": {"filename": "/config/notification.txt"}},
        "ntp": {"disable_startup_check": True},
    }


def users_database():
    return {
        "users": {
            "authelia": {
                "disabled": False,
                "displayname": "Authelia User",
                "password": USERS_PASSWORD_HASH,
                "email": "authelia@example.com",
                "groups": ["admins"],
            }
        }
    }


@contextmanager
def authelia_config():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        os.chmod(path, 0o777)
        (path / "configuration.yml").write_text(
            yaml.safe_dump(configuration(), sort_keys=False), encoding="utf-8"
        )
        (path / "users_database.yml").write_text(
            yaml.safe_dump(users_database(), sort_keys=False), encoding="utf-8"
        )
        for name in ("configuration.yml", "users_database.yml"):
            os.chmod(path / name, 0o644)
        yield str(path)


@pytest.fixture
def config_dir():
    with authelia_config() as directory:
        yield directory


def test_image_contract():
    check_image_contract(IMAGE, EXPECTED_PORTS["authelia"])


def test_build_info_command():
    output = docker_client().containers.run(
        IMAGE, command=["build-info"], remove=True
    )
    fields = {}
    for line in output.decode("utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key] = value.strip()

    assert fields.get("State") == "tagged clean", fields


def test_configuration_is_valid(config_dir):
    output = docker_client().containers.run(
        IMAGE,
        command=["config", "validate", "--config", "/config/configuration.yml"],
        remove=True,
        volumes={config_dir: {"bind": "/config", "mode": "rw"}},
        tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m,uid=1000,gid=1000"},
    )
    assert b"without errors" in output, output.decode("utf-8", errors="replace")


def test_container_becomes_ready(config_dir):
    name = container_name("authelia")
    container = docker_client().containers.run(
        IMAGE,
        detach=True,
        name=name,
        ports={"9091/tcp": ("127.0.0.1", None)},
        volumes={config_dir: {"bind": "/config", "mode": "rw"}},
        tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m,uid=1000,gid=1000"},
    )
    with managed_container(container):
        health_url = (
            f"http://127.0.0.1:{published_port(container, 9091)}/api/health"
        )

        def is_ready(_running_container):
            try:
                with urlopen(health_url, timeout=5) as response:
                    if response.status != 200:
                        return False
                    payload = json.loads(response.read() or b"{}")
                    return payload.get("status") == "OK"
            except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                return False

        wait_for_container(container, is_ready)
        assert (Path(config_dir) / "db.sqlite3").is_file()
