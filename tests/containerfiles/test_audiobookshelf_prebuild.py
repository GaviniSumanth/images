"""Audiobookshelf-specific pre-build checks."""

from pathlib import Path

import pytest

from prebuild import (
    KNOWN_DIVERGENCE,
    KNOWN_OUR_URL,
    KNOWN_UPSTREAM_URL,
    parse_nusqlite,
)

pytestmark = pytest.mark.upstream

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_nusqlite_parity(upstream_dockerfile):
    ours = parse_nusqlite(
        (REPO_ROOT / "images" / "audiobookshelf" / "Containerfile").read_text(
            encoding="utf-8"
        )
    )
    upstream = parse_nusqlite(
        upstream_dockerfile.read_text(encoding="utf-8")
    )

    if ours == upstream:
        return

    if (ours, upstream) == KNOWN_DIVERGENCE:
        pytest.skip(
            "Known NuSQLite divergence: ours pins "
            f"{KNOWN_OUR_URL} with a SHA; upstream pins "
            f"{KNOWN_UPSTREAM_URL} without one. Any change to either side "
            "fails this test so the difference is reviewed."
        )

    pytest.fail(
        "NuSQLite pins differ from the known baseline.\n"
        f"ours:     {ours}\n"
        f"upstream: {upstream}\n"
        f"known:    {KNOWN_DIVERGENCE}"
    )
