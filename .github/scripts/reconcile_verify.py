#!/usr/bin/env python3
"""Move verify entries with no published alias into the build matrix."""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from release_config import (
    IMAGE_PATTERN,
    OWNER_PATTERN,
    VERSION_PATTERN,
    ReleaseConfigError,
    required_env,
)

REGISTRY = "ghcr.io"
TIMEOUT_SECONDS = 30
MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


class ReconcileError(Exception):
    """Raised when the verify matrix cannot be reconciled with the registry."""


def parse_matrix(value: str, name: str) -> list[dict]:
    """Parse a matrix output value and return its object entries."""
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError as error:
        raise ReconcileError(f"{name} is not valid JSON: {error}") from error

    if not isinstance(data, list):
        raise ReconcileError(f"{name} must be a JSON array")

    return [entry for entry in data if isinstance(entry, dict)]


def registry_token(
    repository: str,
    actor: str,
    token: str,
    opener=urllib.request.urlopen,
    timeout: int = TIMEOUT_SECONDS,
) -> str:
    """Return a GHCR pull token for a repository."""
    credentials = base64.b64encode(f"{actor}:{token}".encode("utf-8")).decode("ascii")
    query = urllib.parse.urlencode(
        {"service": REGISTRY, "scope": f"repository:{repository}:pull"}
    )
    request = urllib.request.Request(
        f"https://{REGISTRY}/token?{query}",
        headers={"Authorization": f"Basic {credentials}"},
    )

    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ReconcileError(
            f"Unable to get a registry token for {repository}: HTTP {error.code}"
        ) from error
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ReconcileError(
            f"Unable to get a registry token for {repository}: {error}"
        ) from error

    value = payload.get("token") or payload.get("access_token")
    if not isinstance(value, str) or not value:
        raise ReconcileError(f"Registry token response for {repository} has no token")

    return value


def alias_exists(
    repository: str,
    tag: str,
    actor: str,
    token: str,
    opener=urllib.request.urlopen,
    timeout: int = TIMEOUT_SECONDS,
) -> bool:
    """Return whether the repository has the given tag."""
    bearer = registry_token(repository, actor, token, opener, timeout)
    request = urllib.request.Request(
        f"https://{REGISTRY}/v2/{repository}/manifests/{urllib.parse.quote(tag, safe='')}",
        headers={"Authorization": f"Bearer {bearer}", "Accept": MANIFEST_ACCEPT},
    )

    try:
        with opener(request, timeout=timeout) as response:
            response.read()
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise ReconcileError(
            f"Unable to inspect {REGISTRY}/{repository}:{tag}: HTTP {error.code}"
        ) from error
    except (urllib.error.URLError, OSError) as error:
        raise ReconcileError(
            f"Unable to inspect {REGISTRY}/{repository}:{tag}: {error}"
        ) from error


def reconcile(
    build: list[dict],
    verify: list[dict],
    owner: str,
    actor: str,
    token: str,
    exists=alias_exists,
) -> dict[str, list[dict]]:
    """Promote verify entries whose published alias is missing into build."""
    if not OWNER_PATTERN.fullmatch(owner):
        raise ReconcileError(f"Invalid owner: {owner!r}")

    build_images = {entry.get("image") for entry in build}
    remaining = []
    promoted = []

    for entry in verify:
        image = entry.get("image")
        tag = entry.get("tag")
        if (
            not isinstance(image, str)
            or not IMAGE_PATTERN.fullmatch(image)
            or not isinstance(tag, str)
            or not VERSION_PATTERN.fullmatch(tag)
        ):
            raise ReconcileError(f"Invalid verify matrix entry: {entry!r}")

        repository = f"{owner}/{image}"
        if exists(repository, tag, actor, token):
            remaining.append(entry)
        else:
            promoted.append(entry)

    for entry in promoted:
        if entry["image"] not in build_images:
            build.append(entry)
            build_images.add(entry["image"])

    return {"build": build, "verify": remaining}


def write_output(path: str, name: str, value: str) -> None:
    with open(path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def main() -> None:
    try:
        build = parse_matrix(os.environ.get("BUILD_MATRIX", "[]"), "BUILD_MATRIX")
        verify = parse_matrix(os.environ.get("VERIFY_MATRIX", "[]"), "VERIFY_MATRIX")

        if verify:
            result = reconcile(
                build,
                verify,
                required_env("OWNER").strip().lower(),
                required_env("GITHUB_ACTOR"),
                required_env("GITHUB_TOKEN"),
            )
        else:
            result = {"build": build, "verify": verify}

        build_json = json.dumps(result["build"], separators=(",", ":"))
        verify_json = json.dumps(result["verify"], separators=(",", ":"))
    except (ReconcileError, ReleaseConfigError, OSError) as error:
        print(f"::error::Unable to reconcile verify matrix: {error}")
        sys.exit(1)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        write_output(output_path, "build_matrix", build_json)
        write_output(output_path, "verify_matrix", verify_json)
    else:
        print(f"build_matrix={build_json}")
        print(f"verify_matrix={verify_json}")

    print(f"Build matrix: {build_json}")
    print(f"Verify matrix: {verify_json}")


if __name__ == "__main__":
    main()
