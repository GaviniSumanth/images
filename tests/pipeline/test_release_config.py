import json

import pytest

import release_config
from release_config import (
    ReleaseConfigError,
    github_slug,
    load_repositories,
    release_tag,
    repositories_from_data,
    image_test_file,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/name",
        "https://github.com/owner/name/",
        "https://github.com/Owner/Name.with-dots_1",
    ],
)
def test_github_slug_accepts_valid_urls(url):
    assert github_slug(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        42,
        "http://github.com/owner/name",
        "https://gitlab.com/owner/name",
        "https://user:pass@github.com/owner/name",
        "https://github.com/owner/name?x=1",
        "https://github.com/owner/name#frag",
        "https://github.com/owner/name/extra",
        "https://github.com/owner/name.git",
        "https://github.com/owner",
        "https://github.com/owner/",
        "https://github.com/-bad/name",
        "https://github.com/owner/bad name",
    ],
)
def test_github_slug_rejects_invalid_urls(url):
    with pytest.raises(ReleaseConfigError):
        github_slug(url)


def test_github_slug_returns_slug():
    assert github_slug("https://github.com/Owner/Project") == "Owner/Project"


def test_repositories_from_data_supports_object_and_list():
    entries = [{"image": "example"}]
    assert repositories_from_data({"repositories": entries}) == entries
    assert repositories_from_data(entries) == entries
    assert repositories_from_data("nope") is None


def test_load_repositories_reads_object(tmp_path):
    path = tmp_path / "releases.json"
    path.write_text(json.dumps({"repositories": [{"image": "example"}]}))
    assert load_repositories(path) == [{"image": "example"}]


def test_load_repositories_reads_list(tmp_path):
    path = tmp_path / "releases.json"
    path.write_text(json.dumps([{"image": "example"}]))
    assert load_repositories(path) == [{"image": "example"}]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{}",
        '{"repositories": []}',
        '{"repositories": "nope"}',
        '{"repositories": [1]}',
        "not json",
    ],
)
def test_load_repositories_rejects_invalid_documents(tmp_path, content):
    path = tmp_path / "releases.json"
    path.write_text(content)
    with pytest.raises(ReleaseConfigError):
        load_repositories(path)


def test_load_repositories_rejects_missing_file(tmp_path):
    with pytest.raises(ReleaseConfigError):
        load_repositories(tmp_path / "missing.json")


def test_test_file_name_normalizes_hyphens():
    assert image_test_file("error-pages") == "test_error_pages.py"


def test_release_tag_is_immutable():
    assert release_tag("v1.2.3", "42", "2") == "v1.2.3-42-2"


@pytest.mark.parametrize(("number", "attempt"), [("x", "1"), ("1", "x")])
def test_release_tag_requires_numeric_run_values(number, attempt):
    with pytest.raises(ReleaseConfigError):
        release_tag("v1.2.3", number, attempt)


def test_release_tag_rejects_overlong_tags():
    with pytest.raises(ReleaseConfigError):
        release_tag("a" * 128, "1", "1")


def test_required_env_uses_typed_error(monkeypatch):
    monkeypatch.delenv("MISSING_TEST_VALUE", raising=False)

    with pytest.raises(ReleaseConfigError):
        release_config.required_env("MISSING_TEST_VALUE")

    with pytest.raises(ValueError):
        release_config.required_env("MISSING_TEST_VALUE", ValueError)
