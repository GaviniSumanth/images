#!/usr/bin/env python3
"""Prepare OCI labels, annotations, and the upstream revision for a build."""

import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from release_config import ReleaseConfigError, required_env


class MetadataError(Exception):
    """Raised when build metadata cannot be prepared."""


def upstream_revision(source: Path) -> str:
    if not source.is_dir():
        raise MetadataError(f"Upstream source directory does not exist: {source}")

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or f"exit code {result.returncode}"
        raise MetadataError(f"Unable to read upstream revision from {source}: {details}")

    revision = result.stdout.strip()
    if not revision:
        raise MetadataError(f"Upstream revision is empty for {source}")

    return revision


def build_metadata(
    workspace: Path,
    upstream_source: str,
    release_metadata: str,
    upstream_version: str,
    container_source: str,
    container_vendor: str,
    now: datetime | None = None,
) -> tuple[str, str, str]:
    """Return the revision, labels, and annotations for a build."""
    workspace = workspace.resolve()
    source = (workspace / upstream_source).resolve()
    if not source.is_relative_to(workspace):
        raise MetadataError("UPSTREAM_SOURCE must be inside GITHUB_WORKSPACE")

    revision = upstream_revision(source)

    try:
        metadata = json.loads(release_metadata)
    except json.JSONDecodeError as error:
        raise MetadataError(f"RELEASE_METADATA is not valid JSON: {error}") from error

    if not isinstance(metadata, dict):
        raise MetadataError("RELEASE_METADATA must be a JSON object")

    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in metadata.items()
    ):
        raise MetadataError("RELEASE_METADATA must contain only string values")

    if any("\n" in key or "\r" in key for key in metadata):
        raise MetadataError("RELEASE_METADATA keys must be single-line strings")

    if any("\n" in value or "\r" in value for value in metadata.values()):
        raise MetadataError("RELEASE_METADATA values must be single-line strings")

    for value in (upstream_version, container_source, container_vendor):
        if not value or "\n" in value or "\r" in value:
            raise MetadataError("Build metadata values must be non-empty single-line strings")

    created = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata.update(
        {
            "org.opencontainers.image.version": upstream_version,
            "org.opencontainers.image.source": container_source,
            "org.opencontainers.image.vendor": container_vendor,
            "org.opencontainers.image.created": created,
            "org.opencontainers.image.revision": revision,
        }
    )

    entries = sorted(metadata.items())
    labels = "\n".join(f"{key}={value}" for key, value in entries)
    annotations = "\n".join(
        f"{kind}:{key}={value}"
        for key, value in entries
        for kind in ("index", "manifest")
    )

    return revision, labels, annotations


def write_output(name: str, value: str) -> None:
    with open(required_env("GITHUB_OUTPUT"), "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def write_multiline_output(name: str, value: str) -> None:
    delimiter = f"EOF_{secrets.token_hex(16)}"
    while delimiter in value:
        delimiter = f"EOF_{secrets.token_hex(16)}"

    with open(required_env("GITHUB_OUTPUT"), "a", encoding="utf-8") as output:
        output.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def main() -> None:
    try:
        workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
        revision, labels, annotations = build_metadata(
            workspace=workspace,
            upstream_source=required_env("UPSTREAM_SOURCE"),
            release_metadata=required_env("RELEASE_METADATA"),
            upstream_version=required_env("UPSTREAM_VERSION"),
            container_source=required_env("CONTAINER_SOURCE"),
            container_vendor=required_env("CONTAINER_VENDOR"),
        )

        write_output("revision", revision)
        write_multiline_output("labels", labels)
        write_multiline_output("annotations", annotations)
    except (MetadataError, OSError, ReleaseConfigError) as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
