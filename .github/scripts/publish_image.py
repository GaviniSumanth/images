#!/usr/bin/env python3
"""Publish a tested OCI archive to GHCR with immutable and alias tags."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from release_config import ReleaseConfigError, required_env

CREATED_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ATTESTATION_TYPE = "attestation-manifest"


class PublishError(Exception):
    """Raised when the tested archive cannot be published safely."""


def raw_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def read_oci_index(archive: str) -> bytes:
    try:
        with tarfile.open(archive) as tar:
            member = tar.getmember("index.json")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise PublishError(f"OCI archive {archive} has no readable index.json")
            return extracted.read()
    except (KeyError, OSError, tarfile.TarError) as error:
        raise PublishError(f"Unable to read OCI archive {archive}: {error}") from error


def index_manifests(raw_index: bytes) -> list[dict]:
    try:
        data = json.loads(raw_index)
    except json.JSONDecodeError as error:
        raise PublishError(f"OCI index is not valid JSON: {error}") from error

    if not isinstance(data, dict):
        raise PublishError("OCI index must be a JSON object")

    manifests = data.get("manifests")
    if not isinstance(manifests, list):
        return []

    return [manifest for manifest in manifests if isinstance(manifest, dict)]


def platform_manifest_digest(raw_index: bytes) -> str:
    manifests = index_manifests(raw_index)
    if not manifests:
        return raw_digest(raw_index)

    for manifest in manifests:
        platform = manifest.get("platform") or {}
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            digest = manifest.get("digest")
            if isinstance(digest, str) and digest:
                return digest

    if len(manifests) == 1:
        digest = manifests[0].get("digest")
        if isinstance(digest, str) and digest:
            return digest

    raise PublishError("OCI index has no linux/amd64 image manifest")


def manifest_digests(raw_index: bytes) -> set[str]:
    manifests = index_manifests(raw_index)
    if not manifests:
        return {raw_digest(raw_index)}

    return {
        manifest["digest"]
        for manifest in manifests
        if isinstance(manifest.get("digest"), str)
    }


def attestation_count(raw_index: bytes) -> int:
    count = 0
    for manifest in index_manifests(raw_index):
        annotations = manifest.get("annotations") or {}
        platform = manifest.get("platform") or {}
        if (
            annotations.get("vnd.docker.reference.type") == ATTESTATION_TYPE
            or platform.get("os") == "unknown"
        ):
            count += 1

    return count


def is_not_found(stderr: str) -> bool:
    message = stderr.lower()
    return any(
        phrase in message
        for phrase in (
            "manifest unknown",
            "not found",
            "name unknown",
            "no such manifest",
            "does not exist",
        )
    )


def skopeo_command(*args: str, authfile: str | None = None) -> list[str]:
    command = ["skopeo", args[0]]
    if authfile:
        command.extend(["--authfile", authfile])
    command.extend(args[1:])
    return command


def inspect_raw(
    reference: str,
    authfile: str | None = None,
    runner=subprocess.run,
) -> bytes | None:
    result = runner(
        skopeo_command("inspect", "--raw", reference, authfile=authfile),
        capture_output=True,
        timeout=120,
    )
    if result.returncode == 0:
        return result.stdout

    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    if is_not_found(stderr):
        return None

    raise PublishError(f"Unable to inspect {reference}: {stderr.strip() or 'unknown error'}")


def inspect_config(
    reference: str,
    authfile: str | None = None,
    runner=subprocess.run,
) -> dict:
    result = runner(
        skopeo_command("inspect", "--config", reference, authfile=authfile),
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise PublishError(
            f"Unable to inspect {reference} config: {stderr.strip() or 'unknown error'}"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PublishError(f"Image config for {reference} is not valid JSON: {error}") from error


def labels_from_config(config: dict) -> dict:
    labels = (config.get("config") or {}).get("Labels") or {}
    if not isinstance(labels, dict):
        raise PublishError("Image config labels are not an object")

    return labels


def copy_archive(
    archive: str,
    reference: str,
    authfile: str | None = None,
    runner=subprocess.run,
) -> None:
    command = ["skopeo", "copy", "--all", "--preserve-digests"]
    if authfile:
        command.extend(["--authfile", authfile, "--dest-authfile", authfile])
    command.extend([f"oci-archive:{archive}", reference])

    result = runner(command, capture_output=True, timeout=600)
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise PublishError(
            f"Unable to push {reference}: {stderr.strip() or 'unknown error'}"
        )


def verify_labels(
    labels: dict,
    metadata: dict,
    upstream_version: str,
    container_source: str,
    container_vendor: str,
) -> None:
    expected = dict(metadata)
    expected.update(
        {
            "org.opencontainers.image.version": upstream_version,
            "org.opencontainers.image.source": container_source,
            "org.opencontainers.image.vendor": container_vendor,
        }
    )

    for key, value in expected.items():
        if labels.get(key) != value:
            raise PublishError(
                f"Published label {key} is {labels.get(key)!r}, expected {value!r}"
            )

    created = labels.get("org.opencontainers.image.created")
    if not isinstance(created, str) or not CREATED_PATTERN.fullmatch(created):
        raise PublishError("Published image has no valid created label")

    revision = labels.get("org.opencontainers.image.revision")
    if not isinstance(revision, str) or not revision:
        raise PublishError("Published image has no revision label")


def publish(
    archive: str,
    image: str,
    release_tag_name: str,
    alias: str,
    metadata: dict,
    upstream_version: str,
    container_source: str,
    container_vendor: str,
    authfile: str | None = None,
    runner=subprocess.run,
) -> None:
    source_raw = read_oci_index(archive)
    platform_digest = platform_manifest_digest(source_raw)
    source_digests = manifest_digests(source_raw)
    attestations = attestation_count(source_raw)
    if attestations < 1:
        raise PublishError(
            "OCI archive has no attestation manifests; refusing to publish without SBOM/provenance"
        )

    immutable = f"docker://{image}:{release_tag_name}"
    alias_reference = f"docker://{image}:{alias}"

    existing = inspect_raw(immutable, authfile, runner)
    if existing is not None:
        if platform_manifest_digest(existing) != platform_digest:
            raise PublishError(
                f"Immutable tag {image}:{release_tag_name} already exists with a different image"
            )
        print(f"Immutable tag {image}:{release_tag_name} already points at this image")
    else:
        copy_archive(archive, immutable, authfile, runner)

    copy_archive(archive, alias_reference, authfile, runner)

    immutable_raw = inspect_raw(immutable, authfile, runner)
    alias_raw = inspect_raw(alias_reference, authfile, runner)
    if immutable_raw is None or alias_raw is None:
        raise PublishError("Published tag is not readable after push")

    if platform_manifest_digest(immutable_raw) != platform_digest:
        raise PublishError("Published immutable tag does not match the tested image")
    if platform_manifest_digest(alias_raw) != platform_digest:
        raise PublishError("Published alias does not match the tested image")
    if raw_digest(immutable_raw) != raw_digest(alias_raw):
        raise PublishError("Alias and immutable tag point at different indexes")
    if not source_digests.issubset(manifest_digests(immutable_raw)):
        raise PublishError("Published immutable tag is missing archive manifests")
    if not source_digests.issubset(manifest_digests(alias_raw)):
        raise PublishError("Published alias is missing archive manifests")

    labels = labels_from_config(inspect_config(alias_reference, authfile, runner))
    verify_labels(
        labels,
        metadata,
        upstream_version,
        container_source,
        container_vendor,
    )

    print(
        f"Published {image}:{release_tag_name} and alias {image}:{alias} "
        f"(platform digest {platform_digest}, {attestations} attestation manifest(s))"
    )


def authfile_from_env() -> str | None:
    explicit = os.environ.get("REGISTRY_AUTH_FILE")
    if explicit:
        return explicit

    docker_config = os.environ.get("DOCKER_CONFIG")
    if docker_config:
        return str(Path(docker_config) / "config.json")

    return os.path.expanduser("~/.docker/config.json")


def main() -> None:
    try:
        metadata = json.loads(required_env("RELEASE_METADATA"))
        if not isinstance(metadata, dict):
            raise PublishError("RELEASE_METADATA must be a JSON object")

        publish(
            archive=required_env("OCI_ARCHIVE"),
            image=required_env("IMAGE"),
            release_tag_name=required_env("RELEASE_TAG"),
            alias=required_env("ALIAS"),
            metadata=metadata,
            upstream_version=required_env("UPSTREAM_VERSION"),
            container_source=required_env("CONTAINER_SOURCE"),
            container_vendor=required_env("CONTAINER_VENDOR"),
            authfile=authfile_from_env(),
        )
    except (
        PublishError,
        OSError,
        ReleaseConfigError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"::error::Unable to publish image: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
