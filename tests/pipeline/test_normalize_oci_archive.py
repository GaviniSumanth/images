import hashlib
import io
import json
import tarfile

import pytest

from normalize_oci_archive import (
    NormalizeError,
    ZSTD_ANNOTATION,
    normalize_archive,
)

pytestmark = pytest.mark.unit

INDEX_TYPE = "application/vnd.oci.image.index.v1+json"
IMAGE_TYPE = "application/vnd.oci.image.manifest.v1+json"
CONFIG_TYPE = "application/vnd.oci.image.config.v1+json"
GZIP_LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"
ZSTD_LAYER = "application/vnd.oci.image.layer.v1.tar+zstd"
ATTESTATION_TYPE = "vnd.docker.reference.type"


def digest_of(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blob_name(digest):
    algorithm, _, value = digest.partition(":")
    return f"blobs/{algorithm}/{value}"


def manifest_blob(layers):
    config = json.dumps({"config": {}}, separators=(",", ":")).encode()
    manifest = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": IMAGE_TYPE,
            "config": {
                "mediaType": CONFIG_TYPE,
                "digest": digest_of(config),
                "size": len(config),
            },
            "layers": layers,
        },
        separators=(",", ":"),
    ).encode()
    return manifest, config


def build_archive(
    tmp_path,
    layer_type,
    nested=True,
    annotated=False,
    name="image.oci.tar",
):
    """Write an OCI archive shaped like buildx's output and return its details."""
    image_manifest, image_config = manifest_blob(
        [
            {
                "mediaType": layer_type,
                "digest": digest_of(b"layer"),
                "size": len(b"layer"),
            }
        ]
    )
    attestation_manifest, attestation_config = manifest_blob(
        [
            {
                "mediaType": "application/vnd.in-toto+json",
                "digest": digest_of(b"attestation"),
                "size": len(b"attestation"),
            }
        ]
    )

    image_digest = digest_of(image_manifest)
    attestation_digest = digest_of(attestation_manifest)
    image_descriptor = {
        "mediaType": IMAGE_TYPE,
        "digest": image_digest,
        "size": len(image_manifest),
        "platform": {"architecture": "amd64", "os": "linux"},
    }
    if annotated:
        image_descriptor["annotations"] = {ZSTD_ANNOTATION: "true"}

    inner = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": INDEX_TYPE,
            "manifests": [
                image_descriptor,
                {
                    "mediaType": IMAGE_TYPE,
                    "digest": attestation_digest,
                    "size": len(attestation_manifest),
                    "platform": {"architecture": "unknown", "os": "unknown"},
                    "annotations": {
                        ATTESTATION_TYPE: "attestation-manifest",
                        "vnd.docker.reference.digest": image_digest,
                    },
                },
            ],
        },
        separators=(",", ":"),
    ).encode()

    inner_digest = digest_of(inner)
    if nested:
        root = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_TYPE,
                "manifests": [
                    {
                        "mediaType": INDEX_TYPE,
                        "digest": inner_digest,
                        "size": len(inner),
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
    else:
        root = inner

    members = {
        "index.json": root,
        "oci-layout": json.dumps({"imageLayoutVersion": "1.0.0"}).encode(),
        blob_name(image_digest): image_manifest,
        blob_name(attestation_digest): attestation_manifest,
        blob_name(digest_of(image_config)): image_config,
        blob_name(digest_of(attestation_config)): attestation_config,
        blob_name(digest_of(b"layer")): b"layer",
        blob_name(digest_of(b"attestation")): b"attestation",
    }
    if nested:
        members[blob_name(inner_digest)] = inner

    path = tmp_path / name
    with tarfile.open(path, "w") as tar:
        for member_name, data in members.items():
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    return {
        "path": str(path),
        "root": root,
        "inner": inner,
        "inner_digest": inner_digest,
        "image_digest": image_digest,
    }


def read_members(archive):
    with tarfile.open(archive) as tar:
        return {
            member.name: tar.extractfile(member).read()
            for member in tar
            if member.isfile()
        }


def read_index(archive, name="index.json"):
    return json.loads(read_members(archive)[name])


def read_resolved_index(archive):
    root = read_index(archive)
    entry = root["manifests"][0]
    if entry["mediaType"] == INDEX_TYPE:
        return read_index(archive, blob_name(entry["digest"])), entry
    return root, entry


def test_normalize_annotates_zstd_image_descriptors(tmp_path):
    details = build_archive(tmp_path, ZSTD_LAYER)

    assert normalize_archive(details["path"]) is True

    inner, wrapper_entry = read_resolved_index(details["path"])
    assert wrapper_entry["digest"] == digest_of(
        read_members(details["path"])[blob_name(wrapper_entry["digest"])]
    )
    assert wrapper_entry["size"] == len(
        read_members(details["path"])[blob_name(wrapper_entry["digest"])]
    )
    assert wrapper_entry["digest"] != details["inner_digest"]

    image, attestation = inner["manifests"]
    assert image["digest"] == details["image_digest"]
    assert image["annotations"][ZSTD_ANNOTATION] == "true"
    assert ZSTD_ANNOTATION not in attestation.get("annotations", {})
    assert attestation["annotations"][ATTESTATION_TYPE] == "attestation-manifest"


def test_normalize_leaves_gzip_archives_unchanged(tmp_path):
    details = build_archive(tmp_path, GZIP_LAYER)
    before = read_members(details["path"])

    assert normalize_archive(details["path"]) is False

    assert read_members(details["path"]) == before


def test_normalize_is_idempotent(tmp_path):
    details = build_archive(tmp_path, ZSTD_LAYER)

    assert normalize_archive(details["path"]) is True
    after_first = read_members(details["path"])

    assert normalize_archive(details["path"]) is False
    assert read_members(details["path"]) == after_first


def test_normalize_accepts_an_existing_annotation(tmp_path):
    details = build_archive(tmp_path, ZSTD_LAYER, annotated=True)
    before = read_members(details["path"])

    assert normalize_archive(details["path"]) is False
    assert read_members(details["path"]) == before


def test_normalize_supports_a_direct_image_index(tmp_path):
    details = build_archive(tmp_path, ZSTD_LAYER, nested=False)

    assert normalize_archive(details["path"]) is True

    index = read_index(details["path"])
    assert index["manifests"][0]["annotations"][ZSTD_ANNOTATION] == "true"


def test_normalize_keeps_every_original_blob(tmp_path):
    details = build_archive(tmp_path, ZSTD_LAYER)
    before = read_members(details["path"])

    assert normalize_archive(details["path"]) is True

    after = read_members(details["path"])
    assert set(before) <= set(after)
    for name, data in before.items():
        if name == "index.json" or name == blob_name(details["inner_digest"]):
            continue
        assert after[name] == data


def test_normalize_rejects_a_missing_archive(tmp_path):
    with pytest.raises(NormalizeError, match="Unable to read"):
        normalize_archive(str(tmp_path / "missing.tar"))


def test_normalize_rejects_an_archive_without_an_index(tmp_path):
    archive = tmp_path / "no-index.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("oci-layout")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"{}"))

    with pytest.raises(NormalizeError, match="index.json"):
        normalize_archive(str(archive))


def test_normalize_rejects_an_invalid_index(tmp_path):
    archive = tmp_path / "invalid.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("index.json")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"{"))

    with pytest.raises(NormalizeError, match="not valid JSON"):
        normalize_archive(str(archive))


def test_normalize_rejects_a_missing_descriptor_blob(tmp_path):
    archive = tmp_path / "broken.tar"
    index = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": INDEX_TYPE,
            "manifests": [
                {
                    "mediaType": IMAGE_TYPE,
                    "digest": "sha256:" + "d" * 64,
                    "size": 1,
                }
            ],
        }
    ).encode()
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("index.json")
        info.size = len(index)
        tar.addfile(info, io.BytesIO(index))

    with pytest.raises(NormalizeError, match="blobs/sha256"):
        normalize_archive(str(archive))


def test_normalize_rejects_an_invalid_digest(tmp_path):
    archive = tmp_path / "invalid-digest.tar"
    index = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": INDEX_TYPE,
            "manifests": [{"mediaType": IMAGE_TYPE, "digest": "../escape"}],
        }
    ).encode()
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("index.json")
        info.size = len(index)
        tar.addfile(info, io.BytesIO(index))

    with pytest.raises(NormalizeError, match="Invalid OCI digest"):
        normalize_archive(str(archive))


def test_cli_annotates_the_archive(tmp_path, run_script):
    details = build_archive(tmp_path, ZSTD_LAYER)

    result = run_script(
        "normalize_oci_archive.py", env={"OCI_ARCHIVE": details["path"]}
    )

    assert result.returncode == 0, result.stderr
    assert "Annotated" in result.stdout
    inner, _ = read_resolved_index(details["path"])
    assert inner["manifests"][0]["annotations"][ZSTD_ANNOTATION] == "true"


def test_cli_requires_an_archive(run_script):
    result = run_script("normalize_oci_archive.py", env={"OCI_ARCHIVE": ""})

    assert result.returncode == 1
    assert "OCI_ARCHIVE" in result.stdout
