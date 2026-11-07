import copy
import json

import pytest

import detect_changes
from detect_changes import (
    FULL_REBUILD,
    PREBUILD_TEST_FALLBACK,
    build_required,
    build_matrices,
    changed_files,
    matrices_for,
    prebuild_test_file,
    verify_required,
)
from helpers import commit_all, write_json

pytestmark = pytest.mark.unit

REPOSITORIES = [
    {
        "repository": "https://github.com/owner/a",
        "version": "v1.0.0",
        "containerfile": "a/Containerfile",
        "image": "a",
        "metadata": {"org.opencontainers.image.title": "A"},
    },
    {
        "repository": "https://github.com/owner/b",
        "version": "v2.0.0",
        "containerfile": "b/Containerfile",
        "image": "b",
        "metadata": {"org.opencontainers.image.title": "B"},
    },
]


def repositories():
    return copy.deepcopy(REPOSITORIES)


def test_no_changes_produces_empty_matrices():
    assert matrices_for(repositories(), repositories(), []) == {
        "build": [],
        "verify": [],
    }


def test_full_rebuild_builds_everything():
    result = matrices_for(repositories(), repositories(), [FULL_REBUILD])
    assert [entry["image"] for entry in result["build"]] == ["a", "b"]
    assert result["verify"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "v1.1.0"),
        ("containerfile", "new/Containerfile"),
        ("image", "new"),
        ("metadata", {"org.opencontainers.image.title": "New"}),
    ],
)
def test_release_changes_build_only_that_image(field, value):
    current = repositories()
    current[0][field] = value
    result = matrices_for(current, repositories(), ["releases.json"])
    expected_image = "new" if field == "image" else "a"
    assert [entry["image"] for entry in result["build"]] == [expected_image]


def test_new_image_is_built():
    current = repositories()
    new = copy.deepcopy(REPOSITORIES[1])
    new.update(
        {
            "repository": "https://github.com/owner/c",
            "image": "c",
            "containerfile": "c/Containerfile",
        }
    )
    current.append(new)
    result = matrices_for(current, repositories(), ["releases.json"])
    assert [entry["image"] for entry in result["build"]] == ["c"]


def test_removed_image_is_not_built():
    result = matrices_for(repositories()[:1], repositories(), ["releases.json"])
    assert result == {"build": [], "verify": []}


@pytest.mark.parametrize(
    "path",
    [
        "a/Containerfile",
        "a/Containerfile.dockerignore",
        "a/assets/config/default.conf",
    ],
)
def test_containerfile_changes_build_that_image(path):
    result = matrices_for(repositories(), repositories(), [path])
    assert [entry["image"] for entry in result["build"]] == ["a"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/images/container_test_common.py",
        "tests/image_contract.py",
        "tests/requirements-test.txt",
        "pyproject.toml",
        "tests/images/assets/test-ffmpeg-runtime.cjs",
        ".github/scripts/detect_changes.py",
        ".github/workflows/build-container.yml",
        ".github/workflows/container-pipeline.yml",
    ],
)
def test_shared_changes_verify_all_images(path):
    result = matrices_for(repositories(), repositories(), [path])
    assert result["build"] == []
    assert [entry["image"] for entry in result["verify"]] == ["a", "b"]


def test_image_test_change_verifies_only_that_image():
    result = matrices_for(
        repositories(), repositories(), ["tests/images/test_b.py"]
    )
    assert result["build"] == []
    assert [entry["image"] for entry in result["verify"]] == ["b"]


def test_pipeline_test_changes_do_not_verify_images():
    result = matrices_for(
        repositories(), repositories(), ["tests/pipeline/test_detect_changes.py"]
    )
    assert result == {"build": [], "verify": []}


def test_build_images_are_not_verified_twice():
    current = repositories()
    current[0]["version"] = "v1.1.0"
    result = matrices_for(
        current,
        repositories(),
        ["releases.json", "tests/images/container_test_common.py"],
    )
    assert [entry["image"] for entry in result["build"]] == ["a"]
    assert [entry["image"] for entry in result["verify"]] == ["b"]


def test_build_required_handles_missing_previous_entry():
    assert build_required(repositories()[0], None, []) is True


def test_verify_required_ignores_full_rebuild():
    assert verify_required(repositories()[0], [FULL_REBUILD], set()) is False


def test_matrix_entry_contains_test_files():
    entry = matrices_for(
        repositories(), repositories(), ["tests/images/test_a.py"]
    )["verify"][0]
    assert entry["test_file"] == "tests/images/test_a.py"
    assert entry["prebuild_test"] == PREBUILD_TEST_FALLBACK
    assert entry["repo"] == "owner/a"


def test_prebuild_test_file_prefers_image_specific_test(tmp_path):
    specific = tmp_path / "tests" / "containerfiles" / "test_my_image_prebuild.py"
    specific.parent.mkdir(parents=True)
    specific.write_text("", encoding="utf-8")

    assert prebuild_test_file("my-image", tmp_path) == (
        "tests/containerfiles/test_my_image_prebuild.py"
    )


def test_prebuild_test_file_falls_back_to_generic_test(tmp_path):
    assert prebuild_test_file("my-image", tmp_path) == PREBUILD_TEST_FALLBACK


def test_audiobookshelf_uses_a_specific_prebuild_test():
    assert prebuild_test_file("audiobookshelf") == (
        "tests/containerfiles/test_audiobookshelf_prebuild.py"
    )


def git_repository(repo):
    (repo / "a").mkdir()
    (repo / "b").mkdir()
    (repo / "a" / "Containerfile").write_text("FROM scratch\n")
    (repo / "b" / "Containerfile").write_text("FROM scratch\n")
    write_json(repo / "releases.json", {"repositories": repositories()})
    first = commit_all(repo, "initial")
    return repo, first


def test_build_matrices_initial_revision_builds_all(git_repo):
    repo, _ = git_repository(git_repo)
    result = build_matrices("0" * 40, "HEAD", cwd=repo)
    assert [entry["image"] for entry in result["build"]] == ["a", "b"]


def test_build_matrices_detects_containerfile_change(git_repo):
    repo, first = git_repository(git_repo)
    (repo / "a" / "Containerfile").write_text("FROM scratch\n# changed\n")
    second = commit_all(repo, "change a")
    result = build_matrices(first, second, cwd=repo)
    assert [entry["image"] for entry in result["build"]] == ["a"]


def test_build_matrices_detects_test_change(git_repo):
    repo, first = git_repository(git_repo)
    (repo / "tests" / "images").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "images" / "test_b.py").write_text("")
    second = commit_all(repo, "change b test")
    result = build_matrices(first, second, cwd=repo)
    assert result["build"] == []
    assert [entry["image"] for entry in result["verify"]] == ["b"]


def test_build_matrices_rejects_invalid_current(git_repo):
    repo, _ = git_repository(git_repo)
    with pytest.raises(detect_changes.ReleaseConfigError, match="does not exist"):
        build_matrices("0" * 40, "f" * 40, cwd=repo)


def test_changed_files_uses_nul_delimited_output(git_repo):
    repo, first = git_repository(git_repo)
    (repo / "a" / "Containerfile").write_text("FROM scratch\n# changed\n")
    (repo / "b" / "Containerfile").write_text("FROM scratch\n# changed\n")
    second = commit_all(repo, "change both")
    assert changed_files(first, second, cwd=repo) == [
        "a/Containerfile",
        "b/Containerfile",
    ]


def test_changed_files_returns_full_rebuild_for_unknown_before(git_repo):
    repo, _ = git_repository(git_repo)
    assert changed_files("f" * 40, "HEAD", cwd=repo) == [FULL_REBUILD]
