import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / ".github" / "scripts"


@pytest.fixture
def github_output(tmp_path):
    path = tmp_path / "github_output"
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture
def script_env(github_output):
    env = os.environ.copy()
    env["GITHUB_OUTPUT"] = str(github_output)
    # Force deterministic values: CI exports real GITHUB_RUN_* variables, and
    # tests that need other values override them through run_script(env=...).
    env["GITHUB_RUN_NUMBER"] = "42"
    env["GITHUB_RUN_ATTEMPT"] = "1"
    return env


@pytest.fixture
def run_script(script_env):
    def invoke(name, *args, env=None):
        merged = script_env.copy()
        if env:
            merged.update(env)

        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *map(str, args)],
            cwd=REPO_ROOT,
            env=merged,
            capture_output=True,
            text=True,
        )

    return invoke


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Tests"], cwd=repo, check=True
    )
    return repo
