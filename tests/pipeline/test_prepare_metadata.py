import json
from datetime import datetime, timezone

import pytest

import prepare_metadata
from helpers import commit_all
from prepare_metadata import (
    MetadataError,
    build_metadata,
    upstream_revision,
    write_multiline_output,
    write_output,
)

pytestmark = pytest.mark.unit


def metadata_repo(git_repo):
    (git_repo / "file.txt").write_text("content\n", encoding="utf-8")
    revision = commit_all(git_repo, "initial")
    return git_repo, revision


def test_build_metadata_formats_labels_and_annotations(git_repo):
    repo, revision = metadata_repo(git_repo)
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    actual_revision, labels, annotations = build_metadata(
        workspace=repo,
        upstream_source=".",
        release_metadata=json.dumps(
            {"org.opencontainers.image.title": "Example"}
        ),
        upstream_version="v1.2.3",
        container_source="https://github.com/owner/images",
        container_vendor="owner",
        now=now,
    )

    assert actual_revision == revision
    assert labels.splitlines() == [
        "org.opencontainers.image.created=2026-01-02T03:04:05Z",
        f"org.opencontainers.image.revision={revision}",
        "org.opencontainers.image.source=https://github.com/owner/images",
        "org.opencontainers.image.title=Example",
        "org.opencontainers.image.vendor=owner",
        "org.opencontainers.image.version=v1.2.3",
    ]
    expected_annotations = []
    for line in labels.splitlines():
        expected_annotations.append(f"index:{line}")
        expected_annotations.append(f"manifest:{line}")

    assert annotations.splitlines() == expected_annotations


def test_build_metadata_rejects_source_outside_workspace(git_repo):
    repo, _ = metadata_repo(git_repo)
    with pytest.raises(MetadataError, match="inside GITHUB_WORKSPACE"):
        build_metadata(
            workspace=repo,
            upstream_source="../outside",
            release_metadata="{}",
            upstream_version="v1",
            container_source="https://github.com/owner/images",
            container_vendor="owner",
        )


@pytest.mark.parametrize("value", ["not json", "[]", '{"a": 1}', '{"a": "x\\ny"}'])
def test_build_metadata_rejects_invalid_release_metadata(git_repo, value):
    repo, _ = metadata_repo(git_repo)
    with pytest.raises(MetadataError):
        build_metadata(
            workspace=repo,
            upstream_source=".",
            release_metadata=value,
            upstream_version="v1",
            container_source="https://github.com/owner/images",
            container_vendor="owner",
        )


def test_upstream_revision_rejects_missing_directory(tmp_path):
    with pytest.raises(MetadataError, match="does not exist"):
        upstream_revision(tmp_path / "missing")


def test_upstream_revision_rejects_non_repository(tmp_path):
    with pytest.raises(MetadataError, match="Unable to read upstream revision"):
        upstream_revision(tmp_path)


def test_write_outputs(github_output, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    write_output("revision", "abc")
    write_multiline_output("labels", "a=b\nc=d")

    content = github_output.read_text()
    assert "revision=abc\n" in content
    assert "labels<<EOF_" in content
    assert "a=b\nc=d\n" in content


def test_main_writes_outputs(git_repo, github_output, monkeypatch, capsys):
    repo, revision = metadata_repo(git_repo)
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repo))
    monkeypatch.setenv("UPSTREAM_SOURCE", ".")
    monkeypatch.setenv(
        "RELEASE_METADATA",
        json.dumps({"org.opencontainers.image.title": "Example"}),
    )
    monkeypatch.setenv("UPSTREAM_VERSION", "v1.2.3")
    monkeypatch.setenv("CONTAINER_SOURCE", "https://github.com/owner/images")
    monkeypatch.setenv("CONTAINER_VENDOR", "owner")

    prepare_metadata.main()

    content = github_output.read_text()
    assert f"revision={revision}\n" in content
    assert "labels<<EOF_" in content
    assert "annotations<<EOF_" in content
    assert "index:org.opencontainers.image.version=v1.2.3\n" in content
    assert "manifest:org.opencontainers.image.version=v1.2.3\n" in content
    assert capsys.readouterr().err == ""


def test_main_reports_missing_environment(monkeypatch, capsys):
    monkeypatch.delenv("RELEASE_METADATA", raising=False)

    with pytest.raises(SystemExit) as error:
        prepare_metadata.main()

    assert error.value.code == 1
    assert "::error::" in capsys.readouterr().out
