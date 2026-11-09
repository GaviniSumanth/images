import base64
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import generate_changelogs
import publish_changelogs
from generate_changelogs import (
    ChangelogError,
    filter_context_for_image,
    group_context_by_date,
    load_commit_paths,
    normalize_changelog,
    release_entries,
    repository_slug,
)
from publish_changelogs import (
    PublishError,
    apply_generated_changelogs,
    create_or_update_pull_request,
    validate_generated_tree,
)
from release_config import ReleaseConfigError

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
BRANCH = "automation/changelogs"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def init_repo(
    repo: Path, *, files: dict[str, str] | None = None, remote: Path | None = None
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "--initial-branch=main")
    git(repo, "config", "user.name", "Unit test")
    git(repo, "config", "user.email", "unit@example.invalid")
    for name, content in (files or {}).items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "-q", "--allow-empty", "-m", "test: initial")
    if remote is not None:
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "-q", "-u", "origin", "main")


def init_bare_remote(path: Path) -> None:
    path.mkdir(parents=True)
    git(path, "init", "-q", "--bare", "--initial-branch=main")


def write_artifact(directory: Path, files: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def mock_api(monkeypatch, responses):
    calls = []

    def fake_request(url, token, *, method="GET", payload=None):
        calls.append({"url": url, "token": token, "method": method, "payload": payload})
        result = responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(publish_changelogs, "request_json", fake_request)
    return calls


def publish_environment(monkeypatch, repo, artifact, *, token="test-token"):
    monkeypatch.setattr(publish_changelogs, "REPO_ROOT", repo)
    monkeypatch.setenv("GITHUB_TOKEN", token)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/images")
    monkeypatch.setenv("GENERATED_CHANGELOG_DIR", str(artifact))
    monkeypatch.delenv("CHANGELOG_BRANCH", raising=False)
    monkeypatch.delenv("CHANGELOG_BASE_BRANCH", raising=False)


class FakeGitHub:
    def __init__(self):
        self.requests = []
        self.pull_requests = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(("GET", self.path, None))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(owner.pull_requests).encode("utf-8"))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                owner.requests.append(("POST", self.path, payload))
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"html_url": "https://github.com/owner/images/pull/42"}
                    ).encode("utf-8")
                )

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc_info):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"



def test_image_context_filters_paths_and_release_updates():
    context = [
        {
            "version": None,
            "commits": [
                {"id": "image-change", "message": "update image"},
                {"id": "release-change", "message": "update release"},
                {"id": "other-image", "message": "update other image"},
            ],
        }
    ]

    filtered = filter_context_for_image(
        context,
        "books",
        {
            "image-change": {"books/Containerfile"},
            "release-change": {"releases.json"},
            "other-image": {"other/Containerfile"},
        },
        {"release-change": {"books"}},
    )

    assert [commit["id"] for commit in filtered[0]["commits"]] == [
        "image-change",
        "release-change",
    ]
    assert len(context[0]["commits"]) == 3


def test_image_context_omits_empty_release_sections():
    context = [{"version": "v1.0.0", "commits": [{"id": "other"}]}]
    assert filter_context_for_image(context, "books", {}, {}) == []


def make_commit(commit_id: str, timestamp: int, **extra) -> dict:
    commit = {
        "id": commit_id,
        "message": f"change {commit_id}",
        "committer": {
            "name": "Unit test",
            "email": "unit@example.invalid",
            "timestamp": timestamp,
        },
        "conventional": True,
    }
    commit.update(extra)
    return commit


def utc_timestamp(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp())


def test_group_context_by_date_orders_newest_first_and_deduplicates():
    newer = make_commit("newer", utc_timestamp(2026, 11, 8))
    older = make_commit("older", utc_timestamp(2026, 11, 7))
    context = [
        {"version": None, "commits": [newer, older]},
        {"version": "v1.0.0", "commits": [newer]},
    ]

    grouped = group_context_by_date(context)

    assert [release["version"] for release in grouped] == ["2026-11-08", "2026-11-07"]
    assert [
        [commit["id"] for commit in release["commits"]] for release in grouped
    ] == [["newer"], ["older"]]


def test_group_context_by_date_preserves_commit_order_within_a_day():
    first = make_commit("first", utc_timestamp(2026, 11, 8, 18))
    second = make_commit("second", utc_timestamp(2026, 11, 8, 6))

    grouped = group_context_by_date([{"commits": [first, second]}])

    assert [commit["id"] for commit in grouped[0]["commits"]] == ["first", "second"]


def test_group_context_by_date_recomputes_release_metadata():
    first = make_commit("first", utc_timestamp(2026, 11, 8, 18))
    second = make_commit("second", utc_timestamp(2026, 11, 8, 6), conventional=False)
    context = [
        {
            "version": "v9.9.9",
            "message": "old release",
            "timestamp": 1,
            "previous": "v9.9.8",
            "commit_id": "unrelated",
            "commit_range": {"from": "a", "to": "b"},
            "statistics": {"commit_count": 99},
            "commits": [first, second],
        }
    ]

    release = group_context_by_date(context)[0]

    assert release["version"] == "2026-11-08"
    assert release["message"] is None
    assert release["previous"] is None
    assert release["timestamp"] == utc_timestamp(2026, 11, 8, 18)
    assert release["commit_id"] == "first"
    assert release["commit_range"] == {"from": "second", "to": "first"}
    assert release["statistics"] == {
        "commit_count": 2,
        "commits_timespan": 0,
        "conventional_commit_count": 1,
        "links": [],
    }


def test_group_context_by_date_rejects_commits_without_a_timestamp():
    context = [{"commits": [{"id": "missing", "message": "change"}]}]

    with pytest.raises(ChangelogError):
        group_context_by_date(context)


def test_group_context_by_date_returns_empty_for_empty_context():
    assert group_context_by_date([]) == []


def test_release_entries_supports_canonical_and_legacy_shapes():
    entry = {"image": "books", "version": "v1.2.3"}
    assert release_entries({"repositories": [entry]}) == {"books": entry}
    assert release_entries([entry]) == {"books": entry}


def test_release_version_changes_are_attributed_to_the_changed_image(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    entries = [
        {"image": "books", "version": "v1.0.0"},
        {"image": "music", "version": "v2.0.0"},
    ]
    releases_file = repo / "releases.json"
    releases_file.write_text(
        json.dumps({"repositories": entries}), encoding="utf-8"
    )
    subprocess.run(["git", "add", "releases.json"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Unit test",
            "-c",
            "user.email=unit@example.invalid",
            "commit",
            "-m",
            "test: create release entries",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    entries[0]["version"] = "v1.1.0"
    releases_file.write_text(
        json.dumps({"repositories": entries}), encoding="utf-8"
    )
    subprocess.run(["git", "add", "releases.json"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Unit test",
            "-c",
            "user.email=unit@example.invalid",
            "commit",
            "-m",
            "update books application",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    commit_id = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(generate_changelogs, "REPO_ROOT", repo)

    assert generate_changelogs.changed_release_images(commit_id) == {"books"}


def test_load_commit_paths_reads_history_in_one_process(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    init_repo(repo, files={"one.txt": "one\n"})
    first = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "two.txt").write_text("two\n", encoding="utf-8")
    git(repo, "add", "two.txt")
    git(repo, "commit", "-q", "-m", "test: add two")
    second = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "commit", "-q", "--allow-empty", "-m", "test: empty")
    empty = git(repo, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(generate_changelogs, "REPO_ROOT", repo)

    paths = load_commit_paths({first, second, empty})

    assert paths[first] == {"one.txt"}
    assert paths[second] == {"two.txt"}
    assert paths[empty] == set()


def test_normalize_changelog_replaces_placeholder_and_ends_with_one_newline():
    content = "# Changelog\n\n__REPOSITORY_URL__/commit/abc\n\n\n"
    assert normalize_changelog(content, "https://github.com/owner/images") == (
        "# Changelog\n\nhttps://github.com/owner/images/commit/abc\n"
    )


def test_normalize_changelog_rejects_empty_output():
    with pytest.raises(ChangelogError):
        normalize_changelog(" \n\n", "https://github.com/owner/images")


def test_git_cliff_binary_uses_explicit_override(monkeypatch):
    monkeypatch.setenv("GIT_CLIFF_BIN", sys.executable)
    assert generate_changelogs.git_cliff_binary() == shutil.which(sys.executable)


def test_git_cliff_binary_reports_missing_binary(monkeypatch):
    monkeypatch.setenv("GIT_CLIFF_BIN", "definitely-not-a-real-git-cliff")
    with pytest.raises(ChangelogError):
        generate_changelogs.git_cliff_binary()

    monkeypatch.delenv("GIT_CLIFF_BIN")
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ChangelogError):
        generate_changelogs.git_cliff_binary()


def test_repository_slug_uses_github_repository(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "Owner/Project")
    assert repository_slug() == "Owner/Project"


def test_repository_slug_rejects_invalid_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "not-a-slug")
    with pytest.raises(ReleaseConfigError):
        repository_slug()


def test_repository_slug_falls_back_to_origin(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    init_repo(repo)
    git(repo, "remote", "add", "origin", "git@github.com:owner/name.git")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(generate_changelogs, "REPO_ROOT", repo)

    assert repository_slug() == "owner/name"


def test_changelog_template_is_repository_neutral_and_narrow():
    config = (REPO_ROOT / ".github" / "changelog.toml").read_text(encoding="utf-8")

    assert "__REPOSITORY_URL__" in config
    assert "github.com/GaviniSumanth" not in config
    assert "tag_pattern" not in config
    assert "grouped by commit date (UTC)" in config
    assert 'split(pat="\\n") | first' in config
    for parser in (
        "^chore\\(deps",
        "^fix\\(deps",
        "^build\\(deps",
        "^docs\\(changelog\\)",
        "^chore\\(changelog\\)",
        "Update .+ (?:Docker tag|action|digest) to ",
        "^Pin .+ (?:Docker tag|action|digest) to ",
        "^Pin dependencies$",
    ):
        assert parser in config
    assert "^(renovate|update\\b|bump\\b|pin\\b)" not in config
    for skipped in ("^docs\\(changelog\\)", "^chore\\(changelog\\)", "^Merge "):
        assert config.index(skipped) < config.index("^docs?")


def test_renovate_uses_changelog_dependency_commit_format():
    renovate = json.loads((REPO_ROOT / "renovate.json").read_text(encoding="utf-8"))
    assert renovate["semanticCommits"] == "enabled"
    assert renovate["semanticCommitType"] == "chore"
    assert renovate["semanticCommitScope"] == "deps"


def test_changelog_workflow_generates_data_and_publishes_a_pull_request():
    workflow = yaml.load(
        (WORKFLOW_DIR / "changelog.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    generate_job = workflow["jobs"]["generate"]
    publish_job = workflow["jobs"]["publish"]

    assert workflow["permissions"]["contents"] == "read"
    assert generate_job["permissions"]["contents"] == "read"
    assert publish_job["permissions"] == {
        "actions": "read",
        "contents": "write",
        "pull-requests": "write",
    }

    generate_steps = generate_job["steps"]
    checkout = next(
        step for step in generate_steps if step["name"] == "Checkout repository"
    )
    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["fetch-depth"] == "0"

    install = next(step for step in generate_steps if step["name"] == "Install git-cliff")
    assert install["uses"] == (
        "taiki-e/install-action@cfdb7ed4ccc7c7dce37759eae89dc5674b469b39"
    )
    assert install["with"]["tool"] == "git-cliff@2.14.2"
    assert not any(
        "orhun/git-cliff-action" in step.get("uses", "") for step in generate_steps
    )
    assert all("GIT_CLIFF_BIN" not in step.get("env", {}) for step in generate_steps)

    upload = next(
        step
        for step in generate_steps
        if step["name"] == "Upload generated changelogs"
    )
    assert upload["if"] == "steps.generate.outputs.changed == 'true'"
    assert upload["with"]["name"] == "generated-changelogs"
    assert "CHANGELOG.md" in upload["with"]["path"]
    assert "changelogs/" in upload["with"]["path"]
    assert ".github" not in upload["with"]["path"]

    publish_steps = publish_job["steps"]
    checkout = next(
        step for step in publish_steps if step["name"] == "Checkout repository"
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] == "false"

    download = next(
        step
        for step in publish_steps
        if step["name"] == "Download generated changelogs"
    )
    assert download["with"]["name"] == "generated-changelogs"
    assert download["with"]["path"] == "${{ runner.temp }}/generated-changelogs"

    publish = next(
        step for step in publish_steps if step["name"] == "Publish changelogs"
    )
    assert publish["env"] == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
        "GITHUB_REPOSITORY": "${{ github.repository }}",
        "GENERATED_CHANGELOG_DIR": "${{ runner.temp }}/generated-changelogs",
        "CHANGELOG_BASE_BRANCH": "${{ github.event.repository.default_branch }}",
    }
    assert publish_job["if"] == (
        "github.ref == 'refs/heads/main' && "
        "needs.generate.outputs.changed == 'true'"
    )
    assert all(
        "GITHUB_TOKEN" not in step.get("env", {})
        for step in publish_steps
        if step is not publish
    )


def test_validate_generated_tree_normalizes_files(tmp_path):
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact,
        {"CHANGELOG.md": "# Repo\n\n\n", "changelogs/books.md": "# Books\n\n"},
    )

    assert validate_generated_tree(artifact) == {
        "CHANGELOG.md": "# Repo\n",
        "changelogs/books.md": "# Books\n",
    }


@pytest.mark.parametrize(
    "files",
    [
        {"changelogs/books.md": "# Books\n"},
        {"CHANGELOG.md": "# Repo\n"},
        {"CHANGELOG.md": "# Repo\n", "changelogs/books.md": "# Books\n", "extra.py": ""},
        {"CHANGELOG.md": "# Repo\n", "changelogs/books.txt": "# Books\n"},
        {"CHANGELOG.md": "# Repo\n", "changelogs/books.md": "\0"},
        {"CHANGELOG.md": "# Repo\n", "changelogs/books.md": " \n"},
    ],
    ids=[
        "missing-repository-changelog",
        "missing-image-directory",
        "unexpected-entry",
        "unexpected-image-name",
        "nul-byte",
        "empty-image-changelog",
    ],
)
def test_validate_generated_tree_rejects_invalid_data(tmp_path, files):
    artifact = tmp_path / "artifact"
    write_artifact(artifact, files)

    with pytest.raises(PublishError):
        validate_generated_tree(artifact)


def test_validate_generated_tree_rejects_symlinked_file(tmp_path):
    artifact = tmp_path / "artifact"
    write_artifact(artifact, {"CHANGELOG.md": "# Repo\n"})
    (artifact / "changelogs").mkdir()
    target = tmp_path / "target.md"
    target.write_text("# Books\n", encoding="utf-8")
    (artifact / "changelogs" / "books.md").symlink_to(target)

    with pytest.raises(PublishError):
        validate_generated_tree(artifact)


def test_validate_generated_tree_rejects_symlinked_directory(tmp_path):
    artifact = tmp_path / "artifact"
    write_artifact(artifact, {"CHANGELOG.md": "# Repo\n"})
    target = tmp_path / "target"
    target.mkdir()
    (target / "books.md").write_text("# Books\n", encoding="utf-8")
    (artifact / "changelogs").symlink_to(target, target_is_directory=True)

    with pytest.raises(PublishError):
        validate_generated_tree(artifact)


def test_validate_generated_tree_rejects_non_utf8(tmp_path):
    artifact = tmp_path / "artifact"
    write_artifact(artifact, {"CHANGELOG.md": "# Repo\n"})
    (artifact / "changelogs").mkdir()
    (artifact / "changelogs" / "books.md").write_bytes(b"\xff\xfe")

    with pytest.raises(PublishError):
        validate_generated_tree(artifact)


def test_apply_generated_changelogs_copies_files_and_removes_stale(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={
            "CHANGELOG.md": "# Old\n",
            "changelogs/old.md": "# Old image\n",
            "README.md": "readme\n",
        },
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    monkeypatch.setattr(publish_changelogs, "REPO_ROOT", repo)

    assert apply_generated_changelogs(artifact) is True

    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == "# New\n"
    assert (repo / "changelogs" / "books.md").read_text(encoding="utf-8") == (
        "# Books\n"
    )
    assert not (repo / "changelogs" / "old.md").exists()
    staged = set(
        git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    )
    assert staged == {
        "CHANGELOG.md",
        "changelogs/books.md",
        "changelogs/old.md",
    }
    assert "README.md" not in staged


def test_apply_generated_changelogs_is_idempotent(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"},
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    monkeypatch.setattr(publish_changelogs, "REPO_ROOT", repo)

    assert apply_generated_changelogs(artifact) is False


def test_apply_generated_changelogs_rejects_dirty_worktree(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    init_repo(repo, files={"CHANGELOG.md": "# Old\n"})
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    monkeypatch.setattr(publish_changelogs, "REPO_ROOT", repo)

    with pytest.raises(PublishError):
        apply_generated_changelogs(artifact)


def test_apply_generated_changelogs_rejects_unexpected_existing_file(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={"CHANGELOG.md": "# Old\n", "changelogs/notes.txt": "notes\n"},
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    monkeypatch.setattr(publish_changelogs, "REPO_ROOT", repo)

    with pytest.raises(PublishError):
        apply_generated_changelogs(artifact)


def test_publish_commits_pushes_and_opens_a_pull_request(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    init_bare_remote(remote)
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={"CHANGELOG.md": "# Old\n", "changelogs/old.md": "# Old image\n"},
        remote=remote,
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    publish_environment(monkeypatch, repo, artifact)
    calls = mock_api(
        monkeypatch,
        [[], {"html_url": "https://github.com/owner/images/pull/1"}],
    )

    publish_changelogs.publish()

    assert git(repo, "branch", "--show-current").stdout.strip() == BRANCH
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == (
        publish_changelogs.COMMIT_MESSAGE
    )
    assert git(repo, "log", "-1", "--format=%an <%ae>").stdout.strip() == (
        "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
    )
    assert git(remote, "log", "-1", "--format=%s", BRANCH).stdout.strip() == (
        publish_changelogs.COMMIT_MESSAGE
    )
    assert git(remote, "show", f"{BRANCH}:CHANGELOG.md").stdout == "# New\n"
    assert git(remote, "show", f"{BRANCH}:changelogs/books.md").stdout == "# Books\n"
    assert (
        git(remote, "cat-file", "-e", f"{BRANCH}:changelogs/old.md", check=False)
        .returncode
        != 0
    )

    assert len(calls) == 2
    assert calls[0]["method"] == "GET"
    assert "state=open" in calls[0]["url"]
    assert "head=owner%3Aautomation%2Fchangelogs" in calls[0]["url"]
    assert "base=main" in calls[0]["url"]
    assert calls[1]["method"] == "POST"
    assert calls[1]["payload"] == {
        "title": publish_changelogs.COMMIT_MESSAGE,
        "head": BRANCH,
        "base": "main",
        "body": publish_changelogs.PR_BODY,
    }


def test_publish_script_runs_end_to_end(tmp_path):
    remote = tmp_path / "remote.git"
    init_bare_remote(remote)
    repo = tmp_path / "repo"
    init_repo(repo, files={"CHANGELOG.md": "# Old\n"}, remote=remote)

    scripts = repo / ".github" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("publish_changelogs.py", "release_config.py"):
        shutil.copy2(REPO_ROOT / ".github" / "scripts" / name, scripts / name)
    git(repo, "add", ".github/scripts")
    git(repo, "commit", "-q", "-m", "test: add publish scripts")

    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )

    with FakeGitHub() as github:
        env = os.environ.copy()
        env.update(
            {
                "GITHUB_TOKEN": "test-token",
                "GITHUB_REPOSITORY": "owner/images",
                "GENERATED_CHANGELOG_DIR": str(artifact),
                "GITHUB_API_URL": github.url,
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        env.pop("CHANGELOG_BRANCH", None)
        env.pop("CHANGELOG_BASE_BRANCH", None)
        result = subprocess.run(
            [sys.executable, str(scripts / "publish_changelogs.py")],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    assert result.returncode == 0, result.stderr
    assert "Pushed generated changelogs" in result.stdout
    assert "Created changelog pull request" in result.stdout
    assert git(remote, "show", f"{BRANCH}:CHANGELOG.md").stdout == "# New\n"
    assert git(remote, "show", f"{BRANCH}:changelogs/books.md").stdout == "# Books\n"
    assert [request[0] for request in github.requests] == ["GET", "POST"]
    assert github.requests[1][2]["head"] == BRANCH
    assert github.requests[1][2]["base"] == "main"


def test_publish_force_updates_a_diverged_automation_branch(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    init_bare_remote(remote)
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={"CHANGELOG.md": "# Old\n", "changelogs/old.md": "# Old image\n"},
        remote=remote,
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# First\n", "changelogs/books.md": "# Books\n"}
    )
    publish_environment(monkeypatch, repo, artifact)
    mock_api(
        monkeypatch,
        [
            [],
            {"html_url": "https://github.com/owner/images/pull/1"},
            [],
            {"html_url": "https://github.com/owner/images/pull/1"},
        ],
    )

    publish_changelogs.publish()
    first_sha = git(remote, "rev-parse", BRANCH).stdout.strip()

    git(repo, "switch", "-q", "main")
    write_artifact(
        artifact, {"CHANGELOG.md": "# Second\n", "changelogs/books.md": "# Books\n"}
    )
    publish_changelogs.publish()
    second_sha = git(remote, "rev-parse", BRANCH).stdout.strip()

    assert second_sha != first_sha
    assert (
        git(repo, "merge-base", "--is-ancestor", first_sha, second_sha, check=False)
        .returncode
        == 1
    )
    assert git(remote, "show", f"{BRANCH}:CHANGELOG.md").stdout == "# Second\n"


def test_publish_skips_push_and_pull_request_when_nothing_changed(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    init_repo(
        repo,
        files={"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"},
    )
    artifact = tmp_path / "artifact"
    write_artifact(
        artifact, {"CHANGELOG.md": "# New\n", "changelogs/books.md": "# Books\n"}
    )
    publish_environment(monkeypatch, repo, artifact)
    calls = mock_api(monkeypatch, [])

    publish_changelogs.publish()

    assert calls == []
    assert git(repo, "branch", "--list", BRANCH).stdout.strip() == ""


def test_publish_requires_repository_and_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ReleaseConfigError):
        publish_changelogs.publish(tmp_path)

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/images")
    with pytest.raises(ReleaseConfigError):
        publish_changelogs.publish(tmp_path)


def test_create_or_update_pull_request_reuses_an_existing_request(monkeypatch):
    calls = mock_api(
        monkeypatch, [[{"html_url": "https://github.com/owner/images/pull/7"}]]
    )

    url = create_or_update_pull_request("owner/images", BRANCH, "main", "token")

    assert url == "https://github.com/owner/images/pull/7"
    assert len(calls) == 1
    assert calls[0]["method"] == "GET"


def test_create_or_update_pull_request_recovers_from_a_concurrent_creation(
    monkeypatch,
):
    calls = mock_api(
        monkeypatch,
        [
            [],
            PublishError("already exists"),
            [{"html_url": "https://github.com/owner/images/pull/9"}],
        ],
    )

    url = create_or_update_pull_request("owner/images", BRANCH, "main", "token")

    assert url == "https://github.com/owner/images/pull/9"
    assert [call["method"] for call in calls] == ["GET", "POST", "GET"]


def test_git_authentication_is_command_scoped(monkeypatch):
    observed = []
    token = "test-write-token"
    monkeypatch.setenv("GITHUB_TOKEN", token)

    def fake_run(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(publish_changelogs.subprocess, "run", fake_run)

    publish_changelogs.run_git(["status"])
    publish_changelogs.run_git(
        ["push", "origin", "HEAD:refs/heads/main"], authenticated=True
    )

    local_env = observed[0][1]["env"]
    push_env = observed[1][1]["env"]
    assert "GITHUB_TOKEN" not in local_env
    assert "GIT_CONFIG_COUNT" not in local_env
    assert "GITHUB_TOKEN" not in push_env
    assert push_env["GIT_CONFIG_COUNT"] == "1"
    assert push_env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert push_env["GIT_CONFIG_VALUE_0"] == (
        "AUTHORIZATION: basic "
        + base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    )
    assert token not in " ".join(observed[1][0])


def test_error_detail_redacts_the_token(monkeypatch):
    token = "secret-token"
    monkeypatch.setenv("GITHUB_TOKEN", token)
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    error = subprocess.CalledProcessError(
        1, ["git"], stderr=f"fatal: {token} and {encoded}"
    )

    detail = publish_changelogs.error_detail(error)

    assert token not in detail
    assert encoded not in detail
    assert detail.count("[REDACTED]") == 2


@pytest.mark.parametrize(
    "value",
    ["https://api.github.com", "https://api.github.com/", "http://localhost:8080/api"],
)
def test_api_base_accepts_valid_urls(monkeypatch, value):
    monkeypatch.setenv("GITHUB_API_URL", value)
    assert publish_changelogs.api_base() == value.rstrip("/")


@pytest.mark.parametrize(
    "value",
    [
        "ftp://api.github.com",
        "https://user:pass@api.github.com",
        "https://api.github.com?x=1",
        "https://api.github.com#frag",
        "not-a-url",
    ],
)
def test_api_base_rejects_invalid_urls(monkeypatch, value):
    monkeypatch.setenv("GITHUB_API_URL", value)
    with pytest.raises(PublishError):
        publish_changelogs.api_base()


@pytest.mark.parametrize("value", ["main", BRANCH, "release/1.2"])
def test_validate_branch_accepts_valid_names(value):
    assert publish_changelogs.validate_branch(value, "BRANCH") == value


@pytest.mark.parametrize("value", ["", "bad branch", "-bad", "a..b"])
def test_validate_branch_rejects_invalid_names(value):
    with pytest.raises(PublishError):
        publish_changelogs.validate_branch(value, "BRANCH")
