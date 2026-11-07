#!/usr/bin/env python3
"""Add skopeo's zstd compression annotation to an OCI archive index.

Older skopeo versions add ``io.github.containers.compression.zstd`` to the
index descriptor of an image that uses zstd-compressed layers. That edit
changes the index digest, so a later ``skopeo copy --preserve-digests``
refuses to push the archive. Adding the annotation at build time makes the
skopeo edit a no-op, so the tested digest can still be preserved.

See podman-container-tools/skopeo#2627.
"""

import hashlib
import io
import json
import os
import re
import sys
import tarfile
import tempfile

from release_config import ReleaseConfigError, required_env

INDEX_MEDIA_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
IMAGE_MEDIA_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
ZSTD_LAYER_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+zstd",
    "application/vnd.oci.image.layer.nondistributable.v1.tar+zstd",
}
ZSTD_ANNOTATION = "io.github.containers.compression.zstd"
DIGEST_PATTERN = re.compile(r"[a-z0-9]+:[0-9a-f]+")


class NormalizeError(Exception):
    """Raised when an OCI archive cannot be normalized."""


def blob_name(digest: str) -> str:
    algorithm, _, value = digest.partition(":")
    return f"blobs/{algorithm}/{value}"


def digest_of(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def read_member(tar: tarfile.TarFile, name: str) -> bytes:
    try:
        extracted = tar.extractfile(tar.getmember(name))
    except (KeyError, OSError, tarfile.TarError) as error:
        raise NormalizeError(f"Unable to read {name} from archive: {error}") from error

    if extracted is None:
        raise NormalizeError(f"Archive member {name} is not a file")

    return extracted.read()


def read_blob(tar: tarfile.TarFile, digest: object) -> bytes:
    if not isinstance(digest, str) or not DIGEST_PATTERN.fullmatch(digest):
        raise NormalizeError(f"Invalid OCI digest: {digest!r}")

    return read_member(tar, blob_name(digest))


def has_zstd_layer(manifest: dict) -> bool:
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        return False

    return any(
        isinstance(layer, dict) and layer.get("mediaType") in ZSTD_LAYER_TYPES
        for layer in layers
    )


def annotate(index: dict, tar: tarfile.TarFile, new_blobs: dict[str, bytes]) -> bool:
    """Annotate zstd image descriptors and return whether the index changed."""
    manifests = index.get("manifests")
    if not isinstance(manifests, list):
        return False

    changed = False
    for descriptor in manifests:
        if not isinstance(descriptor, dict):
            continue

        media_type = descriptor.get("mediaType")
        if media_type in INDEX_MEDIA_TYPES:
            inner = json.loads(read_blob(tar, descriptor.get("digest")))
            if annotate(inner, tar, new_blobs):
                blob = json.dumps(inner, separators=(",", ":")).encode()
                new_digest = digest_of(blob)
                new_blobs[blob_name(new_digest)] = blob
                descriptor["digest"] = new_digest
                descriptor["size"] = len(blob)
                changed = True
        elif media_type in IMAGE_MEDIA_TYPES:
            manifest = json.loads(read_blob(tar, descriptor.get("digest")))
            if not has_zstd_layer(manifest):
                continue

            annotations = descriptor.get("annotations")
            if not isinstance(annotations, dict):
                annotations = {}
                descriptor["annotations"] = annotations

            if annotations.get(ZSTD_ANNOTATION) != "true":
                annotations[ZSTD_ANNOTATION] = "true"
                changed = True

    return changed


def copy_member(
    target: tarfile.TarFile,
    member: tarfile.TarInfo,
    data: bytes | None = None,
    stream=None,
) -> None:
    if data is not None:
        info = tarfile.TarInfo(member.name)
        info.size = len(data)
        info.mode = member.mode
        info.mtime = member.mtime
        info.uid = member.uid
        info.gid = member.gid
        info.uname = member.uname
        info.gname = member.gname
        target.addfile(info, io.BytesIO(data))
    else:
        target.addfile(member, stream)


def rewrite(archive: str, index: bytes, new_blobs: dict[str, bytes]) -> None:
    directory = os.path.dirname(os.path.abspath(archive))
    handle, temporary = tempfile.mkstemp(
        dir=directory, prefix=".normalize-", suffix=".tar"
    )
    os.close(handle)

    try:
        with tarfile.open(archive) as source, tarfile.open(temporary, "w") as target:
            for member in source:
                if member.name == "index.json":
                    copy_member(target, member, data=index)
                elif member.name in new_blobs:
                    continue
                elif member.isfile():
                    copy_member(target, member, stream=source.extractfile(member))
                else:
                    target.addfile(member)

            for name, data in new_blobs.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                target.addfile(info, io.BytesIO(data))
        os.replace(temporary, archive)
    except BaseException:
        os.unlink(temporary)
        raise


def normalize_archive(archive: str) -> bool:
    """Add the zstd annotation in place and return whether anything changed."""
    try:
        with tarfile.open(archive) as tar:
            index = json.loads(read_member(tar, "index.json"))
            new_blobs: dict[str, bytes] = {}
            if not annotate(index, tar, new_blobs):
                return False
            new_index = json.dumps(index, separators=(",", ":")).encode()
    except json.JSONDecodeError as error:
        raise NormalizeError(f"OCI index is not valid JSON: {error}") from error
    except (OSError, tarfile.TarError) as error:
        raise NormalizeError(f"Unable to read OCI archive {archive}: {error}") from error

    rewrite(archive, new_index, new_blobs)
    return True


def main() -> None:
    try:
        archive = required_env("OCI_ARCHIVE")
        changed = normalize_archive(archive)
    except (NormalizeError, ReleaseConfigError, OSError) as error:
        print(f"::error::Unable to normalize OCI archive: {error}")
        sys.exit(1)

    print(f"{'Annotated' if changed else 'Left unchanged'} {archive}")


if __name__ == "__main__":
    main()
