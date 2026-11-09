import copy

import pytest

from validate_releases import (
    ValidationError,
    validate_entry,
    validate_repositories,
    validate_unique,
)

pytestmark = pytest.mark.unit

METADATA = {
    "org.opencontainers.image.title": "Example",
    "org.opencontainers.image.description": "Example image",
    "org.opencontainers.image.url": "https://example.com/",
    "org.opencontainers.image.documentation": "https://example.com/docs/",
    "org.opencontainers.image.licenses": "MIT",
}


def entry(**overrides):
    value = {
        "repository": "https://github.com/owner/example",
        "version": "v1.2.3",
        "containerfile": "images/example/Containerfile",
        "image": "example",
        "metadata": copy.deepcopy(METADATA),
    }
    value.update(overrides)
    return value


def test_valid_entry_passes():
    validate_entry(entry(), 0)


@pytest.mark.parametrize(
    "field",
    ["repository", "version", "containerfile", "image", "metadata"],
)
def test_missing_field_is_rejected(field):
    value = entry()
    del value[field]
    with pytest.raises(ValidationError):
        validate_entry(value, 0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "http://github.com/owner/example"),
        ("version", ""),
        ("version", "has space"),
        ("containerfile", "Containerfile"),
        ("containerfile", "/etc/Containerfile"),
        ("containerfile", "example/Containerfile"),
        ("containerfile", "images/Containerfile"),
        ("image", "Example"),
        ("image", "bad/name"),
        ("metadata", []),
    ],
)
def test_invalid_field_is_rejected(field, value):
    with pytest.raises(ValidationError):
        validate_entry(entry(**{field: value}), 0)


@pytest.mark.parametrize(
    "key",
    [
        "org.opencontainers.image.version",
        "org.opencontainers.image.source",
        "org.opencontainers.image.vendor",
        "org.opencontainers.image.created",
        "org.opencontainers.image.revision",
        "com.example.custom",
    ],
)
def test_pipeline_owned_or_unknown_metadata_is_rejected(key):
    value = entry()
    value["metadata"][key] = "value"
    with pytest.raises(ValidationError):
        validate_entry(value, 0)


@pytest.mark.parametrize("value", ["", "line\nbreak", "line\rbreak"])
def test_metadata_values_must_be_single_line(value):
    data = entry()
    data["metadata"]["org.opencontainers.image.title"] = value
    with pytest.raises(ValidationError):
        validate_entry(data, 0)


def test_authors_metadata_is_allowed():
    data = entry()
    data["metadata"]["org.opencontainers.image.authors"] = "Example Authors"
    validate_entry(data, 0)


def test_duplicate_images_are_rejected():
    with pytest.raises(ValidationError):
        validate_unique(
            [
                entry(),
                entry(
                    repository="https://github.com/other/example",
                    containerfile="images/other/Containerfile",
                ),
            ]
        )


def test_duplicate_repositories_are_rejected_case_insensitively():
    with pytest.raises(ValidationError):
        validate_unique(
            [
                entry(),
                entry(
                    repository="https://github.com/Owner/Example",
                    image="other",
                    containerfile="images/other/Containerfile",
                ),
            ]
        )


def test_validate_repositories_reports_index():
    with pytest.raises(ValidationError, match=r"repositories\[1\]"):
        validate_repositories([entry(), entry(image="Bad")])
