import pytest

from container_test_common import image_name, release_entry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("audiobookshelf", "audiobookshelf"),
        ("ghcr.io/owner/audiobookshelf:test-42350477970-1", "audiobookshelf"),
        ("ghcr.io/owner/error-pages@sha256:" + "a" * 64, "error-pages"),
        ("localhost:5000/owner/lldap:v0.6.3", "lldap"),
    ],
)
def test_image_name(reference, expected):
    assert image_name(reference) == expected


def test_release_entry_accepts_a_full_image_reference():
    entry = release_entry("ghcr.io/gavinisumanth/audiobookshelf:test-42350477970-1")
    assert entry["image"] == "audiobookshelf"
