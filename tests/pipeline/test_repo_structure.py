from pathlib import Path

import pytest

from release_config import load_repositories, image_test_file

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORIES = load_repositories()


def test_shared_directory_is_removed():
    assert not (REPO_ROOT / "_shared").exists()


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_release_has_containerfile_and_ignore(entry):
    containerfile = REPO_ROOT / entry["containerfile"]
    assert containerfile.is_file()
    assert containerfile.with_name(f"{containerfile.name}.dockerignore").is_file()


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_release_has_integration_test(entry):
    test_file = REPO_ROOT / "tests" / "images" / image_test_file(entry["image"])
    assert test_file.is_file()


def test_no_orphan_image_directories():
    image_directories = {
        path.parent.name for path in REPO_ROOT.glob("*/Containerfile")
    }
    assert image_directories == {entry["image"] for entry in REPOSITORIES}


def test_requirements_and_project_config_exist():
    assert (REPO_ROOT / "tests" / "requirements-test.txt").is_file()
    assert (REPO_ROOT / "pyproject.toml").is_file()


def test_generic_prebuild_test_exists():
    assert (REPO_ROOT / "tests" / "containerfiles" / "test_prebuild.py").is_file()


def test_no_shell_scripts():
    assert list(REPO_ROOT.rglob("*.sh")) == []


def test_releases_json_has_no_packaging_revision_field():
    assert "container_release" not in (REPO_ROOT / "releases.json").read_text()


def test_image_tests_do_not_reference_shared():
    for test_file in (REPO_ROOT / "tests" / "images").glob("test_*.py"):
        assert "_shared" not in test_file.read_text(), test_file


def test_readme_is_not_empty():
    assert len((REPO_ROOT / "README.md").read_text().strip()) > 80
