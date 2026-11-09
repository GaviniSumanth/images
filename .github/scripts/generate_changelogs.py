#!/usr/bin/env python3
"""Generate the repository and per-image changelogs with Git-cliff."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from release_config import (
    IMAGE_PATTERN,
    RELEASES_FILE,
    REPO_ROOT,
    ReleaseConfigError,
    load_repositories,
    repositories_from_data,
    validate_repository_slug,
)

CONFIG_FILE = REPO_ROOT / ".github" / "changelog.toml"
CHANGELOG_DIR = REPO_ROOT / "changelogs"
REPOSITORY_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
REPOSITORY_URL_TOKEN = "__REPOSITORY_URL__"


class ChangelogError(Exception):
    """Raised when changelog inputs or Git-cliff output are invalid."""


def run_git(
    args: list[str], *, check: bool = True, input_text: str | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=120,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise subprocess.CalledProcessError(
            result.returncode, ["git", *args], output=result.stdout, stderr=detail
        )
    return result


def git_cliff_binary() -> str:
    """Resolve Git-cliff from an explicit override or the process PATH."""
    configured = os.environ.get("GIT_CLIFF_BIN")
    binary = shutil.which(configured or "git-cliff")
    if binary is None:
        if configured:
            raise ChangelogError(f"GIT_CLIFF_BIN is not executable: {configured}")
        raise ChangelogError("git-cliff is not installed or not on PATH")
    return binary


def run_git_cliff(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [git_cliff_binary(), "--config", str(CONFIG_FILE), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise subprocess.CalledProcessError(
            result.returncode,
            ["git-cliff", *args],
            output=result.stdout,
            stderr=detail,
        )
    return result


def repository_slug() -> str:
    """Return the GitHub owner/name slug for the current repository."""
    configured = os.environ.get("GITHUB_REPOSITORY")
    if configured:
        return validate_repository_slug(configured)

    result = run_git(["remote", "get-url", "origin"], check=False)
    if result.returncode:
        raise ChangelogError(
            "Unable to determine the repository; set GITHUB_REPOSITORY"
        )

    remote = result.stdout.strip()
    prefixes = (
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
    )
    for prefix in prefixes:
        if remote.startswith(prefix):
            candidate = remote[len(prefix) :].strip("/")
            break
    else:
        raise ChangelogError(f"Unsupported Git origin URL: {remote}")

    return validate_repository_slug(candidate.removesuffix(".git"))


def normalize_changelog(content: str, repository_url: str) -> str:
    """Replace the repository placeholder and end with exactly one newline."""
    content = content.replace(REPOSITORY_URL_TOKEN, repository_url)
    if REPOSITORY_URL_TOKEN in content:
        raise ChangelogError("Git-cliff output contains an unresolved repository URL")
    if not content.strip():
        raise ChangelogError("Git-cliff produced an empty changelog")
    return content.rstrip() + "\n"


def load_context() -> list[dict]:
    result = run_git_cliff(["--context"])
    try:
        context = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ChangelogError(f"Git-cliff returned invalid JSON context: {error}") from error

    if not isinstance(context, list):
        raise ChangelogError("Git-cliff context must be a list of releases")
    for release in context:
        if not isinstance(release, dict) or not isinstance(release.get("commits"), list):
            raise ChangelogError("Git-cliff context contains an invalid release")
    return context


def load_commit_paths(commit_ids: set[str]) -> dict[str, set[str]]:
    """Read changed paths for every commit in one Git process."""
    if not commit_ids:
        return {}

    ordered = sorted(commit_ids)
    result = run_git(
        ["diff-tree", "--stdin", "--root", "-r", "-m", "--name-only", "-z"],
        input_text="\n".join(ordered) + "\n",
    )
    paths_by_commit = {commit_id: set() for commit_id in ordered}
    current = None
    seen = set()
    for token in result.stdout.split("\0"):
        if not token:
            continue
        if token in paths_by_commit:
            current = token
            seen.add(token)
            continue
        if current is None:
            raise ChangelogError(f"Unexpected git diff-tree output: {token!r}")
        paths_by_commit[current].add(token)

    missing = commit_ids - seen
    if missing:
        # diff-tree emits nothing for an empty commit. Confirm that each
        # missing object is a real commit before treating it as having no paths.
        result = run_git(
            ["cat-file", "--batch-check"],
            input_text="\n".join(sorted(missing)) + "\n",
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) != 3 or parts[1] != "commit":
                raise ChangelogError(
                    "Unable to read changed paths for commit(s): "
                    + ", ".join(sorted(missing))
                )
    return paths_by_commit


def release_entries(data: object) -> dict[str, dict]:
    repositories = repositories_from_data(data)
    if not isinstance(repositories, list):
        raise ChangelogError("Historical releases.json does not contain a repositories list")

    entries = {}
    for entry in repositories:
        if not isinstance(entry, dict) or not isinstance(entry.get("image"), str):
            raise ChangelogError("Historical releases.json contains an invalid image entry")
        entries[entry["image"]] = entry
    return entries


def read_releases_at(revision: str) -> dict[str, dict] | None:
    result = run_git(["show", f"{revision}:releases.json"], check=False)
    if result.returncode:
        return None

    try:
        return release_entries(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise ChangelogError(
            f"Invalid releases.json at {revision}: {error}"
        ) from error


def changed_release_images(commit_id: str) -> set[str]:
    parents = run_git(["rev-list", "--parents", "-n", "1", commit_id]).stdout.split()
    current = read_releases_at(commit_id)
    if current is None:
        return set()

    previous = read_releases_at(parents[1]) if len(parents) > 1 else None
    previous = previous or {}
    return {
        image
        for image in current.keys() | previous.keys()
        if current.get(image) != previous.get(image)
    }


def group_context_by_date(context: list[dict]) -> list[dict]:
    """Split Git-cliff releases into one release per UTC commit date.

    Git-cliff normally groups commits by tag. This repository has no release
    tags, so group by the committer date instead and use the ISO date as the
    release version. Commits keep the newest-first order Git-cliff produced.
    """
    if not context:
        return []

    template = copy.deepcopy(context[0])
    commits = []
    seen = set()
    for release in context:
        for commit in release["commits"]:
            commit_id = commit.get("id") if isinstance(commit, dict) else None
            if not isinstance(commit_id, str):
                raise ChangelogError("Git-cliff context contains a commit without an id")
            if commit_id in seen:
                continue
            seen.add(commit_id)
            commits.append(commit)

    by_date: dict[date, list[dict]] = {}
    for commit in commits:
        committer = commit.get("committer")
        timestamp = committer.get("timestamp") if isinstance(committer, dict) else None
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise ChangelogError(
                f"Commit {commit['id']} is missing a valid committer timestamp"
            )
        day = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        by_date.setdefault(day, []).append(commit)

    grouped = []
    for day in sorted(by_date, reverse=True):
        day_commits = by_date[day]
        release = copy.deepcopy(template)
        release["version"] = day.isoformat()
        release["message"] = None
        release["timestamp"] = max(
            commit["committer"]["timestamp"] for commit in day_commits
        )
        release["previous"] = None
        release["commit_id"] = day_commits[0]["id"]
        release["commit_range"] = {
            "from": day_commits[-1]["id"],
            "to": day_commits[0]["id"],
        }
        release["commits"] = day_commits
        release["statistics"] = {
            "commit_count": len(day_commits),
            "commits_timespan": 0,
            "conventional_commit_count": sum(
                1 for commit in day_commits if commit.get("conventional")
            ),
            "links": [],
        }
        grouped.append(release)
    return grouped


def filter_context_for_image(
    context: list[dict],
    image: str,
    paths_by_commit: dict[str, set[str]],
    release_changes: dict[str, set[str]],
) -> list[dict]:
    filtered = []
    image_prefixes = (f"{image}/", f"images/{image}/")
    for release in context:
        selected = copy.deepcopy(release)
        selected["commits"] = [
            commit
            for commit in release["commits"]
            if any(
                path.startswith(image_prefixes)
                for path in paths_by_commit.get(commit["id"], set())
            )
            or image in release_changes.get(commit["id"], set())
        ]
        if selected["commits"]:
            filtered.append(selected)
    return filtered


def render_context(
    context: list[dict], output_file: Path, repository_url: str
) -> str:
    with tempfile.TemporaryDirectory(prefix="changelog-context-") as directory:
        context_file = Path(directory) / "context.json"
        context_file.write_text(
            json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        run_git_cliff(["--from-context", str(context_file), "--output", str(output_file)])

    if output_file.is_symlink() or not output_file.is_file():
        raise ChangelogError("Git-cliff did not create its requested output file")
    return normalize_changelog(output_file.read_text(encoding="utf-8"), repository_url)


def ensure_real_directory(path: Path) -> None:
    if path.is_symlink():
        raise ChangelogError(f"Refusing to use a symlinked directory: {path}")
    if path.exists() and not path.is_dir():
        raise ChangelogError(f"Expected a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ChangelogError(f"Unable to create a real directory: {path}")


def write_if_changed(path: Path, content: str) -> bool:
    if path.is_symlink():
        raise ChangelogError(f"Refusing to write through a symlink: {path}")
    if path.parent.is_symlink():
        raise ChangelogError(f"Refusing to write into a symlinked directory: {path.parent}")
    if path.exists() and not path.is_file():
        raise ChangelogError(f"Expected a regular file: {path}")
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def set_github_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def generate() -> bool:
    repositories = load_repositories(RELEASES_FILE)
    images = []
    for entry in repositories:
        image = entry.get("image")
        if not isinstance(image, str) or not IMAGE_PATTERN.fullmatch(image):
            raise ChangelogError("releases.json contains an invalid image name")
        images.append(image)
    if len(set(images)) != len(images):
        raise ChangelogError("releases.json contains duplicate image names")
    images.sort()

    repository_url = f"https://github.com/{repository_slug()}"
    context = load_context()
    commit_ids = {
        commit["id"]
        for release in context
        for commit in release["commits"]
        if isinstance(commit, dict) and isinstance(commit.get("id"), str)
    }
    if sum(len(release["commits"]) for release in context) != len(commit_ids):
        raise ChangelogError("Git-cliff context contains malformed or duplicate commits")

    paths_by_commit = load_commit_paths(commit_ids)
    release_changes = {
        commit_id: changed_release_images(commit_id)
        for commit_id, paths in paths_by_commit.items()
        if "releases.json" in paths
    }
    dated_context = group_context_by_date(context)

    changed = False
    ensure_real_directory(CHANGELOG_DIR)
    with tempfile.TemporaryDirectory(prefix="repository-changelog-") as directory:
        rendered_repository = render_context(
            dated_context, Path(directory) / "CHANGELOG.md", repository_url
        )
    changed = write_if_changed(REPOSITORY_CHANGELOG, rendered_repository) or changed

    for image in images:
        image_context = filter_context_for_image(
            dated_context, image, paths_by_commit, release_changes
        )
        with tempfile.TemporaryDirectory(prefix="image-changelog-") as directory:
            rendered = render_context(
                image_context, Path(directory) / f"{image}.md", repository_url
            )
        title = f"# {image} Changelog"
        rendered = rendered.replace("# Changelog", title, 1)
        changed = write_if_changed(CHANGELOG_DIR / f"{image}.md", rendered) or changed

    for existing in CHANGELOG_DIR.glob("*.md"):
        if existing.is_symlink():
            raise ChangelogError(f"Refusing to use a symlinked changelog: {existing}")
        if existing.stem not in images:
            if not existing.is_file():
                raise ChangelogError(f"Expected a regular changelog file: {existing}")
            existing.unlink()
            changed = True

    status = run_git(
        [
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "CHANGELOG.md",
            "changelogs",
        ]
    )
    changed = bool(status.stdout.strip()) or changed
    set_github_output("changed", "true" if changed else "false")
    print("Changelogs updated" if changed else "Changelogs are already current")
    return changed


def error_detail(error: BaseException) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        return (
            (error.stderr or "").strip()
            or (error.output or "").strip()
            or f"command failed with exit code {error.returncode}"
        )
    return str(error)


def main() -> int:
    try:
        generate()
    except (
        ChangelogError,
        OSError,
        ReleaseConfigError,
        subprocess.SubprocessError,
    ) as error:
        print(f"::error::Unable to generate changelogs: {error_detail(error)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
