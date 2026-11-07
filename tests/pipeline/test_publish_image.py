import hashlib
import io
import json
import os
import subprocess
import tarfile

import pytest

from publish_image import (
    PublishError,
    attestation_count,
    authfile_from_env,
    is_not_found,
    labels_from_config,
    manifest_digests,
    platform_manifest_digest,
    publish,
    raw_digest,
    read_image_index,
    read_oci_index,
    verify_labels,
)

pytestmark = pytest.mark.unit

PLATFORM_DIGEST = "sha256:" + "a" * 64
ATTESTATION_DIGEST = "sha256:" + "b" * 64
OTHER_DIGEST = "sha256:" + "c" * 64

METADATA = {"org.opencontainers.image.title": "Example"}
LABELS = {
    "org.opencontainers.image.title": "Example",
    "org.opencontainers.image.version": "v1.2.3",
    "org.opencontainers.image.source": "https://github.com/owner/images",
    "org.opencontainers.image.vendor": "owner",
    "org.opencontainers.image.created": "2026-01-02T03:04:05Z",
    "org.opencontainers.image.revision": "abc123",
}
CONFIG = {"config": {"Labels": LABELS}}


def index_bytes(platform_digest=PLATFORM_DIGEST, include_attestation=True):
    manifests = [
        {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": platform_digest,
            "size": 1,
            "platform": {"architecture": "amd64", "os": "linux"},
        }
    ]
    if include_attestation:
        manifests.append(
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": ATTESTATION_DIGEST,
                "size": 1,
                "annotations": {"vnd.docker.reference.type": "attestation-manifest"},
                "platform": {"architecture": "unknown", "os": "unknown"},
            }
        )

    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": manifests,
        }
    ).encode()


def oci_archive(tmp_path, raw=None):
    path = tmp_path / "image.oci.tar"
    raw = raw or index_bytes()
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo("index.json")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
    return str(path)


def nested_oci_archive(tmp_path):
    """Build the layout buildx produces: a wrapper index around the image index."""
    inner = index_bytes()
    inner_digest = "sha256:" + hashlib.sha256(inner).hexdigest()
    wrapper = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "digest": inner_digest,
                    "size": len(inner),
                }
            ],
        }
    ).encode()

    path = tmp_path / "nested.oci.tar"
    with tarfile.open(path, "w") as tar:
        for name, data in (
            ("index.json", wrapper),
            (f"blobs/sha256/{inner_digest.split(':', 1)[1]}", inner),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return str(path)


class FakeRegistry:
    def __init__(self, raw, existing_raw=None, alias_raw=None, config=None):
        self.raw = raw
        self.tags = {}
        if existing_raw is not None:
            self.tags["docker://ghcr.io/owner/example:v1.2.3-42-1"] = existing_raw
        self.alias_raw = alias_raw
        self.config = config or CONFIG
        self.copies = []

    def __call__(self, command, **kwargs):
        if command[1] == "copy":
            destination = command[-1]
            self.copies.append(destination)
            self.tags[destination] = self.raw
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        assert command[1] == "inspect"
        reference = command[-1]
        if "--config" in command:
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(self.config).encode(), stderr=b""
            )

        if reference not in self.tags:
            return subprocess.CompletedProcess(
                command, 1, stdout=b"", stderr=b"manifest unknown"
            )

        if reference.endswith(":v1.2.3") and self.alias_raw is not None:
            return subprocess.CompletedProcess(
                command, 0, stdout=self.alias_raw, stderr=b""
            )

        return subprocess.CompletedProcess(
            command, 0, stdout=self.tags[reference], stderr=b""
        )


def publish_image(tmp_path, registry, **overrides):
    arguments = {
        "image": "ghcr.io/owner/example",
        "release_tag_name": "v1.2.3-42-1",
        "alias": "v1.2.3",
        "metadata": METADATA,
        "upstream_version": "v1.2.3",
        "container_source": "https://github.com/owner/images",
        "container_vendor": "owner",
        "authfile": "/tmp/auth.json",
        "runner": registry,
    }
    if "archive" not in overrides:
        arguments["archive"] = oci_archive(tmp_path)
    arguments.update(overrides)
    publish(**arguments)


def test_read_oci_index(tmp_path):
    raw = index_bytes()
    assert read_oci_index(oci_archive(tmp_path, raw)) == raw


def test_read_oci_index_rejects_missing_file(tmp_path):
    with pytest.raises(PublishError):
        read_oci_index(str(tmp_path / "missing.tar"))


def test_read_image_index_unwraps_nested_buildx_index(tmp_path):
    raw = read_image_index(nested_oci_archive(tmp_path))
    assert platform_manifest_digest(raw) == PLATFORM_DIGEST
    assert manifest_digests(raw) == {PLATFORM_DIGEST, ATTESTATION_DIGEST}
    assert attestation_count(raw) == 1


def test_read_image_index_keeps_a_plain_index(tmp_path):
    raw = index_bytes()
    assert read_image_index(oci_archive(tmp_path, raw)) == raw


def test_read_image_index_rejects_a_missing_wrapper_blob(tmp_path):
    archive = tmp_path / "broken.oci.tar"
    wrapper = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "digest": "sha256:" + "d" * 64,
                    "size": 1,
                }
            ],
        }
    ).encode()
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("index.json")
        info.size = len(wrapper)
        tar.addfile(info, io.BytesIO(wrapper))

    with pytest.raises(PublishError, match="blobs/sha256"):
        read_image_index(str(archive))


def test_index_helpers():
    raw = index_bytes()
    assert platform_manifest_digest(raw) == PLATFORM_DIGEST
    assert manifest_digests(raw) == {PLATFORM_DIGEST, ATTESTATION_DIGEST}
    assert attestation_count(raw) == 1
    assert raw_digest(raw).startswith("sha256:")


def test_index_without_attestation_is_detected():
    raw = index_bytes(include_attestation=False)
    assert attestation_count(raw) == 0


def test_index_rejects_non_object():
    with pytest.raises(PublishError, match="JSON object"):
        platform_manifest_digest(b"[]")


def test_authfile_prefers_registry_auth_file(monkeypatch, tmp_path):
    monkeypatch.setenv("REGISTRY_AUTH_FILE", str(tmp_path / "auth.json"))
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker"))
    assert authfile_from_env() == str(tmp_path / "auth.json")


def test_authfile_uses_docker_config(monkeypatch, tmp_path):
    monkeypatch.delenv("REGISTRY_AUTH_FILE", raising=False)
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker"))
    assert authfile_from_env() == str(tmp_path / "docker" / "config.json")


def test_authfile_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("REGISTRY_AUTH_FILE", raising=False)
    monkeypatch.delenv("DOCKER_CONFIG", raising=False)
    assert authfile_from_env() == os.path.expanduser("~/.docker/config.json")


def test_is_not_found():
    assert is_not_found("manifest unknown")
    assert is_not_found("not found")
    assert not is_not_found("unauthorized")


def test_labels_from_config():
    assert labels_from_config(CONFIG) == LABELS


def test_verify_labels_accepts_expected_labels():
    verify_labels(
        LABELS,
        METADATA,
        "v1.2.3",
        "https://github.com/owner/images",
        "owner",
    )


def test_verify_labels_rejects_missing_label():
    labels = dict(LABELS)
    del labels["org.opencontainers.image.version"]
    with pytest.raises(PublishError, match="version"):
        verify_labels(
            labels,
            METADATA,
            "v1.2.3",
            "https://github.com/owner/images",
            "owner",
        )


def test_publish_pushes_immutable_and_alias(tmp_path):
    raw = index_bytes()
    registry = FakeRegistry(raw)

    publish_image(tmp_path, registry)

    assert registry.copies == [
        "docker://ghcr.io/owner/example:v1.2.3-42-1",
        "docker://ghcr.io/owner/example:v1.2.3",
    ]


def test_publish_accepts_a_nested_buildx_archive(tmp_path):
    registry = FakeRegistry(index_bytes())

    publish_image(tmp_path, registry, archive=nested_oci_archive(tmp_path))

    assert registry.copies == [
        "docker://ghcr.io/owner/example:v1.2.3-42-1",
        "docker://ghcr.io/owner/example:v1.2.3",
    ]


def test_publish_is_idempotent_for_existing_immutable_tag(tmp_path):
    raw = index_bytes()
    registry = FakeRegistry(raw, existing_raw=raw)

    publish_image(tmp_path, registry)

    assert registry.copies == ["docker://ghcr.io/owner/example:v1.2.3"]


def test_publish_rejects_colliding_immutable_tag(tmp_path):
    registry = FakeRegistry(
        index_bytes(), existing_raw=index_bytes(platform_digest=OTHER_DIGEST)
    )

    with pytest.raises(PublishError, match="already exists"):
        publish_image(tmp_path, registry)

    assert registry.copies == []


def test_publish_rejects_missing_attestations(tmp_path):
    raw = index_bytes(include_attestation=False)
    registry = FakeRegistry(raw)

    with pytest.raises(PublishError, match="attestation"):
        publish_image(tmp_path, registry, archive=oci_archive(tmp_path, raw))

    assert registry.copies == []


def test_publish_rejects_alias_pointing_at_a_different_image(tmp_path):
    raw = index_bytes()
    registry = FakeRegistry(raw, alias_raw=index_bytes(platform_digest=OTHER_DIGEST))

    with pytest.raises(PublishError, match="alias"):
        publish_image(tmp_path, registry)


def test_publish_rejects_missing_archive_manifests(tmp_path):
    raw = index_bytes()
    registry = FakeRegistry(raw)

    class MissingManifestRegistry(FakeRegistry):
        def __call__(self, command, **kwargs):
            if command[1] == "inspect" and "--raw" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=index_bytes(include_attestation=False),
                    stderr=b"",
                )
            return super().__call__(command, **kwargs)

    with pytest.raises(PublishError, match="missing archive manifests"):
        publish_image(tmp_path, MissingManifestRegistry(raw))


def test_publish_rejects_bad_labels(tmp_path):
    config = {"config": {"Labels": {}}}
    registry = FakeRegistry(index_bytes(), config=config)

    with pytest.raises(PublishError, match="label"):
        publish_image(tmp_path, registry)
