"""Generic pre-build checks run against every image's upstream checkout."""

import subprocess

import pytest

pytestmark = pytest.mark.upstream


def test_upstream_source_is_a_git_checkout(upstream_source):
    result = subprocess.run(
        ["git", "-C", str(upstream_source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr.strip()
    assert result.stdout.strip(), "Upstream checkout has no revision"
