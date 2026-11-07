import json
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import docker as docker_sdk
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CREATED_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
REQUIRED_PIPELINE_LABELS = (
    "org.opencontainers.image.created",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.source",
    "org.opencontainers.image.vendor",
    "org.opencontainers.image.version",
)

_client = None


def docker_client():
    global _client
    if _client is None:
        _client = docker_sdk.from_env()

    return _client


def release_entry(image):
    data = json.loads((REPO_ROOT / "releases.json").read_text(encoding="utf-8"))
    for entry in data["repositories"]:
        if entry["image"] == image:
            return entry

    pytest.fail(f"No releases.json entry found for image {image!r}")


def expected_ports(ports):
    if isinstance(ports, int):
        return (ports,)

    return tuple(ports)


def check_image_contract(image, ports):
    """Assert the runtime image invariants and metadata contract."""
    entry = release_entry(image)
    attrs = docker_client().images.get(image).attrs
    config = attrs.get("Config") or {}

    assert config.get("User") == "1000:1000", (
        f"Expected image to run as UID/GID 1000:1000, got: {config.get('User')}"
    )

    healthcheck = config.get("Healthcheck")
    assert not healthcheck, f"Image defines a HEALTHCHECK: {healthcheck}"

    labels = config.get("Labels") or {}
    for key, value in entry["metadata"].items():
        assert labels.get(key) == value, (
            f"Label {key} is {labels.get(key)!r}, expected {value!r}"
        )

    for key in REQUIRED_PIPELINE_LABELS:
        assert labels.get(key), f"Missing required image label: {key}"

    assert labels["org.opencontainers.image.version"] == entry["version"], (
        "Image version label does not match releases.json"
    )
    assert CREATED_PATTERN.fullmatch(labels["org.opencontainers.image.created"]), (
        f"Invalid created label: {labels['org.opencontainers.image.created']!r}"
    )

    exposed = set(config.get("ExposedPorts") or {})
    for port in expected_ports(ports):
        assert f"{port}/tcp" in exposed, (
            f"Expected exposed TCP port {port}, got: {sorted(exposed)}"
        )


def check_image_user(image, expected_user):
    attrs = docker_client().images.get(image).attrs
    image_user = (attrs.get("Config") or {}).get("User")
    assert image_user == expected_user, (
        f"Expected image to run as UID/GID {expected_user}, got: {image_user}"
    )


def container_name(prefix):
    run_id = uuid.uuid4().hex[:8]
    return f"{prefix}-test-{run_id}"


def published_port(container, port):
    container.reload()
    bindings = (container.attrs["NetworkSettings"]["Ports"] or {}).get(f"{port}/tcp")
    assert bindings, f"Container {container.name} has no published port {port}/tcp."
    return int(bindings[0]["HostPort"])


@contextmanager
def managed_container(container):
    try:
        yield container
    finally:
        container.remove(force=True)


def container_logs(container):
    return container.logs().decode("utf-8", errors="replace")


def wait_for_container(container, ready, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        container.reload()
        if not container.attrs["State"]["Running"]:
            pytest.fail(
                f"Container {container.name} exited unexpectedly.\n{container_logs(container)}"
            )
        if ready(container):
            return
        time.sleep(1)

    pytest.fail(
        f"Container {container.name} readiness check timed out.\n{container_logs(container)}"
    )
