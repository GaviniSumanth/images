# AGENTS.md

This repository builds hardened OCI images for upstream applications. It does
not vendor or modify upstream application source: each image is built from an
exact upstream release tag using a `Containerfile` that lives here, then tested,
scanned, and published to GHCR.

Read this before changing anything. If a change conflicts with these rules, stop
and ask instead of silently relaxing them.

## Hard invariants

1. **No image may define a `HEALTHCHECK`.** Readiness is tested externally by
   the pytest suites. Do not add a `HEALTHCHECK` as a convenience.
2. **Only `linux/amd64` is built and published.** Do not add QEMU, arm64
   matrices, or multi-platform manifests.
3. **Runtime containers run as `1000:1000`.** Do not change this UID/GID or add
   a different runtime user.
4. **Keep runtime images minimal.** Add only packages, files, and libraries the
   application actually needs at runtime. Copy dependencies into a hardened
   runtime stage instead of using a general-purpose runtime image.
5. **Never modify upstream application logic.** Changes belong in the
   `Containerfile`, the test suite, `releases.json`, or CI scripts. Do not patch
   upstream source to make a build pass unless explicitly asked.
6. **`releases.json` is the single source of truth** for the upstream
   repository, exact version tag, Containerfile path, image name, and upstream
   OCI metadata. Do not duplicate those values elsewhere.
7. **Base image digests belong to Renovate.** Do not hand-edit digest pins.
   Renovate also updates `releases.json` versions through its `custom.jsonata`
   manager.
8. **Pipeline logic is Python, not shell.** Do not add `.sh` scripts or inline
   `bash` to workflows. Use `.github/scripts/*.py`.
9. **Do not weaken or delete tests** to get a green result. Tests are the
   contract for runtime behavior, metadata, and non-root execution.
10. **Do not publish test images to production tags.** Each build gets an
    immutable `vX.Y.Z-<run_number>-<run_attempt>` tag, and the mutable `vX.Y.Z`
    alias moves only after the tested and scanned OCI archive is published. No
    candidate tags are created.
11. **Never invent OCI metadata.** Use authoritative upstream values. Do not
    use placeholders, guessed licenses, or made-up documentation URLs.
12. **Never commit secrets or print credentials.** CI receives registry
    credentials from GitHub secrets.

## Repository map

| Path | Purpose |
| --- | --- |
| `releases.json` | Image matrix and upstream version/metadata pins. |
| `images/<image>/Containerfile` | Per-image build definition. |
| `images/<image>/Containerfile.dockerignore` | Required build-context exclusions. |
| `tests/images/test_<image>.py` | Required Docker integration suite, with hyphens normalized to underscores. |
| `tests/images/container_test_common.py` | Shared Docker SDK helpers: image contract, cleanup, readiness polling. |
| `tests/image_contract.py` | Expected runtime user and exposed ports per image. |
| `tests/pipeline/` | Fast, offline unit tests for pipeline scripts and repository structure. |
| `tests/containerfiles/` | Static Containerfile checks and generic or per-image pre-build validation tests. |
| `tests/requirements-test.txt` | Pinned test dependencies. |
| `pyproject.toml` | Pytest paths, import roots, and markers. |
| `.github/scripts/` | Python CI helpers and validators. |
| `.github/changelog.toml` | Git-cliff template and commit grouping rules. |
| `.github/workflows/build-container.yml` | Validation, unit tests, change detection, and pipeline dispatch. |
| `.github/workflows/container-pipeline.yml` | Reusable build, test, scan, publish, and verify workflow. |
| `.github/workflows/changelog.yml` | Changelog generation and pull-request publishing. |
| `.github/workflows/renovate.yml` | Scheduled Renovate runs. |
| `renovate.json` | Dependency update policy. |

Current images: `audiobookshelf`, `lldap`, `authelia`, `error-pages`. Upstream
versions are intentionally not repeated here; read `releases.json`.

## `releases.json` contract

The canonical shape is:

```json
{
  "repositories": [
    {
      "repository": "https://github.com/owner/name",
      "version": "v1.2.3",
      "containerfile": "images/image/Containerfile",
      "image": "image",
      "metadata": {
        "org.opencontainers.image.title": "Upstream name",
        "org.opencontainers.image.description": "Short description",
        "org.opencontainers.image.url": "https://upstream.example/",
        "org.opencontainers.image.documentation": "https://upstream.example/docs/",
        "org.opencontainers.image.licenses": "SPDX-identifier"
      }
    }
  ]
}
```

Rules enforced by `.github/scripts/validate_releases.py` and
`release_config.py`:

- `repository` must be exactly `https://github.com/<owner>/<name>`.
  No credentials, ports, query strings, fragments, or `.git` suffixes.
- `version` must be an exact upstream tag that exists on the remote.
- `containerfile` must match `images/<directory>/Containerfile` and exist locally.
- `image` must be lowercase and unique.
- Repository slugs must be unique, case-insensitively.
- Required metadata: `title`, `description`, `url`, `documentation`, and
  `licenses`. All values must be non-empty single-line strings.
- Allowed metadata keys are limited to the OCI keys in `validate_releases.py`.
  Do not add arbitrary keys.
- Do not put pipeline-owned values in `releases.json`
  (`org.opencontainers.image.version`, `.source`, `.vendor`, `.created`,
  `.revision`). CI injects and overwrites them.

## CI pipeline

`build-container.yml` runs on pushes to `main` affecting release files,
Containerfiles, `.dockerignore` files, `tests/`, `pyproject.toml`, or CI
scripts, and on manual dispatch.

1. **Normalize owner**: lowercases and validates the GitHub owner.
2. **Validate releases**: schema, URLs, uniqueness, required metadata.
3. **Validate images**: Containerfile paths, per-image `.dockerignore` and
   integration test files, directory/image name agreement, and that `_shared/`
   is gone.
4. **Run unit tests**: `pytest -m unit` covers pipeline scripts and static
   Containerfile checks without Docker or network access.
5. **Detect changes**: produces a `build` matrix for images that must be
   rebuilt and a `verify` matrix for images whose published alias only needs
   re-testing. Any invalid or nonexistent `before` revision means "rebuild
   everything". An invalid `current` revision must fail clearly.
6. **Dispatch** the reusable pipeline only when either matrix is non-empty.

`container-pipeline.yml` runs per matrix entry:

1. **Build**: checks out this repo into `build/` and the upstream tag into
   `source/`. The upstream checkout is the build context; the Containerfile
   comes from `build/`. The job validates the exact upstream tag, runs the
   matrix-selected pre-build validation suite for the image, and builds
   `linux/amd64` once into an OCI archive with `APP_VERSION`, `APP_REVISION`,
   SBOM, and provenance. Before upload, `normalize_oci_archive.py` adds skopeo's
   `io.github.containers.compression.zstd` annotation to index descriptors for
   images with zstd layers; without it, older skopeo versions rewrite the index
   and `skopeo copy --preserve-digests` refuses to publish. It never pushes. A
   per-image pre-build test may live in
   `tests/containerfiles/test_<image>_prebuild.py`; the matrix selects it when
   present and otherwise runs the generic `tests/containerfiles/test_prebuild.py`.
   Do not add image-name conditionals to workflows.
2. **Test**: downloads the same OCI archive, converts and loads it with
   `skopeo`, installs `tests/requirements-test.txt`, and runs
   `tests/images/test_<image>.py` with `TEST_IMAGE` set.
3. **Scan**: loads the same archive and runs Trivy on OS packages only, failing
   on fixable `CRITICAL`/`HIGH` findings. Library-vulnerability scanning is out
   of scope.
4. **Publish**: only after test and scan pass, pushes the untouched archive
   with `skopeo`, preserving its digest. It creates the immutable release tag
   and moves the mutable alias, then verifies the published index, manifests,
   and labels. Do not rebuild during publish.
5. **Verify**: for images in the verify matrix, pulls the published alias and
   re-runs the integration suite without rebuilding.

### Change detection rules

A single image rebuilds when:

- Its `releases.json` entry changes (version, Containerfile, image, metadata),
- Its Containerfile or `.dockerignore` changes, or
- A full rebuild is requested because the previous revision is unknown.

A single image is verified without rebuilding when:

- Its `tests/images/test_<image>.py` changes,
- Shared test files, `pyproject.toml`, `.github/scripts/`, or either workflow
  change, or
- A shared helper under `tests/images/` changes.

A new image or a changed upstream repository URL builds that image. A force
push or unreadable previous configuration rebuilds everything. Keep this
behavior; it prevents stale images being left behind.

Before dispatch, `reconcile_verify.py` checks each verify entry's published
`vX.Y.Z` alias in GHCR. An entry whose alias is missing (for example because an
earlier build failed before publish) is promoted to the build matrix and
rebuilt instead of being verified. Registry or authentication errors fail the
detection job closed.

## Changelog workflow

`changelog.yml` runs on pushes to `main` and on manual dispatch. It is split so
that untrusted generated data never runs as code with a write token:

1. **Generate** (`contents: read`): checks out full history without persisted
   credentials, installs the pinned `git-cliff` release with the pinned
   `taiki-e/install-action`, and runs
   `.github/scripts/generate_changelogs.py`. The generator uses Git-cliff's
   structured context, groups commits into one section per UTC commit date,
   renders the repository changelog and one changelog per image, and uploads
   only `CHANGELOG.md` and `changelogs/` as an artifact.
2. **Publish** (`contents: write`, `pull-requests: write`): checks out trusted
   repository code at `github.sha`, downloads the artifact into the runner
   temporary directory, and runs
   `.github/scripts/publish_changelogs.py`. The artifact is treated as data:
   the script rejects symlinks, unexpected entries, non-UTF-8 or empty files,
   and invalid image names; it copies only validated `CHANGELOG.md` and
   `changelogs/*.md` files, removes stale image changelogs, and stages only
   those paths.
3. It commits to `automation/changelogs`, pushes with `--force-with-lease` after
   checking the remote branch, and creates or updates a pull request against the
   default branch. It must never push directly to `main`.

`CHANGELOG.md` is generated from the repository history; do not hand-edit it or
the files under `changelogs/`. Run `python3 .github/scripts/generate_changelogs.py`
locally with `git-cliff` on `PATH` to refresh them. The template lives in
`.github/changelog.toml`; it uses the `__REPOSITORY_URL__` placeholder so the
repository URL is not hardcoded, groups sections by UTC commit date, and skips
`docs(changelog)`/`chore(changelog)` commits to avoid feedback loops. The
workflow commit uses the `docs(changelog):` prefix for that reason.

## Containerfile conventions

- Start with the repository's pinned `# syntax=docker/dockerfile:1@sha256:...`
  line where present.
- Use Docker Hardened Images (`dhi.io/...`) or `scratch` for runtime stages,
  with digest pins managed by Renovate.
- Build on `$BUILDPLATFORM` when a stage does not need the target architecture;
  only compile target-specific artifacts in target-platform stages.
- Prefer multi-stage builds. Collect required binaries and shared libraries in a
  staging stage, then copy the minimal root filesystem into the runtime.
- Use `ldd` checks to fail the build when a copied binary has unresolved
  libraries. Do not copy a shell or package manager into a distroless runtime.
- Copy only required certificates, timezone data, and runtime libraries.
- Set `USER 1000:1000` before `ENTRYPOINT`/`CMD`.
- Declare `EXPOSE` for the real listening port.
- Never add `HEALTHCHECK`.
- Do not add `LABEL` blocks for OCI metadata. CI supplies labels and
  annotations at build time.

## Test conventions

- Every image requires `tests/images/test_<image>.py`, with hyphens in the
  image name replaced by underscores; the validator fails without it.
- Integration tests run against `TEST_IMAGE` and use the Docker SDK through
  `tests/images/container_test_common.py`.
- Every suite must call `check_image_contract()` so the `1000:1000` user,
  absence of `HEALTHCHECK`, OCI labels, and exposed ports are verified.
- Use `wait_for_container()` for readiness. It fails fast if the container
  exits and reports logs on timeout.
- Poll the application's HTTP endpoint or use its own healthcheck command.
  Never rely on a Docker `HEALTHCHECK`.
- Always use `managed_container()` or `remove=True` so failed tests do not leak
  containers.
- Bind published ports to `127.0.0.1` with an ephemeral host port.
- Tests must be deterministic, use generated secrets, and leave no state on the
  host.
- Keep fast unit tests in `tests/pipeline/` and `tests/containerfiles/`. They
  must not require Docker, network access, or a registry.
- Pre-build validation tests live in `tests/containerfiles/`. The generic
  `test_prebuild.py` runs for every image; an image may add
  `test_<image>_prebuild.py`, which the change matrix selects automatically.

## Image-specific notes

- **audiobookshelf**: runtime needs `ffmpeg`, `ffprobe`, `tzdata`/zoneinfo, and
  the NuSQLite library. The FFmpeg contract is exercised by
  `tests/images/assets/test-ffmpeg-runtime.cjs`; audio and image handling is in
  scope, video is not. Readiness is polled at `/healthcheck`.
  `tests/containerfiles/test_audiobookshelf_prebuild.py` compares the NuSQLite
  download with the official upstream Dockerfile; `test_nusqlite_parity.py`
  covers the parser and the current pin. It currently records a known
  divergence: this repo pins `mikiher/nunicode-binaries` with a SHA-256, while
  upstream pins `mikiher/nunicode-sqlite` without one. Any change to either side
  fails the test so the difference is reviewed. Do not change the pin without
  an explicit request.
- **authelia**: the binary is built with version, state, and revision ldflags so
  `build-info` reports `State: tagged clean`. Runtime is distroless with config
  under `/config`; it must have no `HEALTHCHECK`. Integration tests generate a
  valid configuration and users database, run `config validate`, start the
  server, poll `/api/health` for `{"status":"OK"}`, and assert the SQLite
  database was created.
- **lldap**: `/app/lldap-entrypoint` seeds `/data/lldap_config.toml` from the
  template when the directory is empty, then execs the real binary. Keep the
  empty-bind-mount test working.
- **error-pages**: runs from `scratch` with CA certificates and `/tmp`, serves
  on port `8080`, and supports HTML/JSON/XML/plain-text error responses.

## Task playbooks

### Update an existing image

1. Change only the `version` field in `releases.json` unless the upstream build
   contract changed.
2. Verify the tag exists exactly as written.
3. Review upstream changes that affect runtime dependencies, build steps, ports,
   or configuration.
4. Update the Containerfile and `tests/images/test_<image>.py` only when
   behavior changed.
5. Run the validators below. Do not edit base image digests; let Renovate
   update them.

### Add a new image

1. Create `images/<image>/Containerfile` and
   `images/<image>/Containerfile.dockerignore`.
2. Add one `releases.json` entry with a unique lowercase image name, unique
   upstream repository, exact tag, and complete OCI metadata.
3. Add `tests/images/test_<image>.py` covering the image contract and real
   readiness/behavior.
4. Add `tests/containerfiles/test_<image>_prebuild.py` only when the image
   needs upstream-specific pre-build checks; otherwise the generic
   `tests/containerfiles/test_prebuild.py` is used.
5. Add the expected exposed ports to `tests/image_contract.py`.
6. Do not edit workflows; the matrix is discovered from `releases.json`.
7. Run every validator below.
8. Confirm the runtime is minimal, has no `HEALTHCHECK`, and uses
   `1000:1000`.

### Change pipeline scripts

- Use Python 3 and the standard library unless a dependency is clearly
  justified.
- Reuse parsing and validation from `release_config.py`.
- Fail closed with a clear `::error::...` message and a nonzero exit code.
- Never shell out with unquoted user input; pass argv lists to `subprocess`.
- Keep `detect_changes.py` behavior intact: full rebuild on unknown/initial
  revisions, per-image rebuild for relevant changes, per-image verification for
  test-only changes, NUL-delimited `git diff`, and clear failure for an invalid
  current revision.
- Keep `validate_upstream_tags.py` distinguishing a missing tag from an
  unreachable remote, and keep the `ls-remote` timeout.
- Keep metadata output multiline-safe; `prepare_metadata.py` uses a random
  heredoc delimiter for a reason.
- Publish only the archive that was tested and scanned. `publish_image.py`
  must keep its immutable-tag collision check, attestation check, digest
  verification, and label verification.
- Preserve the `BEFORE`/`CURRENT` environment-variable contract used by the
  workflow, as well as optional argv support.
- Keep changelog generation deterministic: one Git process for changed paths,
  no hardcoded repository URL, and no `GIT_CLIFF_BIN` path coupling. The
  workflow installs Git-cliff on `PATH`; `GIT_CLIFF_BIN` is only a local
  override.
- Treat the downloaded changelog artifact as untrusted data. `publish_changelogs.py`
  must keep its artifact-tree validation, symlink rejection, generated-path-only
  staging, `--force-with-lease` update, and pull-request flow. Never commit
  changelogs directly to `main`.

## Validation

Run the validators before declaring work complete. These are the same checks CI
performs; they do not require building an image:

| Command | Checks |
| --- | --- |
| `python3 -m pytest -m unit` | Pipeline scripts, workflow shape, repository structure, and static Containerfile invariants. |
| `python3 .github/scripts/validate_releases.py` | `releases.json` schema, URLs, uniqueness, metadata. |
| `python3 .github/scripts/validate_images.py` | Containerfiles, `.dockerignore` files, test entrypoints, and directory naming. |
| `python3 .github/scripts/validate_upstream_tags.py [image ...]` | Exact upstream tags (network required). |
| `python3 .github/scripts/detect_changes.py <before> <current>` | Build and verify matrix calculation. |
| `python3 .github/scripts/validate_test_config.py <image>` | Test entrypoint and requirements exist. |
| `python3 -m py_compile .github/scripts/*.py tests/*.py tests/*/*.py` | Python syntax. |

Also parse changed YAML/JSON files and run `git diff --check`. If a validator
cannot run because of network or credentials, say so explicitly; do not claim it
passed.

## Definition of done

- `releases.json` remains the only version source and validates.
- Upstream tag exists and matches the declared `version` exactly.
- Containerfile builds for `linux/amd64`, uses a minimal runtime, and runs as
  `1000:1000`.
- No image defines `HEALTHCHECK`.
- Tests cover non-root execution and real readiness; new behavior has a test.
- OCI metadata is accurate; no placeholders or invented values.
- Every publish uses an immutable `vX.Y.Z-<run_number>-<run_attempt>` tag; the
  mutable `vX.Y.Z` alias moves only after tests and scans pass.
- No manual digest pinning and no shell pipeline scripts.
- Validators pass, or any environmental limitation is reported honestly.
- Changes stay focused; do not refactor unrelated images or workflows.

## When something is unclear

Ask rather than guess, especially about upstream versions, licenses,
documentation URLs, runtime user changes, or publishing behavior. If an upstream
value cannot be verified, report it instead of inventing one.
