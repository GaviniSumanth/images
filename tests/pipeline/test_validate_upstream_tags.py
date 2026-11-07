import subprocess

import pytest

import validate_upstream_tags
from validate_upstream_tags import UpstreamError, select_entries, validate_tag

pytestmark = pytest.mark.unit

ENTRY = {
    "repository": "https://github.com/owner/example",
    "version": "v1.2.3",
    "image": "example",
}


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_validate_tag_accepts_existing_tag():
    def runner(command, **kwargs):
        assert command[:3] == ["git", "ls-remote", "--tags"]
        assert command[-1] == "refs/tags/v1.2.3"
        return completed(stdout="abc\trefs/tags/v1.2.3\n")

    validate_tag(ENTRY, runner=runner)


def test_validate_tag_reports_missing_tag():
    def runner(command, **kwargs):
        return completed(stdout="")

    with pytest.raises(UpstreamError, match="does not exist"):
        validate_tag(ENTRY, runner=runner)


def test_validate_tag_reports_unreachable_repository():
    def runner(command, **kwargs):
        return completed(returncode=128, stderr="fatal: unable to access")

    with pytest.raises(UpstreamError, match="Unable to reach"):
        validate_tag(ENTRY, runner=runner)


def test_validate_tag_reports_timeout():
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    with pytest.raises(UpstreamError, match="Timed out"):
        validate_tag(ENTRY, runner=runner)


def test_validate_tag_reports_os_error():
    def runner(command, **kwargs):
        raise OSError("git missing")

    with pytest.raises(UpstreamError, match="Unable to run git"):
        validate_tag(ENTRY, runner=runner)


def test_select_entries_returns_all_by_default(monkeypatch):
    other = {**ENTRY, "image": "other", "repository": "https://github.com/o/other"}
    monkeypatch.setattr(
        validate_upstream_tags, "load_repositories", lambda: [ENTRY, other]
    )
    assert select_entries([]) == [ENTRY, other]


def test_select_entries_filters_by_image(monkeypatch):
    other = {**ENTRY, "image": "other", "repository": "https://github.com/o/other"}
    monkeypatch.setattr(
        validate_upstream_tags, "load_repositories", lambda: [ENTRY, other]
    )
    assert select_entries(["other"]) == [other]


def test_select_entries_rejects_unknown_image(monkeypatch):
    monkeypatch.setattr(
        validate_upstream_tags, "load_repositories", lambda: [ENTRY]
    )
    with pytest.raises(UpstreamError, match="Unknown image"):
        select_entries(["missing"])
