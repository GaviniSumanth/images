import subprocess

import pytest

import load_image
from load_image import load_image as load

pytestmark = pytest.mark.unit


def test_load_image_converts_and_loads_archive():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    docker_archive = load(
        "/tmp/image.oci.tar", "ghcr.io/owner/example:v1", runner=runner
    )

    assert docker_archive == "/tmp/image.oci.tar.docker.tar"
    assert calls[0][0] == [
        "skopeo",
        "copy",
        "--multi-arch",
        "system",
        "oci-archive:/tmp/image.oci.tar",
        "docker-archive:/tmp/image.oci.tar.docker.tar:ghcr.io/owner/example:v1",
    ]
    assert calls[1][0] == ["docker", "load", "-i", "/tmp/image.oci.tar.docker.tar"]
    assert calls[2][0] == [
        "docker",
        "image",
        "inspect",
        "ghcr.io/owner/example:v1",
    ]


def test_load_image_uses_explicit_docker_archive():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    archive = load(
        "/tmp/image.oci.tar",
        "example:v1",
        docker_archive="/tmp/image.docker.tar",
        runner=runner,
    )
    assert archive == "/tmp/image.docker.tar"
    assert calls[0][-1] == "docker-archive:/tmp/image.docker.tar:example:v1"


def test_load_image_propagates_command_failure():
    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        load("/tmp/image.oci.tar", "example:v1", runner=runner)
