import pytest

from release_config import ReleaseConfigError
from set_image_names import image_names

pytestmark = pytest.mark.unit


def test_image_names_returns_release_and_alias():
    assert image_names("Owner", "error-pages", "v1.2.3", "42", "2") == {
        "name": "ghcr.io/owner/error-pages",
        "release_tag": "v1.2.3-42-2",
        "alias": "v1.2.3",
        "artifact": "image-error-pages",
    }


@pytest.mark.parametrize(
    ("owner", "image", "version"),
    [
        ("-bad", "example", "v1"),
        ("owner", "Bad", "v1"),
        ("owner", "example", "bad space"),
    ],
)
def test_image_names_rejects_invalid_values(owner, image, version):
    with pytest.raises(ReleaseConfigError):
        image_names(owner, image, version, "1", "1")


def test_image_names_rejects_overlong_release_tag():
    with pytest.raises(ReleaseConfigError):
        image_names("owner", "example", "a" * 128, "1", "1")


def test_cli_writes_outputs(run_script, github_output):
    result = run_script("set_image_names.py", "Owner", "example", "v1.2.3")
    assert result.returncode == 0, result.stderr
    assert github_output.read_text() == (
        "name=ghcr.io/owner/example\n"
        "release_tag=v1.2.3-42-1\n"
        "alias=v1.2.3\n"
        "artifact=image-example\n"
    )


def test_cli_appends_outputs(run_script, github_output):
    github_output.write_text("existing=value\n")
    result = run_script("set_image_names.py", "owner", "example", "v1")
    assert result.returncode == 0, result.stderr
    assert github_output.read_text().startswith("existing=value\n")


def test_cli_requires_run_environment(run_script, monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)
    result = run_script(
        "set_image_names.py",
        "owner",
        "example",
        "v1",
        env={"GITHUB_RUN_NUMBER": ""},
    )
    assert result.returncode == 1
    assert "GITHUB_RUN_NUMBER" in result.stdout


def test_cli_rejects_non_numeric_run_number(run_script):
    result = run_script(
        "set_image_names.py",
        "owner",
        "example",
        "v1",
        env={"GITHUB_RUN_NUMBER": "abc"},
    )
    assert result.returncode == 1
    assert "numeric" in result.stdout


def test_cli_requires_three_arguments(run_script):
    result = run_script("set_image_names.py", "owner")
    assert result.returncode == 2
