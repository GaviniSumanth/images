# Hardened container images

This repository builds hardened OCI images for upstream applications. Each image
is built from an exact upstream release tag with a `Containerfile` kept here, then
tested, scanned, and published to GitHub Container Registry.

Current images: `audiobookshelf`, `authelia`, `error-pages`, `lldap`, and
`qbittorrent`. Pinned upstream versions and OCI metadata live in `releases.json`,
which is the single source of truth.

## Image invariants

- Only `linux/amd64` is built and published.
- Runtime containers run as `1000:1000`.
- Runtime images are minimal and use Docker Hardened Images or `scratch`.
- No image defines a `HEALTHCHECK`; readiness is verified by the test suite.
- Base image digests are updated by Renovate, not by hand.

## Layout

| Path | Purpose |
| --- | --- |
| `releases.json` | Upstream repository, version, Containerfile, image name, and metadata pins. |
| `<image>/Containerfile` | Per-image build definition and build-context exclusions. |
| `tests/pipeline/` | Fast, offline tests for the CI scripts and repository structure. |
| `tests/containerfiles/` | Static checks for Containerfile invariants and upstream parity. |
| `tests/images/` | Docker integration tests, one file per published image. |
| `.github/scripts/` | Python helpers for validation, metadata, build detection, and publishing. |

## Pipeline

`build-container.yml` validates the release configuration, runs the offline unit
tests, and calculates two matrices: images that need a rebuild and images whose
existing release only needs verification. Before dispatch, it checks each
verify entry's published alias in GHCR; if the alias is missing (for example
because an earlier build failed before publish), that image is moved to the
build matrix and rebuilt instead of being verified.

`container-pipeline.yml` runs a pre-build validation test for every image, then
builds each changed image once into an OCI archive. The matrix selects an
optional `tests/containerfiles/test_<image>_prebuild.py` file and falls back to
the generic `tests/containerfiles/test_prebuild.py`; the workflow does not branch
on image names. Before upload, the archive is normalized so that skopeo's zstd
compression annotation is already present and `--preserve-digests` can publish
the tested index unchanged. The archive is uploaded as an artifact and then
loaded for integration tests and a Trivy OS-package scan. Only after both pass is the same
archive pushed to GHCR with `skopeo`, preserving its digest. No candidate tags
are published.

Every build gets an immutable tag of the form `vX.Y.Z-<run_number>-<run_attempt>`.
The mutable `vX.Y.Z` alias is moved only after the tested and scanned archive is
published.

## Local validation

```sh
python3 -m pip install -r tests/requirements-test.txt
python3 -m pytest -m unit
python3 .github/scripts/validate_releases.py
python3 .github/scripts/validate_images.py
python3 -m py_compile .github/scripts/*.py tests/*.py tests/*/*.py
```

Integration tests require Docker and a built image:

```sh
TEST_IMAGE=ghcr.io/owner/image:vX.Y.Z python3 -m pytest -m integration
```

## Adding or updating an image

1. Update only the `version` field in `releases.json` for a routine upstream bump.
2. Add `<image>/Containerfile`, `<image>/Containerfile.dockerignore`, and
   `tests/images/test_<image>.py` for a new image.
3. Keep upstream application source unmodified; changes belong in the
   Containerfile, tests, `releases.json`, or CI scripts.
4. Run the local validation commands above.
