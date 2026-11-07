"""Shared parsing helpers for pre-build validation checks."""

import re

KNOWN_OUR_URL = (
    "https://github.com/mikiher/nunicode-binaries/releases/download/v1.2/"
    "libnusqlite3-linux-musl-x64.zip"
)
KNOWN_OUR_SHA256 = (
    "6fdd092b6ba471d9bd1d5c3b01da4ca2bd84f41b03c91ccc0db6d75f1d97e52d"
)
KNOWN_UPSTREAM_URL = (
    "https://github.com/mikiher/nunicode-sqlite/releases/download/v1.2/"
    "libnusqlite3-linux-musl-x64.zip"
)

KNOWN_DIVERGENCE = (
    (KNOWN_OUR_URL, KNOWN_OUR_SHA256),
    (KNOWN_UPSTREAM_URL, None),
)


def nusqlite_block(text, platform="linux/amd64"):
    """Return the NuSQLite case block for a target platform."""
    pattern = re.compile(
        rf'["\']?{re.escape(platform)}["\']?\)(.*?);;',
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"No NuSQLite case block found for {platform}")

    return match.group(1)


def parse_nusqlite(text, platform="linux/amd64"):
    """Return the NuSQLite archive URL and optional SHA-256 for a platform."""
    block = nusqlite_block(text, platform)
    url_match = re.search(r'https://[^"\s]+\.zip', block)
    if not url_match:
        raise AssertionError(f"No NuSQLite archive URL found for {platform}")

    sha_match = re.search(r"\b[0-9a-fA-F]{64}\b", block)
    return url_match.group(0), sha_match.group(0).lower() if sha_match else None
